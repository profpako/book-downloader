"""bSmart da antoniorasulo89/scuolabooks-reloaded (downloaders/bsmart.py).
Devise web -> auth_token da /api/v6/user -> libreria v6 -> asset singoli -> chiave dinamica.
"""
from __future__ import annotations

import base64
import re as _re
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin as _urljoin

import msgpack
import requests
from Crypto.Cipher import AES

from .base import BaseService, ServiceAuthError

API = "https://www.bsmart.it"
SIGN_IN_URL = "https://www.bsmart.it/users/sign_in"
MY_BSMART_URL = "https://my.bsmart.it/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36")

# Fallback se estrazione chiave dinamica fallisce (pdfgrabber 2023)
FALLBACK_KEY = bytes([30, 0, 184, 152, 115, 19, 157, 33, 4, 237, 80, 26, 139, 248, 104, 155])


class BsmartService(BaseService):
    id = "bsmart"
    label = "bSmart"
    username_label = "Email"
    login_hint = "Usa l'email dell'account bSmart (non il nickname)."
    description = "Libri acquistati o attivati nella libreria bSmart Books."

    def __init__(self) -> None:
        self._s = requests.Session()
        self._s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*"})
        self._enc_key_cache: bytes | None = None

    def _headers(self) -> dict:
        return {"auth_token": self.token or ""}

    def login(self, username: str, password: str) -> None:
        import logging as _logging
        _log = _logging.getLogger("sidecar")
        self.require_creds(username, password)
        cookie = self._devise_requests(username, password)
        _log.info("bsmart login ok via devise")
        self._mint_from_cookie(cookie)

    def _devise_requests(self, username: str, password: str) -> str:
        """Login Devise come bsmart-downloader-gui."""
        html_headers = {"Accept": "text/html,application/xhtml+xml"}
        try:
            r = self._s.get(SIGN_IN_URL, timeout=20, headers=html_headers)
        except requests.RequestException:
            raise ServiceAuthError("Controlla la connessione e riprova.")
        if r.status_code != 200:
            raise ServiceAuthError("Sito bSmart non raggiungibile. Riprova più tardi.")
        form = r.text
        m = _re.search(r'id="new_user".*?authenticity_token" value="([^"]+)"', form, _re.S)
        if not m:
            raise ServiceAuthError("Pagina login cambiata. Riprova più tardi.")
        payload = {"authenticity_token": m.group(1),
                   "user[email]": username, "user[password]": password,
                   "user[remember_me]": "0", "commit": "Accedi"}
        try:
            p = self._s.post(SIGN_IN_URL, data=payload, timeout=30, headers=html_headers)
        except requests.RequestException:
            raise ServiceAuthError("Controlla la connessione e riprova.")
        low = p.text.lower()
        import logging as _logging
        flash = _re.findall(r'(?:alert|flash|error)[^>]{0,80}>([^<]{5,160})', p.text, _re.I)[:3]
        _logging.getLogger("sidecar").info(
            "bsmart devise http=%s post_url=%s still_form=%s flash=%s",
            p.status_code, p.url, 'id="new_user"' in p.text, flash)
        if "email o password non validi" in low or "invalid email or password" in low:
            raise ServiceAuthError("Email o password non validi.")
        if "/users/sign_in" in p.url and 'id="new_user"' in p.text:
            raise ServiceAuthError("Login non riuscito (controlla email/password o eventuale CAPTCHA).")
        cookie = self._s.cookies.get("_bsw_session_v1_production", "")
        if not cookie:
            raise ServiceAuthError("Login riuscito ma cookie non trovato.")
        return cookie

    def login_with_cookie(self, cookie: str) -> None:
        """Accesso per account Google/Microsoft/SSO: incolla _bsw_session_v1_production da browser."""
        import logging as _logging
        _log = _logging.getLogger("sidecar")
        cookie = (cookie or "").strip().strip('"').strip("'")
        if not cookie:
            raise ServiceAuthError("Incolla il cookie di sessione dal browser.")
        self._mint_from_cookie(cookie)
        _log.info("bsmart login ok via cookie")

    def _mint_from_cookie(self, cookie: str) -> None:
        try:
            r = requests.get(f"{API}/api/v5/user",
                             headers={"User-Agent": UA,
                                      "cookie": f"_bsw_session_v1_production={cookie}"},
                             timeout=20)
        except requests.RequestException:
            raise ServiceAuthError("Controlla la connessione e riprova.")
        if r.status_code != 200:
            raise ServiceAuthError("Cookie non valido o scaduto. Ricopialo dal browser.")
        try:
            user = r.json()
        except ValueError:
            raise ServiceAuthError("Risposta inattesa dal server. Riprova più tardi.")
        token = user.get("auth_token", "") if isinstance(user, dict) else ""
        if not token:
            raise ServiceAuthError("Cookie non valido o scaduto. Ricopialo dal browser.")
        self.token = token
        self._s.cookies.set("_bsw_session_v1_production", cookie, domain="www.bsmart.it")
        import vault as _vault
        _vault.save_cookies(self.id, self._s.cookies.get_dict())

    def _restore(self) -> None:
        import vault as _vault
        for k, v in _vault.load_cookies(self.id).items():
            self._s.cookies.set(k, v)

    def _library_raw(self) -> dict[str, dict]:
        self._restore()
        try:
            books = self._s.get(f"{API}/api/v6/books",
                                params={"page_thumb_size": "medium", "per_page": 25000},
                                headers=self._headers(), timeout=20).json()
            pre = self._s.get(f"{API}/books/preactivations".replace("/books/", "/api/v5/books/"),
                              headers=self._headers(), timeout=20).json()
        except (requests.RequestException, ValueError):
            raise ServiceAuthError("Controlla la connessione e riprova.")
        if isinstance(books, dict):
            if books.get("message"):
                raise ServiceAuthError("Sessione scaduta, riaccedi.")
            books = []
        combined = list(books) if isinstance(books, list) else []
        for p in pre if isinstance(pre, list) else []:
            if p.get("no_bsmart") is False:
                combined.extend(p.get("books", []))
        out: dict[str, dict] = {}
        for b in combined:
            bid = str(b.get("id") or b.get("book_id") or "")
            if bid and bid not in out:
                authors = ", ".join(
                    " ".join(str(a.get(k, "")).strip() for k in ("name", "surname")).strip()
                    for a in b.get("authors", []) if isinstance(a, dict)
                )
                brand = b.get("brand") if isinstance(b.get("brand"), dict) else {}
                publisher = brand.get("publisher") if isinstance(brand.get("publisher"), dict) else {}
                activations = b.get("activations") if isinstance(b.get("activations"), list) else []
                activation = activations[0] if activations and isinstance(activations[0], dict) else {}
                out[bid] = {
                    "title": b.get("title") or b.get("name") or f"Libro {bid}",
                    "subtitle": b.get("subtitle") or "", "author": authors,
                    "publisher": publisher.get("name") or brand.get("name") or "",
                    "isbn": activation.get("elisbn") or activation.get("isbn") or "",
                }
        return out

    def list_books(self) -> list[dict]:
        if not self.token:
            raise ServiceAuthError("Devi prima accedere.")
        if self.token in ("cookie-session",) or (self.token.startswith("bsmart-") and len(self.token) < 40):
            raise ServiceAuthError("Sessione aggiornata: riaccedi con le tue credenziali.")
        return [{"id": bid, **b} for bid, b in self._library_raw().items()]

    def _revision(self, book_id: str) -> int:
        r = self._s.get(f"{API}/api/v6/books/by_book_id/{book_id}", headers=self._headers(),
                        timeout=20)
        if r.status_code == 401:
            raise ServiceAuthError("Sessione scaduta, riaccedi.")
        try:
            rev = r.json().get("current_edition", {}).get("revision")
        except ValueError:
            rev = None
        if rev is None:
            raise ServiceAuthError("Libro non leggibile (revisione assente).")
        return rev

    def _resources(self, book_id: str, revision: int) -> list:
        out, page = [], 1
        while True:
            r = self._s.get(f"{API}/api/v5/books/{book_id}/{revision}/resources",
                            params={"per_page": 500, "page": page},
                            headers=self._headers(), timeout=30)
            if r.status_code == 401:
                raise ServiceAuthError("Sessione scaduta, riaccedi.")
            try:
                payload = r.json()
            except ValueError:
                raise ServiceAuthError("Risposta inattesa dal server.")
            if not isinstance(payload, list):
                raise ServiceAuthError("Formato risorse non valido.")
            out.extend(payload)
            if len(payload) < 500:
                break
            page += 1
        return out

    def _enc_key(self) -> bytes:
        if self._enc_key_cache is not None:
            return self._enc_key_cache
        try:
            page = self._s.get(MY_BSMART_URL, timeout=20).text
            scripts = [s for s in _re.findall(r'<script[^>]+src="([^"]+\.js[^"]*)"', page)
                       if s.startswith("/")]
            pat = _re.compile(
                r"var\s+([A-Za-z_$][\w$]*)=String\.fromCharCode\(([^)]*)\),"
                r"([A-Za-z_$][\w$]*)=[\"']constructor[\"'];\3\[\3\]\[\3\]\((.*?)\)\(\)", _re.S)
            for sp in scripts:
                js = self._s.get(_urljoin(MY_BSMART_URL, sp), timeout=30).text
                m = pat.search(js)
                if not m:
                    continue
                char_var, codes, _, expr = m.groups()
                chars = [chr(int(c.strip(), 10)) for c in codes.split(",") if c.strip()]
                idxs = [int(f.group(1)) for f in _re.finditer(rf"{_re.escape(char_var)}\[(\d+)\]", expr)]
                if not idxs:
                    continue
                snippet = "".join(chars[i] for i in idxs if 0 <= i < len(chars))
                # Prima stringa base64 da 16 byte (come gui: candidati 20+ char)
                for cand in _re.findall(r"""['"]([A-Za-z0-9+/]{20,}={0,2})['"]""", snippet):
                    try:
                        key = base64.b64decode(cand)
                    except Exception:
                        continue
                    if len(key) == 16:
                        self._enc_key_cache = key
                        return self._enc_key_cache
        except requests.RequestException:
            pass
        self._enc_key_cache = FALLBACK_KEY
        return self._enc_key_cache

    @staticmethod
    def _decrypt_blob(data: bytes, key: bytes) -> bytes:
        unpacker = msgpack.Unpacker(BytesIO(data[:256]), raw=False)
        header = next(unpacker)
        start = int(header["start"] if isinstance(header, dict) else header[0])
        first, second = data[256:start], data[start:]
        if len(first) < 16:
            raise ServiceAuthError("Pagina non decifrata: libro non supportato.")
        iv = first[:16]
        dec = AES.new(key, AES.MODE_CBC, iv).decrypt(first[16:])
        pad = dec[-1]
        if 1 <= pad <= 16 and dec.endswith(bytes([pad]) * pad):
            dec = dec[:-pad]
        return dec + second

    def download(self, book_id: str, out_dir: Path, progress=None) -> Path:
        from pypdf import PdfReader, PdfWriter
        if not self.token:
            raise ServiceAuthError("Devi prima accedere.")
        self._restore()
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        def rep(f: float) -> None:
            if progress:
                progress(max(0.0, min(1.0, f)))

        lib = self._library_raw()
        if book_id not in lib:
            raise ServiceAuthError("Libro non trovato nella tua libreria.")
        title = "".join(c if c.isalnum() or c in " -_" else "_" for c in lib[book_id]["title"]).strip()
        pdf_path = out_dir / f"bsmart-{book_id}-{title}.pdf"
        try:
            resources = self._resources(book_id, self._revision(book_id))
            assets = [a for res in resources for a in res.get("assets", [])
                      if a.get("use") == "page_pdf"]
            if not assets:
                raise ServiceAuthError("Nessuna pagina PDF per questo libro.")
            key = self._enc_key()
            writer = PdfWriter()
            writer.add_metadata({"/Title": lib[book_id]["title"],
                                 "/Author": lib[book_id].get("author", ""),
                                 "/Subject": f"ISBN {lib[book_id].get('isbn', '')}".strip()})
            n = len(assets)
            for i, asset in enumerate(assets, 1):
                rep((i - 1) / n * 0.95)
                url = asset.get("url", "")
                if not url:
                    raise ServiceAuthError("Pagina senza URL. Riprova più tardi.")
                r = self._s.get(url, timeout=60)
                if r.status_code == 401:
                    raise ServiceAuthError("Sessione scaduta, riaccedi.")
                data = r.content
                if asset.get("encrypted") is not False:
                    try:
                        data = self._decrypt_blob(data, key)
                    except ServiceAuthError:
                        raise
                    except Exception:
                        raise ServiceAuthError("Pagina non decifrata: libro non supportato.")
                reader = PdfReader(BytesIO(data))
                for pg in reader.pages:
                    writer.add_page(pg)
            with open(pdf_path, "wb") as f:
                writer.write(f)
        except ServiceAuthError:
            raise
        except requests.RequestException:
            raise ServiceAuthError("Connessione interrotta durante il download.")
        except Exception:
            raise ServiceAuthError("Download non riuscito. Riprova più tardi.")
        rep(1.0)
        return pdf_path
