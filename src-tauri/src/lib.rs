use std::io::{self, BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Mutex, OnceLock};

use serde_json::json;
use tauri::Manager;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

const MAX_BACKEND_OUTPUT_LINES: usize = 20;
const MAX_BACKEND_OUTPUT_LINE_BYTES: usize = 512 * 1024;
#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

struct BackendSession {
    child: std::process::Child,
    stdin: std::process::ChildStdin,
    stdout: BufReader<std::process::ChildStdout>,
}

fn read_bounded_line<R: BufRead>(reader: &mut R, output: &mut Vec<u8>) -> io::Result<usize> {
    output.clear();
    loop {
        let (bytes_to_consume, found_newline, overflowed) = {
            let available = reader.fill_buf()?;
            if available.is_empty() {
                return Ok(output.len());
            }

            let newline_position = available.iter().position(|byte| *byte == b'\n');
            let candidate_bytes = newline_position
                .map(|position| position + 1)
                .unwrap_or(available.len());
            let remaining_capacity = MAX_BACKEND_OUTPUT_LINE_BYTES.saturating_sub(output.len());
            let bytes_to_copy = candidate_bytes.min(remaining_capacity);
            output.extend_from_slice(&available[..bytes_to_copy]);
            (
                bytes_to_copy,
                newline_position.is_some() && bytes_to_copy == candidate_bytes,
                candidate_bytes > remaining_capacity,
            )
        };

        reader.consume(bytes_to_consume);
        if overflowed {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!(
                    "Backend output line exceeds the {} KiB limit",
                    MAX_BACKEND_OUTPUT_LINE_BYTES / 1024
                ),
            ));
        }
        if found_newline {
            return Ok(output.len());
        }
    }
}

