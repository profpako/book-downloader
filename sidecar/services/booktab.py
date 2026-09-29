"""Zanichelli Booktab/MyZanichelli reale da djlight/pdfgrabber services/znc.py."""
from __future__ import annotations

import gzip
import logging as _logging
import re as _re
import tempfile as _tempfile
import xml.etree.ElementTree as _et
from base64 import b64decode, b64encode
from io import BytesIO
from itertools import cycle, zip_longest
from pathlib import Path
from zipfile import ZipFile

import requests

from .base import BaseService, ServiceAuthError

_log = _logging.getLogger("sidecar")

FAST_API = "https://booktab-fast-api.zanichelli.it/api/v5"
MAIN_API = "https://booktab-main-api.zanichelli.it/api/v5"
STATIC_API = "https://staticmy.zanichelli.it/catalogo/assets"

XOR_KEY = b64decode(
    "VJTP4zAVsLlrpNXXTGV981Tn7zCew0MHD+VkofkRMPcLjLB+w0N/zj02HzPs/4aRDrDSawNqqN2oXH9V36O0vM2CaKH8duGfUhxF+dY"
    "3zAGa0UOaKYEZXEMwM0ZqRW7J8Su/gYV8twZQbyRggzl0LpYVhwiSuGnsPYy61qSGfK1PigKneXc3mzGK/0Oct+SL10rTCPHn3zloHmhJd"
    "nVFsk8o8CdR78mgg3dLSnEvaIlJppPfhi+qjnA7LUiAxhRxh5XokzOIUn04zyi4gyR2cPCRXpol0qsAf7vi0bzRUvM3TloqjjfLa3lKCOzL"
    "WixrYrhNLmu+hFfDik49h1kLVg==")


def _xordecrypt(data: bytes) -> bytes:
    dec = bytes(a ^ b for a, b in zip(data, cycle(XOR_KEY)))
    zf = ZipFile(BytesIO(dec))
    return zf.read(zf.namelist()[0])


def _getsecret(key: str) -> bytes:
    return b64encode((key[-4:] + "zanichelli").encode())[:9]


def _blowfish_decrypt(data: bytes, key: bytes) -> bytes:
    from Crypto.Cipher import Blowfish
    from Crypto.Util.Padding import unpad
    cipher = Blowfish.new(key, Blowfish.MODE_ECB)
    return unpad(cipher.decrypt(b64decode(data)), Blowfish.block_size)


def _decrypt_header(infile: bytes, key: bytes) -> bytes:
    f = BytesIO(infile)
    headerlen = int.from_bytes(f.read(4), byteorder="big")
    return _blowfish_decrypt(f.read(headerlen), key) + f.read()


def _outline(node, appended: list, offset: int, level: int) -> list:
    sub = []
    href = node.get("href")
    if href in appended:
        title = node.get("title", "")
        if node.get("feild2"):
            title = node.get("feild2") + " - " + title
        sub.append([level, title, appended.index(href) + offset])
    for child in node.findall("node"):
        sub.extend(_outline(child, appended, offset, level + 1))
    return sub


def _autocrop(page, pad: float = 8.0) -> None:
    """Taglia margini bianchi puri: bbox contenuto via raster veloce, crop vettoriale."""
    import fitz
    zoom = 0.35
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    w, h, n = pix.width, pix.height, pix.n
    if pix.alpha:
        n -= 1
    if n < 3 or w < 10 or h < 10:
        return
    s = pix.samples
    stride = pix.width * pix.n
    TH = 250

    def row_has(y: int) -> bool:
        return min(s[y * stride:(y + 1) * stride]) < TH

    top = next((y for y in range(h) if row_has(y)), None)
    if top is None:
        return
    bot = next((y for y in range(h - 1, -1, -1) if row_has(y)), h - 1)

    def col_has(x: int) -> bool:
        base = x * pix.n
        stop = (h - 1) * stride + base + pix.n
        return (min(s[base:stop:stride]) < TH or min(s[base + 1:stop:stride]) < TH
                or min(s[base + 2:stop:stride]) < TH)

    left = next((x for x in range(w) if col_has(x)), 0)
    right = next((x for x in range(w - 1, -1, -1) if col_has(x)), w - 1)
    rect = fitz.Rect(left / zoom - pad, top / zoom - pad,
                     (right + 1) / zoom + pad, (bot + 1) / zoom + pad)
    rect &= page.mediabox
    if rect.width > 50 and rect.height > 50:
        page.set_cropbox(rect)


