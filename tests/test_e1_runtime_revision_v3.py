import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class E1RuntimeRevisionV3Tests(unittest.TestCase):
    def test_v3_changes_only_timeout_and_declared_output_from_v2(self) -> None:
        v2 = json.loads((ROOT / "configs" / "E1_devtemp_v2.json").read_text(encoding="utf-8"))
        v3 = json.loads((ROOT / "configs" / "E1_devtemp_v3.json").read_text(encoding="utf-8"))
        self.assertEqual(v3["generator"]["timeout_seconds"], 420)
        self.assertEqual(v2["generator"]["timeout_seconds"], 300)
        v2["generator"]["timeout_seconds"] = v3["generator"]["timeout_seconds"]
        v2["experiment"]["output"] = v3["experiment"]["output"]
        self.assertEqual(v2, v3)

    def test_v3_preflight_is_single_nonformal_long_c2_task(self) -> None:
        revision = json.loads(
            (ROOT / "configs" / "E1_runtime_revision_v3_20260901.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(revision["formal_evidence"])
        self.assertEqual(revision["preflight_gate"]["run_order"], 21)
        self.assertEqual(revision["preflight_gate"]["run_key"], "formal_exp_0171:C2:2")
        self.assertEqual(revision["candidate_runtime"]["timeout_seconds"], 420)

    def test_formal_v3_runtime_lock_references_the_qualified_candidate(self) -> None:
        lock = json.loads(
            (ROOT / "configs" / "E1_formal_runtime_lock_v3_20260901.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lock["status"], "locked_ready_for_new_formal_B01_003")
        self.assertEqual(lock["runtime_revision"]["request_timeout_seconds"], 420)
        self.assertEqual(lock["new_formal_batch"]["run_order_start"], 1)
        self.assertEqual(lock["new_formal_batch"]["run_order_end"], 63)
        self.assertFalse(lock["new_formal_batch"]["overwrite_allowed"])

    def test_b01_result_is_complete_and_has_valid_external_meter_rows(self) -> None:
        result = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B01_003_result_v1.0.json").read_text(
                encoding="utf-8"
            )
        )
        runs = [
            json.loads(line)
            for line in (ROOT / result["energy_integration"]["merged_output"])
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        self.assertTrue(result["formal_evidence"])
        self.assertEqual(result["runner"]["successful"], 63)
        self.assertEqual(result["energy_integration"]["valid_count"], 63)
        self.assertEqual(len(runs), 63)
        self.assertTrue(all(row["status"] == "ok" for row in runs))
        self.assertTrue(
            all((row.get("telemetry") or {}).get("external_meter_valid") for row in runs)
        )

    def test_b02_lock_is_contiguous_and_does_not_overlap_b01(self) -> None:
        lock = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B02_lock_v3_20260902.json").read_text(
                encoding="utf-8"
            )
        )
        design = lock["design"]
        self.assertEqual(design["previous_batch_range"], [1, 63])
        self.assertEqual(design["global_run_order_start"], 64)
        self.assertEqual(design["global_run_order_end"], 126)
        self.assertEqual(design["expected_run_count"], 63)
        self.assertFalse(lock["artifacts"]["overwrite_allowed"])

    def test_b02_result_is_complete_and_b03_lock_is_contiguous(self) -> None:
        result = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B02_001_result_v1.0.json").read_text(
                encoding="utf-8"
            )
        )
        merged = [
            json.loads(line)
            for line in (ROOT / result["energy_integration"]["merged_output"])
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        b03 = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B03_lock_v3_20260902.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(result["formal_evidence"])
        self.assertEqual(result["run_order"], {"start": 64, "end": 126, "count": 63})
        self.assertEqual(result["energy_integration"]["valid_count"], 63)
        self.assertEqual(len(merged), 63)
        self.assertTrue(
            all((row.get("telemetry") or {}).get("external_meter_valid") for row in merged)
        )
        self.assertEqual(b03["design"]["previous_batch_range"], [64, 126])
        self.assertEqual(b03["design"]["global_run_order_start"], 127)
        self.assertEqual(b03["design"]["global_run_order_end"], 189)
        self.assertFalse(b03["artifacts"]["overwrite_allowed"])

    def test_b03_result_is_complete_and_b04_requires_remote_sync_preflight(self) -> None:
        result = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B03_001_result_v1.0.json").read_text(
                encoding="utf-8"
            )
        )
        merged = [
            json.loads(line)
            for line in (ROOT / result["energy_integration"]["merged_output"])
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        b04 = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B04_lock_v3_20260902.json").read_text(
                encoding="utf-8"
            )
        )
        deviation = result["release_control_deviation"]
        self.assertTrue(result["formal_evidence"])
        self.assertEqual(result["run_order"], {"start": 127, "end": 189, "count": 63})
        self.assertEqual(result["energy_integration"]["valid_count"], 63)
        self.assertTrue(all((row.get("telemetry") or {}).get("external_meter_valid") for row in merged))
        self.assertEqual(deviation["time_order_verified"], "local_lock_precedes_first_runner_start")
        self.assertEqual(b04["design"]["previous_batch_range"], [127, 189])
        self.assertEqual(b04["design"]["global_run_order_start"], 190)
        self.assertIn("git pull --ff-only succeeds", b04["preflight"]["mandatory_before_start"])

    def test_b04_result_is_complete_and_b05_requires_clean_remote_preflight(self) -> None:
        result = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B04_001_result_v1.0.json").read_text(
                encoding="utf-8"
            )
        )
        merged = [
            json.loads(line)
            for line in (ROOT / result["energy_integration"]["merged_output"])
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        b05 = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B05_lock_v3_20260902.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(result["formal_evidence"])
        self.assertEqual(result["run_order"], {"start": 190, "end": 252, "count": 63})
        self.assertEqual(result["energy_integration"]["valid_count"], 63)
        self.assertEqual(len(merged), 63)
        self.assertTrue(all((row.get("telemetry") or {}).get("external_meter_valid") for row in merged))
        self.assertEqual(result["release_control_deviation"]["id"], "ANOM-E1-20260902-005")
        self.assertEqual(b05["design"]["previous_batch_range"], [190, 252])
        self.assertEqual(b05["design"]["global_run_order_start"], 253)
        self.assertEqual(b05["design"]["global_run_order_end"], 315)
        self.assertIn("git status --porcelain is empty", b05["preflight"]["mandatory_before_start"])

    def test_b05_attempt001_is_rejected_and_recovery_preflight_is_nonformal(self) -> None:
        diagnostic = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B05_attempt001_diagnostic_v1.0.json").read_text(
                encoding="utf-8"
            )
        )
        preflight = json.loads(
            (ROOT / "configs" / "E1_serial_collector_recovery_preflight_v1_20260902.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(diagnostic["formal_attempt"])
        self.assertFalse(diagnostic["formal_evidence"])
        self.assertEqual(diagnostic["status"], "rejected_serial_corruption")
        self.assertEqual(diagnostic["runner"]["successful"], 63)
        self.assertEqual(diagnostic["collector_raw_outside_git"]["invalid_serial"], 26)
        self.assertEqual(diagnostic["serial_corruption_analysis"]["missing_sequence_samples"], 113)
        self.assertEqual(diagnostic["serial_corruption_analysis"]["affected_run_key"], "formal_exp_0172:C2:1")
        self.assertFalse(preflight["formal_evidence"])
        self.assertEqual(preflight["two_stage_protocol"]["stage_2_duration_seconds"], 1800)
        self.assertIn(
            "collector_session serial_buffer_configuration.status is configured",
            preflight["acceptance"],
        )

    def test_recovery_preflight_passes_and_locks_new_full_b05_attempt(self) -> None:
        result = json.loads(
            (ROOT / "configs" / "E1_serial_collector_recovery_preflight_001_result_v1.0.json").read_text(
                encoding="utf-8"
            )
        )
        lock = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B05_attempt002_lock_v3_20260902.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(result["formal_evidence"])
        self.assertTrue(result["acceptance"]["passed"])
        self.assertEqual(result["collector_raw_outside_git"]["invalid_serial"], 0)
        self.assertEqual(result["device_clock_quality"]["missing_sequence_samples"], 0)
        self.assertLessEqual(result["device_clock_quality"]["maximum_device_gap_ms"], 30.0)
        self.assertEqual(lock["artifacts"]["session_id"], "E1-DEVTEMP-FORMAL-B05-002")
        self.assertEqual(lock["design"]["global_run_order_start"], 253)
        self.assertEqual(lock["design"]["global_run_order_end"], 315)
        self.assertFalse(lock["artifacts"]["overwrite_allowed"])

    def test_b05_attempt002_is_rejected_and_attempt003_requires_server_preflight(self) -> None:
        diagnostic = json.loads(
            (
                ROOT
                / "configs"
                / "E1_formal_batch_B05_attempt002_diagnostic_v1.0.json"
            ).read_text(encoding="utf-8")
        )
        lock = json.loads(
            (
                ROOT
                / "configs"
                / "E1_formal_batch_B05_attempt003_lock_v3_20260903.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(diagnostic["formal_attempt"])
        self.assertFalse(diagnostic["formal_evidence"])
        self.assertEqual(diagnostic["status"], "rejected_llama_server_not_running")
        self.assertEqual(diagnostic["runner"]["rows"], 63)
        self.assertEqual(diagnostic["runner"]["successful"], 0)
        self.assertEqual(diagnostic["runner"]["failed"], 63)
        self.assertEqual(diagnostic["server_preflight"]["health"], "connection_refused_http_000")
        self.assertEqual(lock["artifacts"]["session_id"], "E1-DEVTEMP-FORMAL-B05-003")
        self.assertEqual(lock["design"]["global_run_order_start"], 253)
        self.assertEqual(lock["design"]["global_run_order_end"], 315)
        self.assertIn(
            "verify the exact server PID, HTTP 200 health response, and no-cache startup-log lines",
            lock["mandatory_execution_order"],
        )

    def test_b05_attempt003_is_rejected_for_observed_undervoltage(self) -> None:
        diagnostic = json.loads(
            (
                ROOT
                / "configs"
                / "E1_formal_batch_B05_attempt003_diagnostic_v1.0.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(diagnostic["formal_attempt"])
        self.assertFalse(diagnostic["formal_evidence"])
        self.assertEqual(diagnostic["status"], "rejected_power_chain_undervoltage")
        self.assertEqual(diagnostic["runner"]["successful"], 63)
        self.assertEqual(diagnostic["physical_energy_integration"]["valid_count"], 0)
        self.assertEqual(diagnostic["power_quality"]["undervoltage_sample_count"], 737200)
        self.assertLess(
            diagnostic["power_quality"]["bus_v_max"],
            diagnostic["power_quality"]["firmware_undervoltage_threshold_v"],
        )

    def test_power_recheck_passes_before_new_complete_b05_attempt004(self) -> None:
        result = json.loads(
            (ROOT / "configs" / "E1_power_recheck_preflight_001_result_v1.0.json").read_text(
                encoding="utf-8"
            )
        )
        lock = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B05_attempt004_lock_v3_20260903.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(result["formal_evidence"])
        self.assertTrue(result["acceptance"]["passed"])
        self.assertEqual(result["load_power_check"]["runner"]["successful"], 9)
        self.assertEqual(result["load_power_check"]["runner"]["failed"], 0)
        self.assertEqual(result["load_power_check"]["undervoltage_samples"], 0)
        self.assertGreaterEqual(result["load_power_check"]["bus_v"]["min"], 4.75)
        self.assertEqual(lock["artifacts"]["session_id"], "E1-DEVTEMP-FORMAL-B05-004")
        self.assertEqual(lock["design"]["global_run_order_start"], 253)
        self.assertEqual(lock["design"]["global_run_order_end"], 315)
        self.assertFalse(lock["artifacts"]["overwrite_allowed"])


if __name__ == "__main__":
    unittest.main()
