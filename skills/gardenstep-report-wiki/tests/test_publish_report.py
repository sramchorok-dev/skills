import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "publish_report.py"
SPEC = importlib.util.spec_from_file_location("publish_report", MODULE_PATH)
publish_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(publish_report)


class PublishReportTest(unittest.TestCase):
    def html(self, directory: Path, name: str = "report.html") -> Path:
        path = directory / name
        path.write_text(
            "<!doctype html><html><head><title>현재 구현</title>"
            '<meta name="description" content="한 줄 설명"></head>'
            "<body><h1>대체 제목</h1></body></html>",
            encoding="utf-8",
        )
        return path

    def test_same_path_replaces_registry_entry(self):
        entry = {"id": "one", "path": "reports/chorok/a.html", "title": "new"}
        existing = [
            {"id": "one", "path": "reports/chorok/a.html", "title": "old"},
            {"id": "two", "path": "reports/chorok/b.html", "title": "keep"},
        ]
        merged = publish_report.merge_entry(existing, entry)
        self.assertEqual(["one", "two"], [item["id"] for item in merged])
        self.assertEqual("new", merged[0]["title"])

    def test_public_acknowledgement_is_required(self):
        with tempfile.TemporaryDirectory() as raw:
            source = self.html(Path(raw))
            with self.assertRaisesRegex(publish_report.PublishError, "ack-public"):
                publish_report.validate_source(source, "chorok", "2026-09-13", False)

    def test_private_key_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            source = self.html(Path(raw))
            source.write_text("<html>-----BEGIN PRIVATE KEY-----</html>", encoding="utf-8")
            with self.assertRaisesRegex(publish_report.PublishError, "secret"):
                publish_report.validate_source(source, "chorok", "2026-09-13", True)

    def test_github_token_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            source = self.html(Path(raw))
            source.write_text(
                "<html><body>ghp_abcdefghijklmnopqrstuvwxyz123456</body></html>",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(publish_report.PublishError, "secret"):
                publish_report.validate_source(source, "chorok", "2026-09-13", True)

    def test_cross_project_publish_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            source = self.html(Path(raw))
            with self.assertRaisesRegex(publish_report.PublishError, "only the chorok"):
                publish_report.validate_source(source, "atomerce", "2026-09-13", True)

    def test_entry_path_and_id_are_stable(self):
        with tempfile.TemporaryDirectory() as raw:
            source = self.html(Path(raw), "현재 구현 스펙.html")
            first = publish_report.make_entry(
                source=source, project="chorok", title="A", desc="", tags=[], date="2026-09-13"
            )
            second = publish_report.make_entry(
                source=source, project="chorok", title="B", desc="new", tags=["x"], date="2026-09-13"
            )
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(first["path"], second["path"])
            self.assertTrue(first["path"].endswith("현재-구현-스펙.html"))

    def test_metadata_is_inferred_from_html(self):
        with tempfile.TemporaryDirectory() as raw:
            source = self.html(Path(raw))
            self.assertEqual(("현재 구현", "한 줄 설명"), publish_report.infer_metadata(source))

    def test_svg_titles_do_not_extend_document_title(self):
        with tempfile.TemporaryDirectory() as raw:
            source = self.html(Path(raw))
            source.write_text(
                "<html><head><title>문서 제목</title></head><body>"
                "<svg><title>다이어그램 제목</title></svg></body></html>",
                encoding="utf-8",
            )
            self.assertEqual(("문서 제목", ""), publish_report.infer_metadata(source))

    def test_tags_are_trimmed_deduplicated_and_bounded(self):
        self.assertEqual(["챗봇", "구매"], publish_report.normalize_tags(" 챗봇,구매,챗봇 "))
        with self.assertRaisesRegex(publish_report.PublishError, "at most 10"):
            publish_report.normalize_tags(",".join(f"tag-{index}" for index in range(11)))


if __name__ == "__main__":
    unittest.main()
