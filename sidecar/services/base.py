"""Base per servizi (Fase 1.3). Ogni servizio eredita e sovrascrive login/lista/download."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ServiceAuthError(Exception):
    pass


class BaseService(ABC):
    id: str = ""
    label: str = ""
    needs_browser: bool = False
    token: str | None = None
    username_label: str = "Nome utente"
    login_hint: str = ""
    implemented: bool = True
    description: str = ""

    @abstractmethod
    def login(self, username: str, password: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_books(self) -> list[dict]:
        raise NotImplementedError

    def refresh_if_needed(self) -> None:
        return

    def download(self, book_id: str, out_dir: Path, progress=None) -> Path:
        """Scarica e compone PDF. progress(frazione 0..1) opzionale per barra avanzamento."""
        if not self.token:
            raise ServiceAuthError("Devi prima accedere.")
        if not book_id:
            raise ValueError("Scegli un libro da scaricare.")
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf = out_dir / f"{self.id}-{book_id}.pdf"
        pdf.touch(exist_ok=True)
        if progress:
            progress(1.0)
        return pdf

    @staticmethod
    def require_creds(username: str, password: str) -> None:
        if not username or not password:
            raise ServiceAuthError("Inserisci nome utente e password.")
