use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Mutex, OnceLock};

use serde_json::json;

const MAX_BACKEND_OUTPUT_LINES: usize = 20;

struct BackendSession {
    child: std::process::Child,
    stdin: std::process::ChildStdin,
    stdout: BufReader<std::process::ChildStdout>,
}

impl BackendSession {
    fn start() -> Result<Self, String> {
        let mut cmd = resolve_backend_command()?;
        let mut child = cmd
            .arg("--stdio-json")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|err| format!("Failed to spawn backend process: {err}"))?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "Failed to open backend stdin".to_string())?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "Failed to open backend stdout".to_string())?;

        Ok(Self {
            child,
            stdin,
            stdout: BufReader::new(stdout),
        })
    }

    fn is_running(&mut self) -> bool {
        matches!(self.child.try_wait(), Ok(None))
    }

    fn send_command(&mut self, payload: &serde_json::Value) -> Result<String, String> {
        writeln!(self.stdin, "{payload}")
            .map_err(|err| format!("Failed writing JSON command to backend stdin: {err}"))?;
        self.stdin
            .flush()
            .map_err(|err| format!("Failed flushing backend stdin: {err}"))?;

        let mut response_line = String::new();
        for _ in 0..MAX_BACKEND_OUTPUT_LINES {
            response_line.clear();
            let read = self
                .stdout
                .read_line(&mut response_line)
                .map_err(|err| format!("Failed reading backend stdout: {err}"))?;

            if read == 0 {
                return Err("Backend process exited unexpectedly".to_string());
            }

            let trimmed = response_line.trim();
            if trimmed.is_empty() {
                continue;
            }

            match serde_json::from_str::<serde_json::Value>(trimmed) {
                Ok(serde_json::Value::Object(_)) => return Ok(trimmed.to_string()),
                Ok(_) => continue,
                Err(_) => {
                    eprintln!("Ignoring non-JSON backend output: {trimmed}");
                }
            }
        }

        Err("Backend produced too many invalid output lines".to_string())
    }
}

impl Drop for BackendSession {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

static BACKEND_SESSION: OnceLock<Mutex<Option<BackendSession>>> = OnceLock::new();

fn backend_session_lock() -> &'static Mutex<Option<BackendSession>> {
    BACKEND_SESSION.get_or_init(|| Mutex::new(None))
}

#[tauri::command]
fn backend_ipc(
    command: String,
    message: Option<String>,
    room_name: Option<String>,
) -> Result<String, String> {
    run_backend_command(&command, message.as_deref(), room_name.as_deref())
}

fn push_executable_candidates(candidates: &mut Vec<PathBuf>, root: &Path) {
    candidates.push(root.join("mutinychat-backend"));
    candidates.push(root.join("backend/mutinychat-backend"));
    candidates.push(root.join("backend/dist/mutinychat-backend"));
    candidates.push(root.join("../backend/dist/mutinychat-backend"));

    #[cfg(target_os = "windows")]
    {
        candidates.push(root.join("mutinychat-backend.exe"));
        candidates.push(root.join("backend/mutinychat-backend.exe"));
        candidates.push(root.join("backend/dist/mutinychat-backend.exe"));
        candidates.push(root.join("../backend/dist/mutinychat-backend.exe"));
    }
}

fn backend_exec_candidates() -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    for root in backend_search_roots() {
        push_executable_candidates(&mut candidates, &root);
    }
    candidates
}

fn backend_script_candidates() -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    for root in backend_search_roots() {
        candidates.push(root.join("backend/main.py"));
        candidates.push(root.join("../backend/main.py"));
    }
    candidates
}

fn backend_search_roots() -> Vec<PathBuf> {
    let mut roots = Vec::new();

    if let Ok(cwd) = std::env::current_dir() {
        roots.push(cwd);
    }

    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(mut dir) = exe_path.parent() {
            for _ in 0..6 {
                roots.push(dir.to_path_buf());
                let Some(parent) = dir.parent() else {
                    break;
                };
                dir = parent;
            }
        }
    }

    roots.sort();
    roots.dedup();
    roots
}

fn python_command(script: PathBuf) -> Command {
    #[cfg(target_os = "windows")]
    let mut cmd = {
        let mut command = Command::new("py");
        command.arg("-3");
        command
    };

    #[cfg(not(target_os = "windows"))]
    let mut cmd = Command::new("python3");

    cmd.arg(script);
    cmd
}

fn resolve_backend_command() -> Result<Command, String> {
    if cfg!(debug_assertions) {
        for script in backend_script_candidates() {
            if script.exists() {
                return Ok(python_command(script));
            }
        }
    }

    for path in backend_exec_candidates() {
        if path.is_file() {
            return Ok(Command::new(path));
        }
    }

    for script in backend_script_candidates() {
        if script.exists() {
            return Ok(python_command(script));
        }
    }

    Err("Backend not found. Expected a bundled mutinychat-backend executable or backend/main.py in a development checkout.".to_string())
}

fn run_backend_command(
    command: &str,
    message: Option<&str>,
    room_name: Option<&str>,
) -> Result<String, String> {
    let mut payload = json!({ "cmd": command });
    if let Some(msg) = message {
        payload["message"] = json!(msg);
    }
    if let Some(name) = room_name {
        payload["name"] = json!(name);
    }

    let lock = backend_session_lock();
    let mut guard = lock
        .lock()
        .map_err(|_| "Failed to lock backend session".to_string())?;

    let needs_restart = match guard.as_mut() {
        Some(session) => !session.is_running(),
        None => true,
    };

    if needs_restart {
        *guard = Some(BackendSession::start()?);
    }

    let session = guard
        .as_mut()
        .ok_or_else(|| "Backend session unavailable".to_string())?;

    match session.send_command(&payload) {
        Ok(response) => Ok(response),
        Err(first_error) => {
            *guard = Some(BackendSession::start()?);
            let retry_session = guard
                .as_mut()
                .ok_or_else(|| "Backend session unavailable after restart".to_string())?;
            retry_session.send_command(&payload).map_err(|retry_error| {
                format!("Backend command failed: {first_error}; retry failed: {retry_error}")
            })
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![backend_ipc])
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}
