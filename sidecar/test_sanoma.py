"""Flusso Sanoma senza rete: sessione, libreria Svelte e PDF completo."""
import base64
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import fitz
import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent))
from services.base import ServiceAuthError
from services.sanoma import AUTH, DISPLAY_BOOKS, PLACE, SanomaService, _auth_url


def response(payload, url=PLACE + "/", status=200, headers=None):
    result = requests.Response()
    result.status_code = status
    result.url = url
    result._content = (json.dumps(payload) if isinstance(payload, (dict, list)) else payload).encode()
    result.headers.update(headers or {})
    return result


def library(active=True):
    table = []

    def flatten(value):
        index = len(table)
        table.append(None)
        if isinstance(value, dict):
            table[index] = {key: flatten(item) for key, item in value.items()}
        elif isinstance(value, list):
            table[index] = [flatten(item) for item in value]
        else:
            table[index] = value
        return index

    flatten({"opera_id": "opera", "display_name": "Corso", "is_opera": True, "is_active": active,
             "included": [{"display_name": "Corso", "isbn": "9780000000001", "resource": [
                 {"display_name": "Volume 1", "external_id": "12345",
                  "url": "/prodotti_digitali/libromedia/gedi/12345"},
                 {"display_name": "Volume 1", "external_id": "12345",
                  "url": "/prodotti_digitali/libromedia/gedi/12345"},
                 {"display_name": "Guida", "external_id": "99999", "url": "/altre_risorse"},
             ]}]})
    # My Place invia anche dati differiti come righe JSON successive.
    return (json.dumps({"nodes": [None, {"data": []}]}) + "\n" +
            json.dumps({"type": "chunk", "data": table}))


@pytest.fixture
def service():
    s = SanomaService()
    s.token = json.dumps([{"name": "session", "value": "test-session", "domain": "place.sanoma.it",
                           "path": "/", "secure": True}])
    return s


def test_library_restores_session_and_deduplicates_volumes(service):
    service._s.request = Mock(return_value=response(library()))
    books = service.list_books()
    assert len(books) == 1
    assert books[0]["id"] == "12345"
    assert books[0]["title"] == "Corso - Volume 1"
    assert books[0]["isbn"] == "9780000000001"
    assert service._s.cookies.get("session", domain="place.sanoma.it") == "test-session"


def test_library_decodes_svelte_data_as_utf8(service):
    result = response(library().replace("Corso", "Società"))
    result.encoding = "ISO-8859-1"
    service._s.request = Mock(return_value=result)
    assert service.list_books()[0]["title"] == "Società - Volume 1"


def test_library_excludes_expired_licenses(service):
    service._s.request = Mock(return_value=response(library(active=False)))
    assert service.list_books() == []


def test_login_persists_only_place_session(service):
    config = {"internalOptions": {"state": "state", "_csrf": "csrf"},
              "clientID": "client", "auth0Tenant": "sanoma-italy"}
    encoded = base64.b64encode(json.dumps(config).encode()).decode()

    def request(method, url, **kwargs):
        if url.endswith("?/status"):
            return response({"type": "redirect", "location": AUTH + "/authorize"})
        if url == AUTH + "/authorize":
            return response(f"window.atob('{encoded}')", url=AUTH + "/login")
        if url == AUTH + "/login/callback":
            service._s.cookies.set("session", "new-session", domain="place.sanoma.it", secure=True)
        if url.endswith("__data.json"):
            return response(library())
        return response("")

    service._s.request = Mock(side_effect=request)
    service._s.post = Mock(return_value=response(
        '<form action="/login/callback"><input name="wa" value="a">'
        '<input name="wresult" value="r"><input name="wctx" value="c"></form>'))
    service.login("test@example.invalid", "test-password")
    cookies = json.loads(service.token)
    assert len(cookies) == 1 and cookies[0]["value"] == "new-session"
    payload = service._s.post.call_args.kwargs["json"]
    assert payload["state"] == "state" and payload["_csrf"] == "csrf"
    assert payload["connection"] == "Sanoma-Italy-Database"