def _label_rules(labels: list[str]) -> list[dict]:
    """Comprime sequenza etichette in regole fitz set_page_labels."""
    if not labels:
        return []
    rules, start, cur = [], 0, labels[0]
    for i, lab in enumerate(labels[1:], 1):
        if lab != cur:
            rules.append((start, cur))
            start, cur = i, lab
    rules.append((start, cur))
    out = []
    for startpage, lab in rules:
        if lab.isdigit():
            out.append({"startpage": startpage, "style": "D", "firstpagenum": int(lab)})
        elif lab:
            out.append({"startpage": startpage, "prefix": lab[:20]})
    return out


class BooktabService(BaseService):
    id = "zanichelli-booktab"
    label = "Zanichelli / laZ Ebook"
    username_label = "Email"
    login_hint = "Usa l'email dell'account MyZanichelli."
    description = "Libreria MyZanichelli, inclusi i titoli nei formati Booktab e Kitaboo."

    def login(self, username: str, password: str) -> None:
        import secrets
        import vault as _vault
        self.require_creds(username, password)
        # Device ID stabile per account: non brucia slot dispositivi a ogni login
        dev_key = f"device:{self.id}:{username.strip().lower()}"
        device_id = _vault.load_token(dev_key)  # riuso get/set generici
        if not device_id:
            device_id = secrets.token_hex(8)
            _vault.save_token(dev_key, device_id)
        try:
            r = requests.post(f"{FAST_API}/sessions", json={
                "username": username,
                "password": password,
                "device_id": device_id,
                "device_name": "BookDownloader",
                "dry_run": False,
            }, timeout=20)
            data = r.json()
        except (requests.RequestException, ValueError):
            raise ServiceAuthError("Controlla la connessione e riprova.")
        _log.info("booktab login http=%s keys=%s msg=%s", r.status_code,
                  sorted(data.keys())[:8], str(data.get("message") or data.get("error", ""))[:200])
        if "token" not in data:
            raise ServiceAuthError(data.get("message") or "Password errata o account non valido.")
        self.token = data["token"]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _library_raw(self) -> list[dict]:
        try:
            rb = requests.get(f"{FAST_API}/books", headers=self._headers(), timeout=20)
            books = rb.json()
            meta = requests.get(f"{FAST_API}/metadata", timeout=20).json()
        except (requests.RequestException, ValueError):
            raise ServiceAuthError("Controlla la connessione e riprova.")
        if rb.status_code == 401:
            raise ServiceAuthError("Sessione scaduta, riaccedi.")
        if isinstance(books, dict):
            _log.info("booktab books msg=%s", str(books.get("message", ""))[:200])
            if not books.get("books"):
                raise ServiceAuthError(books.get("message") or "Nessun libro trovato per questo account.")
        titles = {str(b.get("isbn")): b for b in meta.get("books", [])} if isinstance(meta, dict) else {}
        raw = books.get("books", []) if isinstance(books, dict) else []
        no_isbn = sum(1 for b in raw if not b.get("isbn"))
        meta_only = [str(b.get("isbn")) for b in meta.get("books", [])] if isinstance(meta, dict) else []
        in_books = {str(b.get("isbn")) for b in raw if b.get("isbn")}
        _log.info("booktab counts: api=%d no_isbn=%d meta=%d meta_only=%d sample_meta_only=%s",
                  len(raw), no_isbn, len(meta_only),
                  sum(1 for i in meta_only if i not in in_books), meta_only[:5])
        out = []
        for b in books.get("books", []) if isinstance(books, dict) else []:
            isbn = str(b.get("isbn", ""))
            m = titles.get(isbn, {})
            out.append({
                "id": isbn,
                "title": m.get("title", "Senza titolo"),
                "author": m.get("author", ""),
                "publisher": m.get("publisher", ""),
                "isbn": isbn,
                "format": b.get("format", ""),
                "version": b.get("version", ""),
                "encryption": b.get("encryptionType", 0),
                "related": b.get("relatedIsbns", []) or [],
            })
        return out

    def list_books(self) -> list[dict]:
        if not self.token:
            raise ServiceAuthError("Devi prima accedere.")
        if self.token.startswith("booktab-") and len(self.token) < 40:
            raise ServiceAuthError("Sessione aggiornata: riaccedi con le tue credenziali.")
        items = self._library_raw()
        seen: dict[str, int] = {}
        for b in items:
            seen[b["title"]] = seen.get(b["title"], 0) + 1
        out = []
        for b in items:
            title = b["title"]
            if seen[title] > 1 and b["format"]:
                title = f"{title} ({b['format']} {b['version']}".strip() + ")"
            out.append({**b, "title": title})
        return out

    # ---- download ----

    def _metadata(self) -> dict:
        try:
            meta = requests.get(f"{FAST_API}/metadata", timeout=30).json()
            return {str(b.get("isbn")): b for b in meta.get("books", [])} if isinstance(meta, dict) else {}
        except (requests.RequestException, ValueError):
            return {}

    def _sniff(self, isbn: str) -> tuple[str, str, bool]:
        """Rileva formato di un ISBN fuori libreria: legacy / booktab3 / kitaboo + xor."""
        raw = self._resource(isbn, "volume.xml")
        if not raw:
            raise ServiceAuthError("ISBN non valido o non associato (usa ISBN digitale eBook, non cartaceo).")
        try:
            root = _et.fromstring(raw.decode())
            if root.find("volumes") is not None:
                return "booktab", "2.0", False
            return "booktab", "3.0", False
        except _et.ParseError:
            pass
        try:
            root = _et.fromstring(_xordecrypt(raw).decode())
            if root.find("volumes") is not None:
                return "booktab", "2.0", True
            return "booktab", "3.0", True
        except Exception:
            pass
        return "kitaboo", "", False

    def _book_info(self, isbn: str) -> dict:
        lib = next((b for b in self._library_raw() if b["id"] == isbn), None)
        if lib is not None:
            return lib
        meta = self._metadata().get(isbn)
        if meta is None:
            raise ServiceAuthError("ISBN non valido o non associato (usa ISBN digitale eBook, non cartaceo).")
        fmt, ver, enc = self._sniff(isbn)
        _log.info("booktab isbn %s fuori libreria: %s %s enc=%s", isbn, fmt, ver, enc)
        return {"id": isbn, "title": meta.get("title", isbn),
                "author": meta.get("author", ""), "publisher": meta.get("publisher", ""),
                "isbn": isbn,
                "format": fmt, "version": ver, "encryption": int(enc), "related": []}

    def _resource(self, isbn: str, path: str, progress=None, total: float = 0,
                  done: float = 0) -> bytes | bool:
        r = requests.get(f"{MAIN_API}/books/{isbn}/resource/{path}", headers=self._headers(),
                         stream=bool(progress), timeout=60)
        if r.status_code != 200:
            return False
        if not progress:
            return r.content
        length = int(r.headers.get("content-length", 1))
        buf = b""
        for chunk in r.iter_content(chunk_size=102400):
            buf += chunk
            progress(done + len(buf) / length * total)
        return buf

    def _manifest(self, isbn: str) -> dict:
        r = requests.get(f"{MAIN_API}/books/{isbn}/resource/manifest.log",
                         headers=self._headers(), timeout=30)
        if r.status_code == 401:
            raise ServiceAuthError("Sessione scaduta, riaccedi.")
        return r.json()

    def download(self, book_id: str, out_dir: Path, progress=None) -> Path:
        import fitz
        if not self.token:
            raise ServiceAuthError("Devi prima accedere.")
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        def rep(f: float) -> None:
            if progress:
                progress(max(0.0, min(1.0, f)))

        info = self._book_info(book_id)
        title = "".join(c if c.isalnum() or c in " -_" else "_" for c in info["title"]).strip()
        pdf_path = out_dir / f"zanichelli-{book_id}-{title}.pdf"
        pdf = fitz.Document()
        toc, labels = [], []
        fmt = info["format"]
        try:
            if fmt == "booktab":
                if info["version"] in ("1.0", "2.0"):
                    pdf, toc, labels = self._legacy(book_id, pdf, toc, labels, rep)
                else:
                    pdf, toc, labels = self._bt3(book_id, pdf, toc, labels, rep, bool(info["encryption"]))
            else:
                pdf, toc, labels = self._kitaboo(book_id, pdf, toc, labels, rep)
            rep(0.97)
            if toc:
                try:
                    pdf.set_toc(toc)
                except Exception:
                    _log.info("booktab toc skipped")
            rules = _label_rules(labels)
            if rules:
                try:
                    pdf.set_page_labels(rules)
                except Exception:
                    _log.info("booktab labels skipped")
            pdf.set_metadata({"title": info["title"], "author": info.get("author", ""),
                              "subject": f"ISBN {info.get('isbn', book_id)}"})
            pdf.save(str(pdf_path))
            pdf.close()
        except ServiceAuthError:
            raise
        except Exception as exc:
            _log.warning("booktab download %s failed: %r", book_id, exc)
            raise ServiceAuthError("Download non riuscito. Riprova più tardi.")
        rep(1.0)
        return pdf_path

    def _files(self, isbn: str, encryption: bool):
        volumeinfo = self._resource(isbn, "volume.xml")
        if encryption:
            volumeinfo = _xordecrypt(volumeinfo)
        volumeinfo = _et.fromstring(volumeinfo.decode())
        spine = self._resource(isbn, "spine.xml")
        tocelems = {}
        if spine:
            spine = _et.fromstring(spine.decode())
            tocelems = {i.get("id"): i for i in spine.findall("unit")}
        return volumeinfo, tocelems, self._manifest(isbn)

    def _append_unit(self, pdf, unitpdf_bytes: bytes, newlabels: list, config, newtoc: list,
                     tocelems: dict, unitid: str, unittitle: str) -> None:
        import fitz
        unitpdf = fitz.Document(stream=unitpdf_bytes, filetype="pdf")
        pdf.insert_pdf(unitpdf)
        start = int(config.find("pages").text.split("-")[0])
        labels = [p.get("id") for p in config.find("links").findall("page")]
        for j in range(len(unitpdf)):
            plabel = labels[j] if j < len(labels) else None
            newlabels.append(plabel if plabel else str(j + start))
        if tocelems and unitid in tocelems:
            spineitem = tocelems[unitid]
            pageindex = [p.get("btbid") for p in config.find("links").findall("page")]
            try:
                pageno = len(pdf) - len(unitpdf) + pageindex.index(spineitem.get("page")) + 1
            except ValueError:
                pageno = len(pdf) - len(unitpdf) + 1
            newtoc.append([1, spineitem.find("title").text, pageno])
            for h in spineitem.findall("h1"):
                try:
                    hp = len(pdf) - len(unitpdf) + pageindex.index(h.get("page")) + 1
                except ValueError:
                    continue
                newtoc.append([2, h.find("title").text, hp])
        else:
            newtoc.append([1, unittitle, len(pdf) - len(unitpdf) + 1])

    def _bt3(self, isbn: str, pdf, toc: list, labels: list, rep, encryption: bool):
        rep(0.03)
        volumeinfo, tocelems, manifest = self._files(isbn, encryption)
        resources = [i["path"] for i in manifest["resources"]]
        units = sorted(
            [u for u in volumeinfo.find("volume").find("units").findall("unit") if u.find("resources")],
            key=lambda u: u.find("unitorder").text)
        width = 0.90 / max(len(units), 1)
        for i, unit in enumerate(units):
            btbid, unitid = unit.get("btbid"), unit.get("id")
            base = next(j for j in unit.find("resources").findall("resource") if j.get("type") == "base")
            basepath = next(j.text for j in base.findall("download") if j.get("device") == "desktop")
            if btbid + "/" + basepath not in resources:
                continue
            rep(0.05 + i * width)
            unitzip = ZipFile(BytesIO(self._resource(isbn, btbid + "/" + basepath, rep, width, 0.05 + i * width)))
            config = unitzip.read(btbid + "/config.xml")
            if encryption:
                config = _xordecrypt(config)
            config = _et.fromstring(config.decode())
            pdfpath = config.find("content").text
            if not pdfpath.endswith(".pdf"):
                pdfpath += ".pdf"
            fakepath = next(j.text for j in config.find("filesMap").findall("entry") if j.get("key") == pdfpath)
            unitpdf = unitzip.read(btbid + "/" + fakepath)
            if encryption:
                unitpdf = _xordecrypt(unitpdf)
            self._append_unit(pdf, unitpdf, labels, config, toc, tocelems, unitid, unit.find("displaytitle").text)
        return pdf, toc, labels

    def _legacy(self, isbn: str, pdf, toc: list, labels: list, rep):
        rep(0.03)
        volumeinfo, _, manifest = self._files(isbn, False)
        resources = [i["path"] for i in manifest["resources"]]
        units = [u for vol in volumeinfo.find("volumes").findall("volume")
                 for u in vol.find("units").findall("unit")]
        width = 0.90 / max(len(units), 1)
        for i, unit in enumerate(units):
            if unit.get("href") not in resources:
                continue
            unitid = unit.get("id") or unit.get("href").removesuffix(".zip")
            rep(0.05 + i * width)
            resbytes = self._resource(isbn, unit.get("href"), rep, width, 0.05 + i * width)
            unitzip = ZipFile(BytesIO(resbytes))
            config = _et.fromstring(unitzip.read(f"{unitid}/config.xml").decode())
            content = config.find("content").text
            if content.endswith(".swf"):
                continue
            if not content.endswith(".pdf"):
                content += ".pdf"
            if f"{unitid}/{content}" not in unitzip.namelist():
                continue
            self._append_unit(pdf, unitzip.read(f"{unitid}/{content}"), labels, config, toc,
                              {}, unitid, (unit.find("unittitle").text if unit.find("unittitle") is not None else unitid))
        return pdf, toc, labels

    def _kitaboo(self, isbn: str, pdf, toc: list, labels: list, rep):
        import fitz
        rep(0.03)
        basezip = ZipFile(BytesIO(self._resource(isbn, "base.zip", rep, 0.05, 0.05)))
        base = _et.fromstring(basezip.read("OPS/book_toc.xml").decode())
        pagesmap = {p.get("folioNumber"): p.get("src") for p in
                    sorted(base.find("pages").findall("page"), key=lambda p: int(p.get("sequenceNumber")))}
        chapters = base.find("chapters").findall("chapter")
        appended: list[str] = []
        secret = _getsecret(isbn[:13])
        with _tempfile.TemporaryDirectory(prefix="kitaboo.") as tmp:
            tmpdir = Path(tmp)
            for f in basezip.namelist():
                if f.startswith("OPS/css") or f.startswith("OPS/js") or f.startswith("OPS/fonts"):
                    basezip.extract(f, tmpdir)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch()
                bpage = browser.new_page()
                width = 0.83 / max(len(chapters), 1)
                for off, ch in enumerate(chapters):
                    unitstart = 0.10 + off * width
                    rep(unitstart)
                    chzip = ZipFile(BytesIO(self._resource(
                        isbn, ch.find("chapterPagesFile").text, rep, width / 4, unitstart)))
                    for name in chzip.namelist():
                        if "thumbnail" in name:
                            continue
                        elif name.endswith("xhtml"):
                            raw = chzip.read(name)
                            if not raw.startswith(b"<?xml"):
                                raw = _blowfish_decrypt(raw, secret)
                            (tmpdir / name).parent.mkdir(parents=True, exist_ok=True)
                            (tmpdir / name).write_bytes(raw)
                        elif name.endswith("svgz"):
                            raw = gzip.decompress(_decrypt_header(chzip.read(name), secret))
                            (tmpdir / name).parent.mkdir(parents=True, exist_ok=True)
                            (tmpdir / name).write_bytes(raw)
                        else:
                            chzip.extract(name, tmpdir)
                    pages = ch.find("displayPages").text.split(",")
                    pwidth = (width * 3) / (4 * max(len(pages), 1))
                    for j, page in enumerate(pages):
                        pagefile = pagesmap[page]
                        labels.append(page)
                        appended.append(pagefile)
                        fullpath = tmpdir / "OPS" / pagefile
                        bpage.goto(fullpath.as_uri())
                        # Box reale del contenuto (scrollWidth = viewport → margini bianchi)
                        try:
                            dims = bpage.evaluate(
                                "() => { window.scrollTo(0, 0); let R = 0, B = 0;"
                                " for (const el of document.querySelectorAll('body *')) {"
                                " const b = el.getBoundingClientRect();"
                                " if (b.width > 2 && b.height > 2 && b.width < 6000 && b.height < 30000) {"
                                " R = Math.max(R, b.right); B = Math.max(B, b.bottom); } }"
                                " return {w: R, h: B}; }")
                            pw, ph = f"{int(dims['w'])}px", f"{int(dims['h'])}px"
                        except Exception:
                            dims = bpage.evaluate(
                                "() => ({w: document.documentElement.scrollWidth, "
                                "h: document.documentElement.scrollHeight})")
                            pw, ph = f"{int(dims['w'])}px", f"{int(dims['h'])}px"
                        rep(unitstart + width / 4 + pwidth * j)
                        shot = bpage.pdf(print_background=True, width=pw, height=ph,
                                         page_ranges="1", margin={"top": "0", "bottom": "0",
                                                                  "left": "0", "right": "0"})
                        start = len(pdf)
                        pdf.insert_pdf(fitz.Document(stream=shot, filetype="pdf"))
                        for pno in range(start, len(pdf)):
                            _autocrop(pdf[pno])
                browser.close()
        tocobj = _et.fromstring(basezip.read("OPS/toc.xml").decode())
        for node in tocobj.find("toc").findall("node"):
            toc.extend(_outline(node, appended, len(pdf) + 1, 1))
        return pdf, toc, labels
