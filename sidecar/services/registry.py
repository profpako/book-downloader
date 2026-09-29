"""Registry servizi (Fase 1.3). Aggiungere qui nuovi servizi."""
from __future__ import annotations

from .base import BaseService
from .booktab import BooktabService
from .bsmart import BsmartService
from .kitaboo import PearsonReaderService
from .others import GenericService, HubscuolaService, PearsonEtextService


def all_services() -> list[BaseService]:
    return [
        BooktabService(),
        HubscuolaService(),
        BsmartService(),
        PearsonEtextService(),
        PearsonReaderService(),
        GenericService("oxford", "Oxford", "Oxford Learner's Bookshelf / Oxford English Hub."),
        GenericService("laterza", "Laterza diBook", "Manuali digitali Laterza, online e offline."),
        GenericService("raffaello", "Raffaello Player", "Libreria digitale del Gruppo Editoriale Raffaello."),
    ]


def get_service(service_id: str) -> BaseService:
    for s in all_services():
        if s.id == service_id:
            return s
    raise ValueError("Servizio non supportato.")