def test_login_wrong_password_leaves_no_session(service):
    config = {"internalOptions": {}, "clientID": "client", "auth0Tenant": "sanoma-italy"}
    encoded = base64.b64encode(json.dumps(config).encode()).decode()
    service._s.request = Mock(side_effect=[response(""), response({"location": AUTH + "/authorize"}),
                                         response(f"window.atob('{encoded}')")])
    service._s.post = Mock(return_value=response({"error": "invalid_user_password"}, status=401))
    with pytest.raises(ServiceAuthError, match="password Sanoma non validi"):
        service.login("test@example.invalid", "wrong")
    assert service.token is None


@pytest.mark.parametrize("payload", [{"type": "redirect", "location": "/login"}, "not-json"])
def test_invalid_or_expired_library_is_not_reported_as_empty(service, payload):
    service._s.request = Mock(return_value=response(payload))
    with pytest.raises(ServiceAuthError):
        service.list_books()


def test_authentication_does_not_send_credentials_to_another_host(service):
    service._s.request = Mock(side_effect=[response(""), response({"location": "https://example.invalid/login"})])
    service._s.post = Mock()
    with pytest.raises(ServiceAuthError):
        service.login("test@example.invalid", "test-password")
    service._s.post.assert_not_called()
    with pytest.raises(ServiceAuthError):
        _auth_url("http://place.sanoma.it/login")


def test_connection_failure_has_readable_error(service):
    service._s.request = Mock(side_effect=requests.ConnectionError("offline"))
    with pytest.raises(ServiceAuthError, match="connessione"):
        service.list_books()


def download_responses(service, fail_page=False):
    base = "https://cdn.sanoma.it/book"
    cookie_names = ("CloudFront-Policy", "CloudFront-Signature", "CloudFront-Key-Pair-Id")
    with fitz.open() as image:
        p = image.new_page(width=10, height=10)
        p.draw_rect(p.rect, color=(1, 0, 0), fill=(1, 0, 0))
        png = p.get_pixmap().tobytes("png")

    def request(method, url, **kwargs):
        if url.endswith("__data.json"):
            return response(library())
        if "/libromedia/" in url:
            return response("", status=302, headers={"Location": "https://ebook.sanoma.it/?ktoken=book-token"})
        if url == DISPLAY_BOOKS:
            assert kwargs["headers"]["X-Auth-Token"] == "book-token"
            return response({"data": [{"gedi": "12345", "book": {
                "url": base, "cookies": {key: "signed" for key in cookie_names}}}]})
        if url.endswith("master.json"):
            return response({"pages": [{"number": 2}, {"number": 1}]})
        if url.endswith(".svg"):
            if fail_page and url.endswith("/1.svg"):
                return response("missing", status=404)
            width = 200 if url.endswith("/2.svg") else 100
            return response(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="300">'
                            '<defs><path id="ink" d="M5 5H50V50H5Z"/></defs>'
                            '<g><use xlink:href="#ink"/><image xlink:href="image.png" width="100" height="100"/></g></svg>')
        if url.endswith("image.png"):
            result = response("")
            result._content = png
            return result
        raise AssertionError(url)

    service._s.request = Mock(side_effect=request)


def test_download_preserves_page_order_and_embeds_images(service, tmp_path):
    download_responses(service)
    progress = []
    target = service.download("12345", tmp_path, progress.append)
    with fitz.open(target) as pdf:
        assert [p.rect.width for p in pdf] == [200, 100]
        assert all(len(page.get_images()) == 1 for page in pdf)
        assert all(page.get_drawings() for page in pdf)
        assert pdf.metadata["title"] == "Corso - Volume 1"
    assert progress == [0.475, 0.95, 1.0]
    assert service._s.cookies.get("CloudFront-Policy", domain="cdn.sanoma.it", path="/book/") == "signed"


def test_failed_download_keeps_existing_pdf(service, tmp_path):
    download_responses(service, fail_page=True)
    target = tmp_path / "sanoma-12345-Corso - Volume 1.pdf"
    target.write_bytes(b"previous download")
    with pytest.raises(ServiceAuthError):
        service.download("12345", tmp_path)
    assert target.read_bytes() == b"previous download"
    assert list(tmp_path.iterdir()) == [target]
