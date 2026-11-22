"""Batch PDF printing must not crash when several files are open at once."""

from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

import pypdfium2 as pdfium

from justprint.app import App
from justprint.render import RenderError, inspect_pages, open_source, pdfium_lock


def _settings() -> dict:
    return {"paper": "a4", "orientation": "portrait", "color": "color", "image_dpi": 72}


def _write_pdf(folder: Path, name: str, pages: int = 1) -> str:
    document = pdfium.PdfDocument.new()
    try:
        for index in range(pages):
            page = document.new_page(595, 842)
            page.close()
        path = folder / name
        with path.open("wb") as handle:
            document.save(handle)
    finally:
        document.close()
    return str(path)


class MultiPdfTests(unittest.TestCase):
    def setUp(self) -> None:
        self._home = tempfile.TemporaryDirectory()
        os.environ["JUSTPRINT_HOME"] = self._home.name
        self._files = tempfile.TemporaryDirectory()
        self.folder = Path(self._files.name)

    def tearDown(self) -> None:
        self._files.cleanup()
        self._home.cleanup()

    def test_open_document_blocks_other_threads(self) -> None:
        path = _write_pdf(self.folder, "hold.pdf")
        source = open_source(path, _settings())

        def try_lock(timeout: float, sink: dict) -> None:
            sink["acquired"] = pdfium_lock.acquire(timeout=timeout)
            if sink["acquired"]:
                pdfium_lock.release()

        held: dict = {}
        waiter = threading.Thread(target=try_lock, args=(0.2, held))
        try:
            waiter.start()
            waiter.join()
            self.assertFalse(held["acquired"])
        finally:
            source.close()
        free: dict = {}
        follower = threading.Thread(target=try_lock, args=(1, free))
        follower.start()
        follower.join()
        self.assertTrue(free["acquired"])

    def test_failed_open_releases_the_lock(self) -> None:
        path = self.folder / "broken.pdf"
        path.write_bytes(b"this is not a pdf")
        with self.assertRaises(RenderError):
            open_source(str(path), _settings())
        self.assertTrue(pdfium_lock.acquire(timeout=1))
        pdfium_lock.release()

    def test_release_lets_the_next_file_render_then_resume(self) -> None:
        first = _write_pdf(self.folder, "first.pdf", pages=2)
        second = _write_pdf(self.folder, "second.pdf", pages=1)
        source = open_source(first, _settings())
        try:
            self.assertEqual(source.render(0, "preview").size[0] > 0, True)
            source.release_native()
            other = open_source(second, _settings())
            try:
                self.assertEqual(other.page_count, 1)
                self.assertGreater(other.render(0, "print").size[1], 0)
            finally:
                other.close()
            again = source.render(1, "print")
            self.assertGreater(again.size[0], 0)
        finally:
            source.close()
        source.close()

    def test_concurrent_reads_stay_alive(self) -> None:
        paths = [_write_pdf(self.folder, f"report_{index}.pdf", pages=2) for index in range(6)]
        errors: list[BaseException] = []
        barrier = threading.Barrier(len(paths))

        def read(path: str) -> None:
            try:
                barrier.wait(timeout=5)
                self.assertEqual(inspect_pages(path, _settings()), 2)
                source = open_source(path, _settings())
                try:
                    image = source.render(1, "print")
                    self.assertGreater(image.size[0], 0)
                    source.release_native()
                    image = source.render(0, "preview")
                    self.assertGreater(image.size[1], 0)
                finally:
                    source.close()
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=read, args=(path,)) for path in paths]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

    def test_practice_print_many_pdfs_while_preview_runs(self) -> None:
        paths = [_write_pdf(self.folder, f"wolt_{index:02d}.pdf", pages=2) for index in range(4)]
        app = App()
        app.update_settings(
            {
                "practice_run": True,
                "printer": "",
                "wait_for_empty_queue": True,
                "collate": False,
                "show_summary": True,
            }
        )
        added = app.add_paths(paths)
        self.assertEqual(added["added"], 4)
        deadline = time.time() + 10
        while time.time() < deadline:
            state = app.get_state()
            if all(doc["pages"] for doc in state["documents"]):
                break
            time.sleep(0.02)
        else:
            self.fail("files were not read")

        stop = threading.Event()
        preview_errors: list[BaseException] = []

        def preview() -> None:
            while not stop.is_set():
                state = app.get_state()
                for doc in state["documents"]:
                    if not doc["pages"]:
                        continue
                    try:
                        png = app.preview_png(doc["id"], 1)
                    except BaseException as exc:
                        preview_errors.append(exc)
                        return
                    if png is None:
                        preview_errors.append(AssertionError(f"no preview for {doc['name']}"))
                        return

        worker = threading.Thread(target=preview)
        worker.start()
        try:
            app.start_print()
            deadline = time.time() + 20
            while time.time() < deadline:
                if not app.get_state()["job"]["running"]:
                    break
                time.sleep(0.02)
            else:
                self.fail("print did not finish")
        finally:
            stop.set()
            worker.join(timeout=5)

        state = app.get_state()
        self.assertEqual(preview_errors, [])
        self.assertEqual(state["job"]["phase"], "done")
        self.assertEqual([doc["status"] for doc in state["documents"]], ["printed"] * 4)
        self.assertGreater(state["job"]["sheetsPrinted"], 0)


if __name__ == "__main__":
    unittest.main()
