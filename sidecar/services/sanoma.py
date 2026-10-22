"""Sanoma My Place: accesso Auth0, libreria e pagine My Digital Book (LM60)."""
from __future__ import annotations

import base64
import json
import mimetypes
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .base import BaseService, ServiceAuthError

PLACE = "https://place.sanoma.it"
AUTH = "https://login.sanoma.it"
DISPLAY_BOOKS = "https://npmitaly-pro-apidistribucion.sanoma.it/mcs/msproducts/api/products/display-books"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

# MuPDF richiede il prefisso xlink originale per immagini e glifi SVG condivisi.
ET.register_namespace("", "http://www.w3.org/2000/svg")
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def _auth_url(url: str, base: str = PLACE) -> str:
    url = urljoin(base, url)
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in ("place.sanoma.it", "login.sanoma.it"):
        raise ServiceAuthError("Risposta inattesa durante l'accesso Sanoma.")
    return url


def _resolve_table(table: list) -> list[dict]:
    """Legge i riferimenti del formato Svelte/devalue usato dalla libreria."""
    resolved = {}

    def resolve(index):
        if not isinstance(index, int) or isinstance(index, bool):
            return index
        if index < 0:
            return None
        if index in resolved:
            return resolved[index]
        value = table[index]
        if isinstance(value, dict):
            result = resolved[index] = {}
            result.update((key, resolve(ref)) for key, ref in value.items())
        elif isinstance(value, list):
            result = resolved[index] = []
            result.extend(resolve(ref) for ref in value)
        else:
            result = resolved[index] = value
        return result

    return [resolve(i) for i, value in enumerate(table)
            if isinstance(value, dict) and "opera_id" in value and "display_name" in value]


