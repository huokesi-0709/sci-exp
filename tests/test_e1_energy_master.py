import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class E1EnergyMasterTests(unittest.TestCase):
    def test_master_has_exact_frozen_manifest_coverage_and_valid_physical_energy(self):
        manifest_path = ROOT / "configs/E1_devtemp_formal_run_manifest_seed42_v1.0.jsonl"
        master_path = ROOT / "results/E1_devtemp_formal_v3_energy_master_v1.0.jsonl"
        audit_path = ROOT / "results/E1_devtemp_formal_v3_energy_master_v1.0.audit.json"
        manifest = read_jsonl(manifest_path)
        master = read_jsonl(master_path)
        audit = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertEqual(len(manifest), 315)
        self.assertEqual(len(master), 315)
        self.assertEqual(
            [row["run_key"] for row in master],
            [row["run_key"] for row in manifest],
        )
        self.assertTrue(all(row["status"] == "ok" for row in master))
        self.assertTrue(
            all((row.get("telemetry") or {}).get("external_meter_valid") is True for row in master)
        )
        self.assertEqual(Counter(row["configuration"] for row in master), {"C0": 105, "C1": 105, "C2": 105})
        self.assertEqual(audit["validation"]["external_meter_valid_count"], 315)
        self.assertEqual(
            audit["output"]["sha256"],
            hashlib.sha256(master_path.read_bytes()).hexdigest().upper(),
        )

    def test_execution_registry_keeps_roles_anonymous_and_unverified(self):
        registry = json.loads(
            (ROOT / "configs/E1_blind_review_execution_registry_v1.0.json").read_text(
                encoding="utf-8"
            )
        )
        roles = registry["roles"]
        self.assertEqual(roles["reviewer_A"]["anonymous_id"], "ANN-A")
        self.assertEqual(roles["reviewer_B"]["anonymous_id"], "ANN-B")
        self.assertEqual(roles["adjudication_body_C"]["anonymous_id"], "ANN-C-ORG")
        self.assertFalse(registry["identity_and_credential_boundary"]["external_credential_verification_performed_by_project"])


if __name__ == "__main__":
    unittest.main()
