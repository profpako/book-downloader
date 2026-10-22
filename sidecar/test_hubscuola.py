"""Download HUB: l'indice può mescolare capitoli e riferimenti numerici."""
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).parent))
from services.base import ServiceAuthError
from services.others import HubscuolaService


def _zip(name, data):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(name, data)
    return buf.getvalue()


class HubscuolaDownloadTests(unittest.TestCase):
    def _service(self, tmp, chapters):
        dbpath = tmp / "publication.db"
        with sqlite3.connect(dbpath) as db:
            db.execute("CREATE TABLE offline_tbl (offline_path TEXT, offline_value TEXT)")
            db.execute("INSERT INTO offline_tbl VALUES (?, ?)", (
                "meyoung/publication/book", json.dumps({"indexContents": {"chapters": chapters}})))
        publication = _zip("publication/publication.db", dbpath.read_bytes())
        chapter_zips = {}
        for cid, width in ((20, 200), (10, 100)):
            pdf = PdfWriter()
            pdf.add_blank_page(width, 300)
            buf = io.BytesIO()
            pdf.write(buf)
            chapter_zips[f"https://ms-mms.hubscuola.it/public/book/{cid}.zip"] = _zip(
                f"{cid}/page.pdf", buf.getvalue())

        def get(url, **kwargs):
            if url.endswith("/publication.zip"):
                return SimpleNamespace(status_code=200, content=publication)
            return SimpleNamespace(status_code=200, content=chapter_zips[url])

        service = HubscuolaService()
        service.token = "test-token"
        service._s.get = Mock(side_effect=get)
        return service

    def test_chapters_and_numeric_references(self):
        for chapters in (
            [{"chapterId": 20}, {"chapterId": 10}],
            [7892150, {"chapterId": 20}, 7892153, {"chapterId": 10}, 7892150],
        ):
            with self.subTest(chapters=chapters), tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                service = self._service(tmp, chapters)
                progress = []
                result = service.download("book", tmp, progress.append)
                self.assertEqual([int(p.mediabox.width) for p in PdfReader(result).pages], [200, 100])
                self.assertEqual(progress, [0.475, 0.95, 1.0])
                self.assertEqual(service._s.get.call_count, 3)

    def test_only_numeric_references_has_no_chapters(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            service = self._service(tmp, [7892150])
            with self.assertRaisesRegex(ServiceAuthError, "Nessun capitolo"):
                service.download("book", tmp)
            self.assertFalse((tmp / "hubscuola-book.pdf").exists())


if __name__ == "__main__":
    unittest.main()
