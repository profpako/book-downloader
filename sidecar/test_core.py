"""Test funzionali minimi Fase 4.1: login, token, download, api."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core import BookDownloader, ServiceId


def _mock_bsmart(monkeypatch):
    """Evita rete nei test: login farlocco + lista fissa (API reale testata a mano)."""
    from services import bsmart as mod

    def fake_login(self, username, password):
        self.require_creds(username, password)
        self.token = "test-token"

    def fake_books(self):
        return [{"id": "b1", "title": "Libro Test", "author": "Ada Autrice",
                 "publisher": "Editore Test", "isbn": "9780000000001"}]

    monkeypatch.setattr(mod.BsmartService, "login", fake_login)
    monkeypatch.setattr(mod.BsmartService, "list_books", fake_books)

    def fake_download(self, book_id, out_dir, progress=None):
        from pathlib import Path as _P
        from pypdf import PdfWriter
        out_dir = _P(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf = out_dir / f"bsmart-{book_id}.pdf"
        w = PdfWriter()
        w.add_blank_page(200, 200)
        with open(pdf, "wb") as f:
            w.write(f)
        if progress:
            progress(1.0)
        return pdf

    monkeypatch.setattr(mod.BsmartService, "download", fake_download)


def test_bsmart_login_download(tmp_path, monkeypatch):
    import vault
    monkeypatch.setattr(vault, "keyring", None)
    vault._fallback = tmp_path / "vault.json"
    _mock_bsmart(monkeypatch)
    d = BookDownloader(out_dir=tmp_path)
    p = d.download(ServiceId.BSMART, {"username": "u", "password": "p"}, "b1")
    assert Path(p).exists()
    job = next(iter(d.jobs.values()))
    assert job.status == "done"


def test_bsmart_login_usa_form_devise_canonico():
    from services.bsmart import BsmartService, SIGN_IN_URL

    class Response:
        status_code = 200
        url = "https://my.bsmart.it/"
        text = '<form id="new_user"><input name="authenticity_token" value="csrf"></form>'

    class Session:
        def __init__(self):
            self.cookies = {"_bsw_session_v1_production": "sessione"}
            self.posted = None

        def get(self, url, **kwargs):
            assert url == "https://www.bsmart.it/users/sign_in"
            return Response()

        def post(self, url, data, **kwargs):
            self.posted = (url, data)
            return Response()

    service = BsmartService()
    service._s = Session()
    assert service._devise_requests("utente@example.it", "segreta") == "sessione"
    assert service._s.posted == (SIGN_IN_URL, {
        "authenticity_token": "csrf", "user[email]": "utente@example.it",
        "user[password]": "segreta", "user[remember_me]": "0", "commit": "Accedi",
    })


def test_download_senza_login_fallisce(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    # ricarica fallback isolato
    import vault
    monkeypatch.setattr(vault, "keyring", None)
    vault._fallback = tmp_path / "vault.json"
    d = BookDownloader(out_dir=tmp_path)
    try:
        d.download(ServiceId.BSMART, {}, "b1")
        raise AssertionError("doveva fallire")
    except Exception as exc:
        assert "accedere" in str(exc).lower()


def test_registry_tutti():
    from services.registry import all_services
    services = all_services()
    ids = {s.id for s in services}
    assert {"zanichelli-booktab", "hubscuola", "bsmart"} <= ids
    assert {"scuolabook", "mondadori", "zanichelli-kitaboo"}.isdisjoint(ids)
    assert {s.id for s in services if not s.implemented} == {
        "pearson-etext", "pearson-reader", "oxford", "laterza", "raffaello"
    }


def _isolated_vault(tmp_path, monkeypatch):
    import vault
    monkeypatch.setattr(vault, "keyring", None)
    vault._fallback = tmp_path / "vault.json"
    return vault


def test_vault_password_last_service(tmp_path, monkeypatch):
    vault = _isolated_vault(tmp_path, monkeypatch)
    vault.save_user("bsmart", "mario")
    vault.save_password("bsmart", "segreta")
    vault.save_last_service("bsmart")
    assert vault.load_user("bsmart") == "mario"
    assert vault.load_password("bsmart") == "segreta"
    assert vault.load_last_service() == "bsmart"
    vault.clear_service("bsmart")
    assert vault.load_password("bsmart") is None
    assert vault.load_user("bsmart") is None


def test_output_directory(tmp_path, monkeypatch):
    vault = _isolated_vault(tmp_path, monkeypatch)
    import sidecar_api
    from fastapi.testclient import TestClient

    sidecar_api.vault = vault
    c = TestClient(sidecar_api.app)
    out = tmp_path / "libri"
    r = c.put("/settings/output-directory", json={"path": str(out)})
    assert r.status_code == 200
    assert out.is_dir()
    assert sidecar_api.downloader.out_dir == out
    assert vault.load_setting("output-directory") == str(out)


def test_archivio_usa_catalogo_e_cambia_cartella(tmp_path, monkeypatch):
    _isolated_vault(tmp_path, monkeypatch)
    import sidecar_api
    from core import Book
    from fastapi.testclient import TestClient

    sidecar_api._catalogs.clear()
    first = tmp_path / "prima"
    first.mkdir()
    (first / "bsmart-b1-file.pdf").touch()
    sidecar_api.downloader.out_dir = first
    book = Book("b1", "Titolo vero", ServiceId.BSMART, "Ada Autrice",
                "Editore Test", "9780000000001")
    sidecar_api._sync_catalog(ServiceId.BSMART, [book])
    c = TestClient(sidecar_api.app)
    item = c.get("/downloads").json()["files"][0]
    assert (item["title"], item["author"], item["isbn"]) == (
        "Titolo vero", "Ada Autrice", "9780000000001")

    second = tmp_path / "seconda"
    second.mkdir()
    (second / "bsmart-b1-altro.pdf").touch()
    assert c.put("/settings/output-directory", json={"path": str(second)}).status_code == 200
    data = c.get("/downloads").json()
    assert data["dir"] == str(second)
    assert data["files"][0]["title"] == "Titolo vero"


def test_elimina_libro_dall_archivio(tmp_path, monkeypatch):
    _isolated_vault(tmp_path, monkeypatch)
    import sidecar_api
    from fastapi.testclient import TestClient

    out = tmp_path / "libri"
    out.mkdir()
    pdf = out / "bsmart-b1-Titolo.pdf"
    pdf.touch()
    sidecar_api.downloader.out_dir = out
    sidecar_api._write_index(out, {pdf.name: {"title": "Titolo vero"}})

    response = TestClient(sidecar_api.app).delete(f"/downloads/{pdf.name}")

    assert response.status_code == 200
    assert not pdf.exists()
    assert pdf.name not in sidecar_api._read_index(out)
    note = out / "note.txt"
    note.write_text("da conservare", encoding="utf-8")
    assert TestClient(sidecar_api.app).delete(f"/downloads/{note.name}").status_code == 400
    assert note.exists()


def test_dialogo_cartella_aggiorna_destinazione(tmp_path, monkeypatch):
    _isolated_vault(tmp_path, monkeypatch)
    import sidecar_api
    from fastapi.testclient import TestClient

    chosen = tmp_path / "scelta"
    monkeypatch.setattr(sidecar_api, "_native_directory_dialog", lambda: str(chosen))
    r = TestClient(sidecar_api.app).post("/settings/choose-output-directory")
    assert r.status_code == 200
    assert r.json()["path"] == str(chosen)
    assert chosen.is_dir()


def test_login_con_password_salvata(tmp_path, monkeypatch):
    _isolated_vault(tmp_path, monkeypatch)
    _mock_bsmart(monkeypatch)
    import sidecar_api
    from fastapi.testclient import TestClient
    c = TestClient(sidecar_api.app)
    r = c.post("/login", json={"service": "bsmart", "username": "u", "password": "p"})
    assert r.status_code == 200
    assert r.json()["books"][0]["author"] == "Ada Autrice"
    assert c.get("/account", params={"service": "bsmart"}).json()["hasPassword"] is True
    assert c.get("/last-service").json()["service"] == "bsmart"
    r2 = c.post("/login", json={"service": "bsmart", "username": "u",
                                "password": "", "use_saved_password": True})
    assert r2.status_code == 200
