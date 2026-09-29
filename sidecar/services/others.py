"""HUB Scuola e piattaforme attive non ancora implementate."""
from __future__ import annotations

import requests
from .base import BaseService, ServiceAuthError


class HubscuolaService(BaseService):
    """Flusso reale da vvettoretti/hubscuola-downloader (hubyoung_lib.HubYoung, MIT)."""
    id = "hubscuola"
    label = "HubScuola"
    username_label = "Email"
    login_hint = "Usa l'email dell'account HUB Scuola."
    description = "Mondadori Education, Rizzoli Education e Deascuola su HUB Young."
    LOGIN_URL = "https://bce.mondadorieducation.it//app/mondadorieducation/login/loginJsonp"
    INTERNAL_LOGIN_URL = "https://ms-api.hubscuola.it/user/internalLogin"
    LIBRARY_URL = "https://ms-api.hubscuola.it/getLibrary/young"
    UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Mobile/15E148")

    def __init__(self) -> None:
        import requests as _rq

        self._s = _rq.Session()
        self._s.headers["user-agent"] = self.UA

    def login(self, username: str, password: str) -> None:
        self.require_creds(username, password)
        try:
            r = self._s.get(self.LOGIN_URL, params={"username": username, "password": password}, timeout=20)
        except requests.RequestException:
            raise ServiceAuthError("Controlla la connessione e riprova.")
        try:
            data = r.json().get("data", {})
        except ValueError:
            raise ServiceAuthError("Risposta inattesa dal server. Riprova più tardi.")
        if not data.get("sessionId"):
            raise ServiceAuthError("Password errata o account non valido.")
        try:
            r2 = self._s.post(self.INTERNAL_LOGIN_URL, json={
                "username": data["username"],
                "sessionId": data["sessionId"],
                "jwt": data["hubEncryptedUser"],
            }, timeout=20)
            token = r2.json().get("tokenId", "")
        except (requests.RequestException, ValueError):
            raise ServiceAuthError("Accesso non riuscito. Riprova più tardi.")
        if not token:
            raise ServiceAuthError("Accesso non riuscito. Riprova più tardi.")
        self.token = token
        self._s.headers["token-session"] = token

    def list_books(self) -> list[dict]:
        if not self.token:
            raise ServiceAuthError("Devi prima accedere.")
        # Token stub pre-fix (hubscuola-username): forzare re-login
        if self.token.startswith("hubscuola-") and "-" in self.token and len(self.token) < 40:
            raise ServiceAuthError("Sessione aggiornata: riaccedi con le tue credenziali.")
        self._s.headers["token-session"] = self.token
        try:
            r = self._s.get(self.LIBRARY_URL, timeout=20)
        except requests.RequestException:
            raise ServiceAuthError("Controlla la connessione e riprova.")
        if r.status_code == 401:
            raise ServiceAuthError("Sessione scaduta, riaccedi.")
        try:
            lib = r.json()
        except ValueError:
            raise ServiceAuthError("Risposta inattesa dal server. Riprova più tardi.")
        items = lib if isinstance(lib, list) else lib.get("books", lib.get("library", lib.get("volumes", [])))
        out = []
        items = items if isinstance(items, list) else []
        if items:
            import logging as _logging
            sample = items[0] if isinstance(items[0], dict) else {}
            _logging.getLogger("sidecar").info("hubscuola library n=%d keys=%s", len(items), sorted(sample.keys())[:20])
        for b in items:
            if isinstance(b, dict) and b.get("id"):
                title = str(b.get("title", "Senza titolo"))
                # Volumi con stesso titolo (es. Cloud Vol.3/Vol.4): accoda volume/sottotitolo
                vol = next((str(b[k]) for k in ("volume", "vol") if b.get(k)), "")
                sub = next((str(b[k]) for k in ("subtitle",) if b.get(k)), "")
                other = next((str(b[k]) for k in ("edition", "edizione", "number",
                                                  "numero", "parte", "tomo") if b.get(k)), "")
                suffix = " ".join(p for p in (f"Vol. {vol}" if vol else "", sub, other) if p).strip()
                if suffix and suffix.lower() not in title.lower():
                    title = f"{title} ({suffix})"
                isbn = b.get("isbn", "")
                if isinstance(isbn, list):
                    isbn = isbn[0] if isbn else ""
                editor = b.get("editor", "")
                if isinstance(editor, dict):
                    editor = editor.get("name", "")
                out.append({"id": str(b["id"]), "title": title,
                            "subtitle": str(b.get("subtitle") or ""),
                            "author": str(b.get("author") or ""),
                            "publisher": str(editor or ""), "isbn": str(isbn or "")})
        # Titoli ancora duplicati: disambigua con suffisso progressivo stabile
        seen: dict[str, int] = {}
        for b in out:
            seen[b["title"]] = seen.get(b["title"], 0) + 1
        dupes = {t for t, n in seen.items() if n > 1}
        counters: dict[str, int] = {}
        for b in out:
            if b["title"] in dupes:
                counters[b["title"]] = counters.get(b["title"], 0) + 1
                b["title"] = f'{b["title"]} [{counters[b["title"]]}]'
        return out

    def download(self, book_id: str, out_dir, progress=None) -> Path:
        """Download reale (hubyoung_lib): publication.zip → capitoli zip → merge PDF."""
        import io
        import json as _json
        import sqlite3
        import tempfile
        import zipfile
        from pathlib import Path as _Path

        if not self.token:
            raise ServiceAuthError("Devi prima accedere.")
        if not book_id:
            raise ValueError("Scegli un libro da scaricare.")
        self._s.headers["token-session"] = self.token
        out_dir = _Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / f"hubscuola-{book_id}.pdf"

        def rep(f: float) -> None:
            if progress:
                progress(max(0.0, min(1.0, f)))

        try:
            pub = self._s.get(
                f"https://ms-mms.hubscuola.it/downloadPackage/{book_id}/publication.zip",
                params={"tokenId": self.token}, timeout=60)
        except requests.RequestException:
            raise ServiceAuthError("Controlla la connessione e riprova.")
        if pub.status_code == 401:
            raise ServiceAuthError("Sessione scaduta, riaccedi.")
        if pub.status_code != 200 or not pub.content:
            raise ServiceAuthError("Download non riuscito. Riprova più tardi.")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                zpath = _Path(tmp) / "publication.zip"
                zpath.write_bytes(pub.content)
                with zipfile.ZipFile(zpath) as z:
                    z.extract("publication/publication.db", tmp)
                db = sqlite3.connect(str(_Path(tmp) / "publication" / "publication.db"))
                row = db.execute(
                    "SELECT offline_value FROM offline_tbl WHERE offline_path=?",
                    (f"meyoung/publication/{book_id}",)).fetchone()
                db.close()
            chapters = _json.loads(row[0])["indexContents"]["chapters"]
        except Exception:
            raise ServiceAuthError("Libro non leggibile (formato inatteso).")
        if not chapters:
            raise ServiceAuthError("Nessun capitolo trovato per questo libro.")
        try:
            from pypdf import PdfWriter
        except ImportError:
            raise ServiceAuthError("Manca libreria PDF (pypdf). Esegui: pip install pypdf.")
        writer = PdfWriter()
        n = len(chapters)
        for i, ch in enumerate(chapters):
            cid = ch.get("chapterId", "")
            try:
                r = self._s.get(
                    f"https://ms-mms.hubscuola.it/public/{book_id}/{cid}.zip",
                    params={"tokenId": self.token, "app": "v2"}, timeout=60)
            except requests.RequestException:
                raise ServiceAuthError("Connessione interrotta durante il download.")
            if r.status_code != 200:
                raise ServiceAuthError(f"Capitolo {i + 1}/{n} non scaricato. Riprova.")
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                for name in sorted(z.namelist()):
                    if ".pdf" in name:
                        with z.open(name) as f:
                            writer.append(io.BytesIO(f.read()))
            rep((i + 1) / n * 0.95)
        with open(pdf_path, "wb") as f:
            writer.write(f)
        rep(1.0)
        return pdf_path


class PearsonEtextService(BaseService):
    id = "pearson-etext"
    label = "Pearson eText"
    implemented = False
    description = "Piattaforma Pearson eText / Pearson+."

    def login(self, username: str, password: str) -> None:
        raise ServiceAuthError("Pearson eText: servizio da implementare.")

    def list_books(self) -> list[dict]:
        raise ServiceAuthError("Pearson eText: servizio da implementare.")


class GenericService(BaseService):
    implemented = False

    def __init__(self, sid: str, label: str, description: str) -> None:
        self.id = sid
        self.label = label
        self.description = description

    def login(self, username: str, password: str) -> None:
        raise ServiceAuthError(f"{self.label}: servizio da implementare.")

    def list_books(self) -> list[dict]:
        raise ServiceAuthError(f"{self.label}: servizio da implementare.")
