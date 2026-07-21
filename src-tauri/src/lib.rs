use std::io::{self, BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, SyncSender, TrySendError};
use std::sync::{Mutex, OnceLock, TryLockError};
use std::thread;
use std::time::{Duration, Instant};

use serde_json::json;
use tauri::Manager;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

const MAX_BACKEND_OUTPUT_LINES: usize = 20;
const MAX_BACKEND_OUTPUT_LINE_BYTES: usize = 512 * 1024;
const BACKEND_REQUEST_QUEUE_CAPACITY: usize = 1;
const BACKEND_POLL_RESPONSE_TIMEOUT: Duration = Duration::from_secs(5);
const BACKEND_DEFAULT_RESPONSE_TIMEOUT: Duration = Duration::from_secs(15);
const BACKEND_TOR_RESPONSE_TIMEOUT: Duration = Duration::from_secs(90);
const BACKEND_CLOSE_COMMAND_TIMEOUT: Duration = Duration::from_secs(2);
const BACKEND_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(2);
#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

struct BackendRequest {
    payload: String,
    response_sender: SyncSender<Result<String, String>>,
}

struct BackendSession {
    child: std::process::Child,
    request_sender: Option<SyncSender<BackendRequest>>,
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

fn exchange_backend_command<W: Write, R: BufRead>(
    stdin: &mut W,
    stdout: &mut R,
    payload: &str,
) -> Result<String, String> {
    writeln!(stdin, "{payload}")
        .map_err(|err| format!("Failed writing JSON command to backend stdin: {err}"))?;
    stdin
        .flush()
        .map_err(|err| format!("Failed flushing backend stdin: {err}"))?;

    let mut response_line = Vec::new();
    for _ in 0..MAX_BACKEND_OUTPUT_LINES {
        let read = read_bounded_line(stdout, &mut response_line)
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

fn backend_worker(
    mut stdin: std::process::ChildStdin,
    stdout: std::process::ChildStdout,
    request_receiver: Receiver<BackendRequest>,
) {
    let mut stdout = BufReader::new(stdout);
    while let Ok(request) = request_receiver.recv() {
        let response = exchange_backend_command(&mut stdin, &mut stdout, &request.payload);
        let should_stop = response.is_err();
        if request.response_sender.send(response).is_err() || should_stop {
            break;
        }
    }
}

fn wait_for_backend_response(
    receiver: &Receiver<Result<String, String>>,
    timeout: Duration,
) -> Result<String, String> {
    match receiver.recv_timeout(timeout) {
        Ok(response) => response,
        Err(RecvTimeoutError::Timeout) => Err(format!(
            "Backend response timed out after {} seconds",
            timeout.as_secs()
        )),
        Err(RecvTimeoutError::Disconnected) => {
            Err("Backend I/O worker stopped unexpectedly".to_string())
        }
    }
}

fn backend_command_timeout(command: &str) -> Duration {
    match command {
        "poll_messages" | "ping" | "get_peer_count" => BACKEND_POLL_RESPONSE_TIMEOUT,
        "start_tor" | "create_room" | "join_room" => BACKEND_TOR_RESPONSE_TIMEOUT,
        _ => BACKEND_DEFAULT_RESPONSE_TIMEOUT,
    }
}

fn request_backend_close(
    sender: &SyncSender<BackendRequest>,
    timeout: Duration,
) -> Result<(), String> {
    let (response_sender, response_receiver) = mpsc::sync_channel(1);
    sender
        .try_send(BackendRequest {
            payload: json!({ "cmd": "close_room" }).to_string(),
            response_sender,
        })
        .map_err(|err| match err {
            TrySendError::Full(_) => {
                "Backend is busy; graceful shutdown command could not be queued".to_string()
            }
            TrySendError::Disconnected(_) => {
                "Backend I/O worker stopped before graceful shutdown".to_string()
            }
        })?;
    wait_for_backend_response(&response_receiver, timeout).map(|_| ())
}

fn finish_backend_command<T>(
    session: &mut Option<T>,
    result: Result<String, String>,
) -> Result<String, String> {
    match result {
        Ok(response) => Ok(response),
        Err(error) => {
            // The backend may have completed a state-changing request before its response failed.
            // Stop the uncertain session, but never replay that request automatically.
            *session = None;
            Err(format!(
                "Backend command failed and the backend was stopped: {error}"
            ))
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

        let (request_sender, request_receiver) = mpsc::sync_channel(BACKEND_REQUEST_QUEUE_CAPACITY);
        if let Err(err) = thread::Builder::new()
            .name("mutinychat-backend-io".to_string())
            .spawn(move || backend_worker(stdin, stdout, request_receiver))
        {
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!("Failed to start backend I/O worker: {err}"));
        }

        Ok(Self {
            child,
            request_sender: Some(request_sender),
        })
    }

    fn is_running(&mut self) -> bool {
        matches!(self.child.try_wait(), Ok(None))
    }

    fn send_command(
        &mut self,
        payload: &serde_json::Value,
        timeout: Duration,
    ) -> Result<String, String> {
        let sender = self
            .request_sender
            .as_ref()
            .ok_or_else(|| "Backend I/O worker is unavailable".to_string())?;
        let (response_sender, response_receiver) = mpsc::sync_channel(1);
        let request = BackendRequest {
            payload: payload.to_string(),
            response_sender,
        };
        sender.try_send(request).map_err(|err| match err {
            TrySendError::Full(_) => "Backend I/O worker is already busy".to_string(),
            TrySendError::Disconnected(_) => "Backend I/O worker has stopped".to_string(),
        })?;

        wait_for_backend_response(&response_receiver, timeout)
    }
}

impl Drop for BackendSession {
    fn drop(&mut self) {
        if let Some(sender) = self.request_sender.as_ref() {
            let _ = request_backend_close(sender, BACKEND_CLOSE_COMMAND_TIMEOUT);
        }
        self.request_sender.take();
        let deadline = Instant::now() + BACKEND_SHUTDOWN_TIMEOUT;
        while Instant::now() < deadline {
            match self.child.try_wait() {
                Ok(Some(_)) | Err(_) => return,
                Ok(None) => thread::sleep(Duration::from_millis(10)),
            }
        }

        let _ = self.child.kill();
        let deadline = Instant::now() + BACKEND_SHUTDOWN_TIMEOUT;
        while Instant::now() < deadline {
            match self.child.try_wait() {
                Ok(Some(_)) | Err(_) => return,
                Ok(None) => thread::sleep(Duration::from_millis(10)),
            }
        }
    }
}

static BACKEND_SESSION: OnceLock<Mutex<Option<BackendSession>>> = OnceLock::new();

fn backend_session_lock() -> &'static Mutex<Option<BackendSession>> {
    BACKEND_SESSION.get_or_init(|| Mutex::new(None))
}

fn stop_backend_session() {
    let mut guard = match backend_session_lock().try_lock() {
        Ok(guard) => guard,
        Err(TryLockError::WouldBlock) => return,
        Err(TryLockError::Poisoned(poisoned)) => poisoned.into_inner(),
    };
    guard.take();
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

fn development_backend_script() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend/main.py")
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
        command.env("MUTINYCHAT_REQUIRE_BUNDLED_TOR", "1");
        command.current_dir(tor_directory);
    } else if !cfg!(debug_assertions) {
        return Err(format!(
            "Bundled Tor executable is missing at {}",
            tor_path.display()
        ));
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

    let script = development_backend_script();
    if script.is_file() {
        return Ok(python_command(script));
    }

    Err(format!(
        "Development backend not found at the compile-time project path {}",
        script.display()
    ))
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
    let mut guard = match lock.try_lock() {
        Ok(guard) => guard,
        Err(TryLockError::WouldBlock) => {
            if command == "poll_messages" {
                return Ok(json!({ "status": "busy" }).to_string());
            }
            return Err("Backend is busy processing another command; try again".to_string());
        }
        Err(TryLockError::Poisoned(_)) => {
            return Err("Failed to lock backend session".to_string());
        }
    };

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

    let result = session.send_command(&payload, backend_command_timeout(command));
    finish_backend_command(&mut *guard, result)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![backend_ipc])
        .build(tauri::generate_context!())
        .expect("error while building Tauri application");

    app.run(|_app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            stop_backend_session();
        }
    });
}

