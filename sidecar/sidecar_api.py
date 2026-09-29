"""Sidecar API FastAPI minimale (Fase 1.2 PLAN.md). Eseguibile via PyInstaller."""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core import Book, BookDownloader, DownloadJob, ServiceId, ServiceSession
import vault

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("sidecar.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("sidecar")

app = FastAPI(title="Book Downloader Sidecar", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

downloader = BookDownloader(
    out_dir=vault.load_setting("output-directory") or Path.home() / "Books" / "Downloader"
)
_sessions: dict[str, ServiceSession] = {}
_catalogs: dict[str, dict[str, Book]] = {}
_index_lock = threading.Lock()


def _book_dict(book: Book) -> dict:
    return {"id": book.id, "title": book.title, "author": book.author,
            "publisher": book.publisher, "isbn": book.isbn,
            "subtitle": book.subtitle, "service": book.service.value}


def _file_identity(path: Path) -> tuple[str, str, str]:
    prefixes = {"zanichelli-": ServiceId.BOOKTAB.value,
                "hubscuola-": ServiceId.HUBSCUOLA.value, "bsmart-": ServiceId.BSMART.value}
    for prefix, service in prefixes.items():
        if path.stem.startswith(prefix):
            book_id, _, title = path.stem[len(prefix):].partition("-")
            return service, book_id, title.replace("_", " ")
    return "", "", path.stem


def _index_path(out: Path) -> Path:
    return out / ".book-downloader-index.json"


def _read_index(out: Path) -> dict:
    import json

    try:
        data = json.loads(_index_path(out).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_index(out: Path, data: dict) -> None:
    import json

    target = _index_path(out)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


def _sync_catalog(service: ServiceId, books: list[Book], out: Path | None = None) -> None:
    out = out or downloader.out_dir
    catalog = _catalogs.setdefault(service.value, {})
    catalog.update({book.id: book for book in books})
    if not out.exists():
        return
    with _index_lock:
        index = _read_index(out)
        for path in out.glob("*.pdf"):
            file_service, book_id, _ = _file_identity(path)
            book = catalog.get(book_id) if file_service == service.value else None
            if book:
                index[path.name] = _book_dict(book)
        _write_index(out, index)


def _record_download(path: str, service: ServiceId, book_id: str) -> None:
    pdf = Path(path)
    book = _catalogs.get(service.value, {}).get(book_id)
    if book:
        _sync_catalog(service, [book], pdf.parent)


class LoginRequest(BaseModel):
    service: ServiceId
    username: str = ""
    password: str = ""
    use_saved_password: bool = False
    session_cookie: str = ""


class DownloadRequest(BaseModel):
    service: ServiceId
    book_id: str


class DownloadAllRequest(BaseModel):
    service: ServiceId
    book_ids: list[str]


class OutputDirectoryRequest(BaseModel):
    path: str


def _creds_for(service: ServiceId) -> dict:
    session = _sessions.get(service.value)
    if session and session.token:
        return {"username": "saved", "password": "saved"}
    raise HTTPException(status_code=401, detail="Devi prima accedere.")


def _run_bg(service: ServiceId, creds: dict, book_id: str) -> str:
    """Crea job running e scarica in thread: la UI polla /status (barra reale)."""
    import uuid

    job = DownloadJob(service=service, book_id=book_id, status="running")
    job.job_id = str(uuid.uuid4())
    downloader.jobs[job.job_id] = job

    def work() -> None:
        try:
            pdf_path = downloader.download(service, creds, book_id,
                                           progress=lambda _jid, f: setattr(job, "progress", f))
            job.status, job.progress, job.pdf_path = "done", 1.0, pdf_path
            _record_download(pdf_path, service, book_id)
        except Exception as exc:
            job.status = "error"
            job.error = str(exc)

    threading.Thread(target=work, daemon=True).start()
    return job.job_id


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/services")
def services() -> dict:
    from services.registry import all_services

    return {
        "services": [
            {"id": s.id, "label": s.label, "needsBrowser": s.needs_browser,
             "usernameLabel": s.username_label, "loginHint": s.login_hint,
             "implemented": s.implemented, "description": s.description}
            for s in all_services()
        ]
    }


@app.post("/login")
def login(req: LoginRequest) -> dict:
    import vault

    username = (req.username or (vault.load_user(req.service.value) or "")).strip()
    password = req.password
    if req.use_saved_password or not password:
        password = vault.load_password(req.service.value) or ""
    else:
        password = password.strip()
    cookie = (req.session_cookie or "").strip().strip('"').strip("'")
    try:
        session = ServiceSession(req.service)
        session.login({"username": username, "password": password, "session_cookie": cookie})
    except Exception as exc:  # messaggio già in italiano da core.py
        log.info("login %s fallito: %s", req.service.value, exc)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _sessions[req.service.value] = session
    # Abbina credenziali al servizio: riuso senza ridigitare (Fase 1.4)
    vault.save_user(req.service.value, username or "cookie")
    if password:
        vault.save_password(req.service.value, password)
    vault.save_last_service(req.service.value)
    try:
        books = session.list_books()
    except Exception as exc:
        # Login riuscito ma lista fallita: niente 500, avviso in UI
        log.warning("%s list failed: %s", req.service.value, exc)
        return {"ok": True, "books": [], "listWarning": str(exc)}
    _sync_catalog(req.service, books)
    return {
        "ok": True,
        "books": [_book_dict(b) for b in books],
    }


@app.get("/account")
def account(service: ServiceId) -> dict:
    """Credenziali salvate per servizio (password mai restituita)."""
    import vault

    user = vault.load_user(service.value)
    return {
        "service": service.value,
        "username": user,
        "hasPassword": bool(vault.load_password(service.value)),
    }


@app.delete("/account")
def forget_account(service: ServiceId) -> dict:
    import vault

    vault.clear_service(service.value)
    _sessions.pop(service.value, None)
    return {"ok": True}


@app.get("/last-service")
def last_service() -> dict:
    import vault

    return {"service": vault.load_last_service()}


@app.get("/books")
def books(service: ServiceId) -> dict:
    session = _sessions.get(service.value)
    if session is None:
        raise HTTPException(status_code=401, detail="Devi prima accedere.")
    session.refresh_if_needed()
    items = session.list_books()
    _sync_catalog(service, items)
    return {"books": [_book_dict(b) for b in items]}


@app.post("/download")
def download(req: DownloadRequest) -> dict:
    creds = _creds_for(req.service)
    if not req.book_id:
        raise HTTPException(status_code=400, detail="Scegli un libro da scaricare.")
    job_id = _run_bg(req.service, creds, req.book_id)
    return {"jobId": job_id, "status": "running"}


@app.post("/download-all")
def download_all(req: DownloadAllRequest) -> dict:
    creds = _creds_for(req.service)
    ids = [b for b in req.book_ids if b]
    if not ids:
        raise HTTPException(status_code=400, detail="Nessun libro da scaricare.")
    return {"jobIds": [_run_bg(req.service, creds, b) for b in ids]}


@app.get("/status/{job_id}")
def status(job_id: str) -> dict:
    try:
        job = downloader.get_job(job_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "jobId": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "pdfPath": job.pdf_path,
        "error": job.error,
    }


@app.get("/downloads")
def downloads() -> dict:
    out = downloader.out_dir
    files = sorted(out.glob("*.pdf")) if out.exists() else []
    index = _read_index(out)
    result = []
    for file in files:
        service, book_id, fallback_title = _file_identity(file)
        metadata = index.get(file.name, {})
        result.append({"name": file.name, "path": str(file), "service": service,
                       "bookId": book_id, "title": metadata.get("title") or fallback_title,
                       "subtitle": metadata.get("subtitle", ""),
                       "author": metadata.get("author", ""),
                       "publisher": metadata.get("publisher", ""),
                       "isbn": metadata.get("isbn", ""), "size": file.stat().st_size})
    return {"dir": str(out), "files": result}


@app.delete("/downloads/{name}")
def delete_download(name: str) -> dict:
    if Path(name).name != name or Path(name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Nome file non valido.")
    out = downloader.out_dir
    file = out / name
    try:
        file.unlink()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Il libro non esiste più.") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Il file non può essere eliminato.") from exc
    with _index_lock:
        index = _read_index(out)
        index.pop(name, None)
        _write_index(out, index)
    return {"deleted": name}


@app.get("/settings/output-directory")
def output_directory() -> dict:
    return {"path": str(downloader.out_dir)}


@app.put("/settings/output-directory")
def set_output_directory(req: OutputDirectoryRequest) -> dict:
    import os

    out = Path(req.path).expanduser()
    if not out.is_absolute():
        raise HTTPException(status_code=400, detail="Scegli una cartella con percorso assoluto.")
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail="La cartella non può essere creata.") from exc
    if not out.is_dir() or not os.access(out, os.W_OK):
        raise HTTPException(status_code=400, detail="La cartella non è scrivibile.")
    downloader.out_dir = out
    vault.save_setting("output-directory", str(out))
    for service, catalog in _catalogs.items():
        _sync_catalog(ServiceId(service), list(catalog.values()), out)
    return {"path": str(out)}


def _native_directory_dialog() -> str:
    import shutil
    import subprocess

    if sys.platform == "darwin":
        cmd = ["/usr/bin/osascript", "-e",
               'POSIX path of (choose folder with prompt "Scegli dove salvare i libri")']
    elif sys.platform == "win32":
        script = ("Add-Type -AssemblyName System.Windows.Forms;"
                  "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
                  "$d.Description='Scegli dove salvare i libri';"
                  "if($d.ShowDialog() -eq 'OK'){$d.SelectedPath}")
        cmd = ["powershell", "-NoProfile", "-Command", script]
    elif shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", "--directory", "--title=Scegli dove salvare i libri"]
    elif shutil.which("kdialog"):
        cmd = ["kdialog", "--getexistingdirectory", ".", "--title", "Scegli dove salvare i libri"]
    else:
        raise HTTPException(status_code=501, detail="Selettore cartella non disponibile su questo sistema.")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


@app.post("/settings/choose-output-directory")
def choose_output_directory() -> dict:
    chosen = _native_directory_dialog()
    return set_output_directory(OutputDirectoryRequest(path=chosen)) if chosen else {"path": None}


@app.post("/shutdown")
def shutdown() -> dict:
    import os
    import threading

    threading.Timer(0.2, lambda: os._exit(0)).start()
    return {"ok": True}


if __name__ == "__main__":
    import socket

    import uvicorn

    def free_port(want: int) -> int:
        for p in range(want, want + 20):
            with socket.socket() as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(("127.0.0.1", p))
                    return p
                except OSError:
                    continue
        return want

    want = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8923
    port = free_port(want)
    print(f"READY port={port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
