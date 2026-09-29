"""Pearson Reader+: piattaforma attiva, integrazione ancora da implementare."""
from __future__ import annotations

from .base import BaseService, ServiceAuthError

class PearsonReaderService(BaseService):
    id = "pearson-reader"
    label = "Pearson Reader+"
    needs_browser = True
    implemented = False
    description = "Lettore Pearson per corsi e libri compatibili con Reader+."

    def login(self, username: str, password: str) -> None:
        raise ServiceAuthError("Pearson Reader+: servizio da implementare.")

    def list_books(self) -> list[dict]:
        raise ServiceAuthError("Pearson Reader+: servizio da implementare.")