#[cfg(test)]
mod tests {
    use super::{
        backend_command_timeout, development_backend_script, exchange_backend_command,
        finish_backend_command, read_bounded_line, request_backend_close,
        wait_for_backend_response, BACKEND_DEFAULT_RESPONSE_TIMEOUT, BACKEND_POLL_RESPONSE_TIMEOUT,
        BACKEND_TOR_RESPONSE_TIMEOUT, MAX_BACKEND_OUTPUT_LINE_BYTES,
    };
    use std::io::{Cursor, ErrorKind};
    use std::path::PathBuf;
    use std::sync::mpsc;
    use std::time::{Duration, Instant};

    #[test]
    fn development_backend_is_bound_to_the_compile_time_checkout() {
        let expected = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend/main.py");

        assert_eq!(expected, development_backend_script());
    }

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

    #[test]
    fn backend_exchange_writes_request_and_accepts_json_response() {
        let mut stdin = Vec::new();
        let mut stdout = Cursor::new(b"{\"status\":\"ok\"}\n".to_vec());

        let response = exchange_backend_command(&mut stdin, &mut stdout, "{\"cmd\":\"ping\"}")
            .expect("backend exchange should succeed");

        assert_eq!(b"{\"cmd\":\"ping\"}\n", stdin.as_slice());
        assert_eq!("{\"status\":\"ok\"}", response);
    }

