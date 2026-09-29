use std::net::TcpListener;
use std::sync::Mutex;
use tauri::{Manager, WindowEvent};

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0").ok()
        .and_then(|l| l.local_addr().ok().map(|a| a.port()))
        .unwrap_or(8923)
}

struct SidecarPort(Mutex<u16>);

#[tauri::command]
fn sidecar_port(state: tauri::State<SidecarPort>) -> u16 {
    *state.0.lock().unwrap()
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(SidecarPort(Mutex::new(8923)))
        .invoke_handler(tauri::generate_handler![sidecar_port])
        .setup(|app| {
            use tauri_plugin_shell::ShellExt;
            let port = free_port();
            *app.state::<SidecarPort>().0.lock().unwrap() = port;
            let sidecar = app.shell().sidecar("binaries/api")
                .and_then(|s| s.args(["--port", &port.to_string()]).spawn());
            if let Ok((mut rx, child)) = sidecar {
                app.manage(Mutex::new(Some(child)));
                tauri::async_runtime::spawn(async move {
                    use tauri_plugin_shell::process::CommandEvent;
                    while let Some(ev) = rx.recv().await {
                        if let CommandEvent::Stdout(line) = ev {
                            let t = String::from_utf8_lossy(&line);
                            if t.contains("READY") { println!("{t}"); }
                        }
                    }
                });
            }
            Ok(())
        })
        .on_window_event(|w, ev| {
            if let WindowEvent::Destroyed = ev {
                // Shutdown sidecar alla chiusura (Fase 2.2, std only: no extra deps)
                if let Some(port) = w.app_handle().try_state::<SidecarPort>()
                    .map(|s| *s.0.lock().unwrap()) {
                    use std::io::Write;
                    if let Ok(mut s) = std::net::TcpStream::connect(format!("127.0.0.1:{port}")) {
                        let _ = s.write_all(b"POST /shutdown HTTP/1.0\r\nContent-Length: 0\r\n\r\n");
                    }
                }
                if let Some(m) = w.app_handle().try_state::<Mutex<Option<tauri_plugin_shell::process::CommandChild>>>() {
                    if let Some(child) = m.lock().ok().and_then(|mut g| g.take()) {
                        let _ = child.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("errore avvio app");
}