class SanomaService(BaseService):
    id = "sanoma"
    label = "Sanoma / My Place"
    username_label = "Email"
    login_hint = "Usa l'email e la password del tuo account My Place Sanoma già trasferito da Pearson."
    description = "Libri Sanoma attivati su My Place, nel formato My Digital Book."

    def __init__(self):
        self._s = requests.Session()
        self._s.headers.update({"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9"})

    def _request(self, method: str, url: str, **kwargs):
        try:
            response = self._s.request(method, url, timeout=60, **kwargs)
        except requests.RequestException:
            raise ServiceAuthError("Controlla la connessione e riprova.") from None
        if response.status_code == 401:
            raise ServiceAuthError("Sessione Sanoma scaduta, riaccedi.")
        if response.status_code >= 400:
            raise ServiceAuthError("Sanoma non ha restituito il contenuto richiesto. Riprova più tardi.")
        return response

    def login(self, username: str, password: str) -> None:
        self.require_creds(username, password)
        self.token = None
        self._s.cookies.clear()
        try:
            self._request("GET", f"{PLACE}/login")
            response = self._request("POST", f"{PLACE}/login?/status", data={
                "ref": f"{PLACE}/", "context": "", "text": username,
            }, headers={"Origin": PLACE, "Referer": f"{PLACE}/login", "x-sveltekit-action": "true"})
            location = _auth_url(response.json()["location"])
            if urlparse(location).netloc != "login.sanoma.it":
                raise ServiceAuthError("Completa il trasferimento o la verifica dell'account su place.sanoma.it, poi riprova.")
            page = self._request("GET", location)
            encoded = re.search(r"window\.atob\('([^']+)'\)", page.text)
            if not encoded:
                raise ServiceAuthError("Pagina di accesso Sanoma cambiata. Riprova più tardi.")
            config = json.loads(base64.b64decode(encoded[1]))
            payload = {**config["internalOptions"], "client_id": config["clientID"],
                       "redirect_uri": f"{PLACE}/", "tenant": config["auth0Tenant"],
                       "connection": "Sanoma-Italy-Database", "username": username,
                       "password": password, "sso": True, "popup_options": {}}
            response = self._s.post(f"{AUTH}/usernamepassword/login", json=payload,
                                    headers={"Origin": AUTH, "Referer": page.url}, timeout=30)
            if response.status_code in (400, 401):
                raise ServiceAuthError("Email o password Sanoma non validi.")
            if response.status_code == 429:
                raise ServiceAuthError("Troppi tentativi di accesso Sanoma. Attendi e riprova.")
            if response.status_code != 200:
                raise ServiceAuthError("Accesso Sanoma non riuscito. Verifica l'account su place.sanoma.it.")
            form = BeautifulSoup(response.content, "html.parser").find("form")
            fields = {field["name"]: field.get("value", "") for field in form.select("input[name]")} if form else {}
            if not all(fields.get(key) for key in ("wa", "wresult", "wctx")):
                raise ServiceAuthError("Accesso Sanoma non riuscito. Verifica l'account su place.sanoma.it.")
            callback = _auth_url(form.get("action") or "/login/callback", AUTH)
            response = self._request("POST", callback, data=fields, headers={"Origin": AUTH})
            if urlparse(response.url).path.startswith("/login"):
                raise ServiceAuthError("Completa la verifica dell'account su place.sanoma.it, poi riprova.")
            self._library_raw()
            self.token = json.dumps([
                {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path, "secure": c.secure}
                for c in self._s.cookies if c.domain.lstrip(".") in ("place.sanoma.it", "sanoma.it")
            ])
            if self.token == "[]":
                self.token = None
                raise ServiceAuthError("Sessione Sanoma non ricevuta. Riprova.")
        except requests.RequestException:
            raise ServiceAuthError("Controlla la connessione e riprova.") from None
        except (ValueError, KeyError, TypeError):
            raise ServiceAuthError("Risposta inattesa durante l'accesso Sanoma. Riprova più tardi.") from None

    def _restore(self):
        if not self.token:
            raise ServiceAuthError("Devi prima accedere.")
        try:
            for cookie in json.loads(self.token):
                if cookie["domain"].lstrip(".") not in ("place.sanoma.it", "sanoma.it"):
                    raise ValueError("domain")
                self._s.cookies.set(**cookie)
        except (ValueError, KeyError, TypeError):
            raise ServiceAuthError("Sessione Sanoma non valida, riaccedi.") from None

    def _library_raw(self) -> list[dict]:
        response = self._request("GET", f"{PLACE}/prodotti_digitali/__data.json",
                                 headers={"Accept": "application/json", "Referer": f"{PLACE}/prodotti_digitali"})
        books = {}
        try:
            for line in response.content.decode("utf-8").splitlines():
                if not line.strip():
                    continue
                payload = json.loads(line)
                if payload.get("type") == "redirect" or urlparse(response.url).path.startswith("/login"):
                    raise ServiceAuthError("Sessione Sanoma scaduta, riaccedi.")
                nodes = payload.get("nodes", []) + [payload]
                for node in nodes:
                    if not isinstance(node, dict) or not isinstance(node.get("data"), list):
                        continue
                    for opera in _resolve_table(node["data"]):
                        if opera.get("is_active") is False:
                            continue
                        for product in opera.get("included") or []:
                            for resource in product.get("resource") or []:
                                url = resource.get("url") or ""
                                bid = str(resource.get("external_id") or "")
                                if not bid.isdecimal() or "/prodotti_digitali/libromedia/" not in url:
                                    continue
                                title = product.get("display_name") or opera["display_name"]
                                volume = resource.get("display_name") or ""
                                if volume and volume.casefold() not in title.casefold():
                                    title = f"{title} - {volume}"
                                isbn = str(product.get("isbn") or "")
                                books.setdefault(bid, {"id": bid, "title": title, "publisher": "Sanoma",
                                                      "author": opera.get("authors") if isinstance(opera.get("authors"), str) else "",
                                                      "isbn": isbn if len(isbn) == 13 and isbn.isdecimal() else "",
                                                      "url": _auth_url(url)})
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ServiceAuthError("Formato della libreria Sanoma inatteso. Riprova più tardi.") from None
        return list(books.values())

    def list_books(self) -> list[dict]:
        self._restore()
        return self._library_raw()

    def download(self, book_id: str, out_dir: Path, progress=None) -> Path:
        import fitz

        self._restore()
        book = next((b for b in self._library_raw() if b["id"] == book_id), None)
        if not book:
            raise ServiceAuthError("Libro non trovato nella tua libreria Sanoma.")
        response = self._request("GET", book["url"], allow_redirects=False)
        redirect = urlparse(urljoin(book["url"], response.headers.get("Location", "")))
        if redirect.scheme != "https" or redirect.netloc != "ebook.sanoma.it":
            raise ServiceAuthError("Impossibile aprire questo libro Sanoma. Riaccedi e riprova.")
        ktoken = parse_qs(redirect.query).get("ktoken", [""])[0]
        if not ktoken:
            raise ServiceAuthError("Impossibile aprire questo libro Sanoma. Riaccedi e riprova.")
        response = self._request("GET", DISPLAY_BOOKS, headers={"X-Auth-Token": ktoken,
                                 "Origin": "https://ebook.sanoma.it", "Referer": "https://ebook.sanoma.it/"})
        try:
            entries = response.json()["data"]
            entry = next(item for item in entries if str(item["gedi"]) == book_id)
            access = entry["book"]
            base = access["url"].rstrip("/")
            parsed = urlparse(base)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("url")
            for name in ("CloudFront-Policy", "CloudFront-Signature", "CloudFront-Key-Pair-Id"):
                self._s.cookies.set(name, access["cookies"][name], domain=parsed.hostname, path=parsed.path + "/", secure=True)
            master = self._request("GET", f"{base}/assets/book/data/master.json").json()
            pages = master["pages"]
            if not pages or any(not str(p["number"]).isdecimal() for p in pages):
                raise ValueError("pages")
        except (ValueError, KeyError, TypeError, StopIteration):
            raise ServiceAuthError("Libro Sanoma non leggibile nel formato My Digital Book supportato.") from None
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        title = "".join(c if c.isalnum() or c in " -_" else "_" for c in book["title"]).strip()
        target = out_dir / f"sanoma-{book_id}-{title[:150]}.pdf"
        with fitz.open() as pdf, tempfile.TemporaryDirectory(dir=out_dir) as tmp:
            for i, page in enumerate(pages):
                number = page["number"]
                url = f"{base}/assets/book/pages/{number}/{number}.svg"
                response = self._request("GET", url)
                try:
                    root = ET.fromstring(response.content)
                    for image in root.iter():
                        if image.tag.rsplit("}", 1)[-1] != "image":
                            continue
                        for key in ("href", "{http://www.w3.org/1999/xlink}href"):
                            href = image.get(key)
                            if href and not href.startswith("data:"):
                                image_url = urljoin(url, href)
                                image_location = urlparse(image_url)
                                if image_location.scheme != "https" or image_location.netloc != parsed.netloc:
                                    raise ServiceAuthError("Immagine del libro Sanoma su un indirizzo non supportato.")
                                asset = self._request("GET", image_url)
                                mime = mimetypes.guess_type(urlparse(image_url).path)[0] or "image/png"
                                image.set(key, f"data:{mime};base64," + base64.b64encode(asset.content).decode())
                    # shortcut: i glifi SVG non sono ricercabili, aggiungere il livello .data se serve la ricerca.
                    with fitz.open(stream=ET.tostring(root), filetype="svg") as svg:
                        with fitz.open(stream=svg.convert_to_pdf(), filetype="pdf") as rendered:
                            pdf.insert_pdf(rendered)
                except (ET.ParseError, ValueError, RuntimeError):
                    raise ServiceAuthError(f"Pagina {i + 1} Sanoma non leggibile. Download interrotto.") from None
                if progress:
                    progress((i + 1) / len(pages) * 0.95)
            pdf.set_metadata({"title": book["title"], "subject": f"ISBN {book['isbn']}"})
            output = Path(tmp) / "book.pdf"
            pdf.save(output, garbage=3, deflate=True)
            output.replace(target)
        if progress:
            progress(1.0)
        return target