    #[test]
    fn backend_response_wait_has_a_real_deadline() {
        let (_sender, receiver) = mpsc::sync_channel(1);
        let timeout = Duration::from_millis(20);
        let started = Instant::now();

        let error = wait_for_backend_response(&receiver, timeout)
            .expect_err("an unresponsive backend must time out");

        assert!(error.contains("timed out"));
        assert!(started.elapsed() >= timeout);
        assert!(started.elapsed() < Duration::from_secs(1));
    }

    #[test]
    fn backend_commands_use_bounded_class_specific_timeouts() {
        assert_eq!(
            BACKEND_POLL_RESPONSE_TIMEOUT,
            backend_command_timeout("poll_messages")
        );
        assert_eq!(
            BACKEND_TOR_RESPONSE_TIMEOUT,
            backend_command_timeout("create_room")
        );
        assert_eq!(
            BACKEND_TOR_RESPONSE_TIMEOUT,
            backend_command_timeout("join_room")
        );
        assert_eq!(
            BACKEND_DEFAULT_RESPONSE_TIMEOUT,
            backend_command_timeout("send_message")
        );
    }

    #[test]
    fn failed_backend_command_stops_session_without_replaying_request() {
        let mut session = Some("original backend session");

        let error = finish_backend_command(&mut session, Err("response was lost".to_string()))
            .expect_err("an uncertain command result must be returned to the caller");

        assert!(session.is_none());
        assert!(error.contains("backend was stopped"));
        assert!(error.contains("response was lost"));
    }

    #[test]
    fn graceful_backend_close_uses_only_the_idempotent_close_command() {
        let (request_sender, request_receiver) = mpsc::sync_channel::<super::BackendRequest>(1);
        let worker = std::thread::spawn(move || {
            let request = request_receiver.recv().expect("shutdown request");
            assert_eq!(r#"{"cmd":"close_room"}"#, request.payload);
            request
                .response_sender
                .send(Ok(r#"{"status":"closed"}"#.to_string()))
                .expect("shutdown response");
        });

        request_backend_close(&request_sender, Duration::from_secs(1))
            .expect("graceful shutdown should complete");
        worker.join().expect("worker should finish");
    }
}