impl BackendSession {
    fn start(app: &tauri::AppHandle) -> Result<Self, String> {
        let mut cmd = resolve_backend_command(app)?;
        configure_backend_command(app, &mut cmd)?;

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

        let mut response_line = Vec::new();
        for _ in 0..MAX_BACKEND_OUTPUT_LINES {
            let read = read_bounded_line(&mut self.stdout, &mut response_line)
                .map_err(|err| format!("Failed reading backend stdout: {err}"))?;

            if read == 0 {
                return Err("Backend process exited unexpectedly".to_string());
            }

            let response_text = std::str::from_utf8(&response_line)
                .map_err(|err| format!("Backend output is not valid UTF-8: {err}"))?;
            let trimmed = response_text.trim();
            if trimmed.is_empty() {
                continue;
            }

            match serde_json::from_str::<serde_json::Value>(trimmed) {
                Ok(serde_json::Value::Object(_)) => return Ok(trimmed.to_string()),
                Ok(_) => continue,
                Err(_) => {
                    let preview: String = trimmed.chars().take(200).collect();
                    eprintln!("Ignoring non-JSON backend output: {preview}");
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
    app: tauri::AppHandle,
    command: String,
    message: Option<String>,
    room_name: Option<String>,
) -> Result<String, String> {
    run_backend_command(&app, &command, message.as_deref(), room_name.as_deref())
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

fn resource_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    app.path()
        .resource_dir()
        .map_err(|err| format!("Failed to resolve application resource directory: {err}"))
}

fn bundled_backend_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let file_name = if cfg!(target_os = "windows") {
        "mutinychat-backend.exe"
    } else {
        "mutinychat-backend"
    };
    Ok(resource_dir(app)?.join(file_name))
}

fn bundled_tor_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let file_name = if cfg!(target_os = "windows") {
        "tor.exe"
    } else {
        "tor"
    };
    Ok(resource_dir(app)?.join("tor").join(file_name))
}

fn configure_backend_command(app: &tauri::AppHandle, command: &mut Command) -> Result<(), String> {
    let tor_path = bundled_tor_path(app)?;
    let tor_directory = tor_path
        .parent()
        .ok_or_else(|| "Bundled Tor path has no parent directory".to_string())?;

    if tor_path.is_file() {
        command.env("MUTINYCHAT_TOR_PATH", &tor_path);
        command.current_dir(tor_directory);
    } else if !cfg!(debug_assertions) {
        return Err(format!(
            "Bundled Tor executable is missing at {}",
            tor_path.display()
        ));
    }

    if !cfg!(debug_assertions) {
        command.env("MUTINYCHAT_REQUIRE_BUNDLED_TOR", "1");
    }

    #[cfg(target_os = "windows")]
    command.creation_flags(CREATE_NO_WINDOW);

    Ok(())
}

fn resolve_backend_command(app: &tauri::AppHandle) -> Result<Command, String> {
    if !cfg!(debug_assertions) {
        let backend_path = bundled_backend_path(app)?;
        if backend_path.is_file() {
            return Ok(Command::new(backend_path));
        }
        return Err(format!(
            "Bundled backend executable is missing at {}",
            backend_path.display()
        ));
    }

    for script in backend_script_candidates() {
        if script.exists() {
            return Ok(python_command(script));
        }
    }

    for path in backend_exec_candidates() {
        if path.is_file() {
            return Ok(Command::new(path));
        }
    }

    Err("Backend not found. Expected backend/main.py or a local mutinychat-backend executable in a development checkout.".to_string())
}

fn run_backend_command(
    app: &tauri::AppHandle,
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
        *guard = Some(BackendSession::start(app)?);
    }

    let session = guard
        .as_mut()
        .ok_or_else(|| "Backend session unavailable".to_string())?;

    match session.send_command(&payload) {
        Ok(response) => Ok(response),
        Err(first_error) => {
            *guard = Some(BackendSession::start(app)?);
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

#[cfg(test)]
mod tests {
    use super::{read_bounded_line, MAX_BACKEND_OUTPUT_LINE_BYTES};
    use std::io::{Cursor, ErrorKind};

    #[test]
    fn bounded_line_reader_accepts_normal_json() {
        let mut reader = Cursor::new(b"{\"status\":\"ok\"}\nnext\n".to_vec());
        let mut output = Vec::new();

        let read = read_bounded_line(&mut reader, &mut output).expect("line should be accepted");

        assert_eq!(read, output.len());
        assert_eq!(b"{\"status\":\"ok\"}\n", output.as_slice());
    }

    #[test]
    fn bounded_line_reader_accepts_exact_limit_including_newline() {
        let mut input = vec![b'x'; MAX_BACKEND_OUTPUT_LINE_BYTES - 1];
        input.push(b'\n');
        let mut reader = Cursor::new(input);
        let mut output = Vec::new();

        let read = read_bounded_line(&mut reader, &mut output).expect("boundary line should pass");

        assert_eq!(MAX_BACKEND_OUTPUT_LINE_BYTES, read);
        assert_eq!(MAX_BACKEND_OUTPUT_LINE_BYTES, output.len());
    }

    #[test]
    fn bounded_line_reader_rejects_oversized_line_without_growing_past_limit() {
        let mut input = vec![b'x'; MAX_BACKEND_OUTPUT_LINE_BYTES];
        input.extend_from_slice(b"x\n");
        let mut reader = Cursor::new(input);
        let mut output = Vec::new();

        let error =
            read_bounded_line(&mut reader, &mut output).expect_err("line should be rejected");

        assert_eq!(ErrorKind::InvalidData, error.kind());
        assert_eq!(MAX_BACKEND_OUTPUT_LINE_BYTES, output.len());
    }

    #[test]
    fn bounded_line_reader_handles_eof_without_newline() {
        let mut reader = Cursor::new(b"{\"status\":\"ok\"}".to_vec());
        let mut output = Vec::new();

        let read = read_bounded_line(&mut reader, &mut output).expect("EOF line should pass");

        assert_eq!(b"{\"status\":\"ok\"}".len(), read);
    }
}
