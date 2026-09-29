"""Core downloader — refactoring pdfgrabber come libreria (Fase 1.1 PLAN.md)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ServiceId(str, Enum):
    BOOKTAB = "zanichelli-booktab"
    HUBSCUOLA = "hubscuola"
    BSMART = "bsmart"
    PEARSON_ETEXT = "pearson-etext"
    PEARSON_READER = "pearson-reader"
    OXFORD = "oxford"
    LATERZA = "laterza"
    RAFFAELLO = "raffaello"


NEEDS_PLAYWRIGHT: set[ServiceId] = {ServiceId.PEARSON_READER}


class DownloaderError(Exception):
    """Errore di dominio con messaggio già in italiano semplice (Fase 3.3)."""


@dataclass
class Book:
    id: str
    title: str
    service: ServiceId
    author: str = ""
    publisher: str = ""
    isbn: str = ""
    subtitle: str = ""


@dataclass
class DownloadJob:
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    service: ServiceId = ServiceId.BOOKTAB
    book_id: str = ""
    status: str = "queued"  # queued | running | done | error
    progress: float = 0.0
    pdf_path: str | None = None
    error: str | None = None


class ServiceSession:
    """Isola login/token per servizio (Fase 1.1). Delega a services.registry (Fase 1.3)."""

    service: ServiceId

    def __init__(self, service: ServiceId) -> None:
        self.service = service
        self.token: str | None = None
        # Riusa token salvato per evitare accessi ripetuti.
        try:
            from vault import load_token
            self.token = load_token(service.value)
        except Exception:
            self.token = None

    def login(self, credentials: dict) -> None:
        from services.registry import get_service
        import vault

        svc = get_service(self.service.value)
        try:
            if credentials.get("session_cookie") and hasattr(svc, "login_with_cookie"):
                svc.login_with_cookie(credentials["session_cookie"])
            else:
                svc.login(credentials.get("username", ""), credentials.get("password", ""))
        except ValueError as exc:
            raise DownloaderError(str(exc)) from exc
        except Exception as exc:
            raise DownloaderError(str(exc)) from exc
        self.token = svc.token
        if self.token:
            vault.save_token(self.service.value, self.token)
            if credentials.get("session_cookie"):
                vault.save_user(self.service.value, credentials.get("username") or "cookie")
            elif credentials.get("username"):
                vault.save_user(self.service.value, credentials["username"])

    def list_books(self) -> list[Book]:
        if not self.token:
            raise DownloaderError("Devi prima accedere.")
        from services.registry import get_service

        svc = get_service(self.service.value)
        svc.token = self.token
        svc.refresh_if_needed()
        self.token = svc.token
        return [Book(id=b["id"], title=b["title"], service=self.service,
                     author=str(b.get("author") or ""),
                     publisher=str(b.get("publisher") or ""),
                     isbn=str(b.get("isbn") or ""),
                     subtitle=str(b.get("subtitle") or ""))
                for b in svc.list_books()]

    def refresh_if_needed(self) -> None:
        from services.registry import get_service

        svc = get_service(self.service.value)
        svc.token = self.token
        svc.refresh_if_needed()
        self.token = svc.token


class BookDownloader:
    """Interfaccia unificata: download(service, credentials, book_id) -> pdf_path."""

    def __init__(self, out_dir: Path | str = "downloads") -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, DownloadJob] = {}

    def _session(self, service: ServiceId, credentials: dict) -> ServiceSession:
        session = ServiceSession(service)
        user = credentials.get("username", "")
        pwd = credentials.get("password", "")
        # Riusa token salvato se credenziali dummy/assenti (chiamata /download)
        if user and pwd and user != "saved":
            session.login(credentials)
        elif not session.token:
            raise DownloaderError("Devi prima accedere.")
        return session

    def download(self, service: ServiceId, credentials: dict, book_id: str,
                   progress=None) -> str:
        if not book_id:
            raise DownloaderError("Scegli un libro da scaricare.")
        from services.registry import get_service

        session = self._session(service, credentials)
        session.refresh_if_needed()
        svc = get_service(service.value)
        svc.token = session.token
        job = DownloadJob(service=service, book_id=book_id, status="running")
        self.jobs[job.job_id] = job

        def rep(f: float) -> None:
            job.progress = max(0.0, min(1.0, f))
            if progress:
                progress(job.job_id, job.progress)

        try:
            pdf_path = svc.download(book_id, self.out_dir, progress=rep)
        except ValueError as exc:
            job.status = "error"
            job.error = str(exc)
            raise DownloaderError(str(exc)) from exc
        except Exception as exc:
            msg = str(exc) if str(exc) else "Download non riuscito."
            job.status = "error"
            job.error = msg
            raise DownloaderError(msg) from exc
        job.status = "done"
        job.progress = 1.0
        job.pdf_path = str(pdf_path)
        return str(pdf_path)

    def get_job(self, job_id: str) -> DownloadJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise DownloaderError("Download non trovato.")
        return job
