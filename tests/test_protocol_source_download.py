import hashlib
import csv
import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "下载权威协议源.py"
REGISTRY_PATH = (
    PROJECT_ROOT / "data" / "raw" / "protocols" / "协议来源登记_v0.1.jsonl"
)
CANDIDATE_CHUNKS = PROJECT_ROOT / "data" / "processed" / "候选协议切块_v0.1.jsonl"
LICENSE_AUDIT = (
    PROJECT_ROOT / "data" / "annotations" / "许可与版本核验表_v0.1.csv"
)
SPEC = spec_from_file_location("protocol_source_download", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProtocolSourceDownloadTests(unittest.TestCase):
    def test_candidate_protocols_cannot_be_used_as_formal_knowledge_base(
        self,
    ) -> None:
        registry = [
            MODULE.json.loads(line)
            for line in REGISTRY_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        chunks = [
            MODULE.json.loads(line)
            for line in CANDIDATE_CHUNKS.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(15, len(registry))
        self.assertTrue(all(row["file_sha256"] for row in registry))
        self.assertTrue(chunks)
        self.assertTrue(all(row["status"] == "draft" for row in chunks))
        self.assertTrue(all(row["content_review_status"] == "pending" for row in chunks))
        self.assertTrue(
            all(row["license_status"] == "pending_manual_confirmation" for row in chunks)
        )
        self.assertTrue(all(row["source_id"] for row in chunks))
        self.assertTrue(all(row["file_sha256"] for row in chunks))

    def test_html_extraction_removes_script_and_trims_markers(self) -> None:
        repeated_body = "这是需要保留的正式正文，包含公众避险行动。" * 20
        html = f"""
        <html><body><nav>导航噪声</nav><h1>正文开始</h1>
        <p>{repeated_body}</p>
        <script>危险脚本噪声</script>
        <p>第二段正文，包含公众避险行动。</p>
        <p>正文结束</p><footer>页脚噪声</footer></body></html>
        """.encode("utf-8")
        text = MODULE.extract_html_text(
            html,
            start_marker="正文开始",
            end_marker="正文结束",
        )
        self.assertIn("需要保留", text)
        self.assertIn("公众避险行动", text)
        self.assertNotIn("危险脚本", text)
        self.assertNotIn("导航噪声", text)
        self.assertNotIn("正文结束", text)

    def test_misdeclared_latin1_html_prefers_valid_utf8(self) -> None:
        repeated_body = "高层建筑火灾时不得乘坐普通电梯。" * 30
        html = (
            f"<html><body><h1>正文开始</h1><p>{repeated_body}</p></body></html>"
        ).encode("utf-8")
        text = MODULE.extract_html_text(
            html,
            content_type="text/html; charset=ISO-8859-1",
            start_marker="正文开始",
        )
        self.assertIn("不得乘坐普通电梯", text)
        self.assertNotIn("ä¸", text)

    def test_existing_file_is_verified_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "原始文件" / "existing.pdf"
            target.parent.mkdir(parents=True)
            content = b"%PDF-test-existing"
            target.write_bytes(content)
            result = MODULE.materialize_source(
                {
                    "source_id": "TEST",
                    "file": "原始文件/existing.pdf",
                    "source_url": "https://invalid.example/",
                    "retrieval_mode": "pdf",
                },
                registry_directory=root,
                timeout=1,
            )
            self.assertEqual("existing_verified", result["status"])
            self.assertEqual(hashlib.sha256(content).hexdigest(), result["sha256"])
            self.assertEqual(content, target.read_bytes())

    def test_license_audit_blocks_uncleared_redistribution(self) -> None:
        with LICENSE_AUDIT.open(
            "r", encoding="utf-8-sig", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(15, len(rows))
        self.assertEqual(
            {
                "WHO_ICRC_BEC_2018",
                "WHO_PFA_2011",
            },
            {
                row["source_id"]
                for row in rows
                if row["再分发决定"]
                == "conditional_noncommercial_attribution_sharealike"
            },
        )
        self.assertEqual(
            13,
            sum(
                row["再分发决定"]
                == "blocked_pending_manual_confirmation"
                for row in rows
            ),
        )

    def test_existing_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "原始文件" / "existing.pdf"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"%PDF-current")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                MODULE.materialize_source(
                    {
                        "source_id": "TEST",
                        "file": "原始文件/existing.pdf",
                        "file_sha256": hashlib.sha256(b"different").hexdigest(),
                        "source_url": "https://invalid.example/",
                        "retrieval_mode": "pdf",
                    },
                    registry_directory=root,
                    timeout=1,
                )


if __name__ == "__main__":
    unittest.main()
