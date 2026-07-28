use serde_json::{json, Value};
use std::{
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::{Arc, Mutex},
};
use tauri::{Manager, State};

struct EngineProcess {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
    next_id: u64,
}

impl EngineProcess {
    fn spawn(resource_dir: &Path) -> Result<Self, String> {
        let packaged = resource_dir.join("engine").join("litemap-engine");
        let mut command = if packaged.is_file() {
            Command::new(packaged)
        } else {
            let root = find_repository_root()
                .ok_or_else(|| "Could not locate the development engine directory".to_string())?;
            let mut development = Command::new("python3");
            development
                .arg("-m")
                .arg("litemap_engine.rpc")
                .env("PYTHONPATH", root.join("engine"))
                .current_dir(root);
            development
        };
        command
            .arg("--serve")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());
        let mut child = command
            .spawn()
            .map_err(|error| format!("Failed to start reconstruction engine: {error}"))?;
        let input = child
            .stdin
            .take()
            .ok_or_else(|| "Engine stdin is unavailable".to_string())?;
        let output = BufReader::new(
            child
                .stdout
                .take()
                .ok_or_else(|| "Engine stdout is unavailable".to_string())?,
        );
        Ok(Self {
            child,
            input,
            output,
            next_id: 1,
        })
    }

    fn request(&mut self, method: &str, params: Value) -> Result<Value, String> {
        if self
            .child
            .try_wait()
            .map_err(|error| error.to_string())?
            .is_some()
        {
            return Err("The reconstruction engine exited unexpectedly".to_string());
        }
        let id = self.next_id;
        self.next_id += 1;
        let request = json!({"jsonrpc":"2.0", "id":id, "method":method, "params":params});
        serde_json::to_writer(&mut self.input, &request).map_err(|error| error.to_string())?;
        self.input
            .write_all(b"\n")
            .map_err(|error| error.to_string())?;
        self.input.flush().map_err(|error| error.to_string())?;
        let mut line = String::new();
        if self
            .output
            .read_line(&mut line)
            .map_err(|error| error.to_string())?
            == 0
        {
            return Err("The reconstruction engine closed its response stream".to_string());
        }
        let response: Value = serde_json::from_str(&line)
            .map_err(|error| format!("Invalid engine response: {error}"))?;
        if response.get("id").and_then(Value::as_u64) != Some(id) {
            return Err("The reconstruction engine returned a mismatched response".to_string());
        }
        if let Some(error) = response.get("error") {
            return Err(error
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("Engine request failed")
                .to_string());
        }
        response
            .get("result")
            .cloned()
            .ok_or_else(|| "Engine response has no result".to_string())
    }
}

impl Drop for EngineProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn find_repository_root() -> Option<PathBuf> {
    let current = std::env::current_dir().ok()?;
    current
        .ancestors()
        .find(|path| path.join("engine/litemap_engine").is_dir())
        .map(Path::to_path_buf)
}

struct EngineState(Arc<Mutex<EngineProcess>>);

#[tauri::command]
fn engine_request(
    method: String,
    params: Value,
    state: State<'_, EngineState>,
) -> Result<Value, String> {
    let mut engine = state
        .0
        .lock()
        .map_err(|_| "Engine supervisor lock was poisoned".to_string())?;
    engine.request(&method, params)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let resource_dir = app
                .path()
                .resource_dir()
                .map_err(|error| error.to_string())?;
            let engine = EngineProcess::spawn(&resource_dir)?;
            app.manage(EngineState(Arc::new(Mutex::new(engine))));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![engine_request])
        .run(tauri::generate_context!())
        .expect("error while running LiteMaptica");
}
