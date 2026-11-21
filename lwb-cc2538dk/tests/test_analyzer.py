import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("analyzer", Path(__file__).resolve().parents[1] / "tools/analyze_logs.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def config(node=1, role="HOST", run=7, sources="3", expected=10):
    return {"tag": "PERF_CONFIG", "run": str(run), "node": str(node), "role": role,
            "source_ids": sources, "expected": str(expected), "protocol": "env_perf_v1"}


def rx(seq, **kw):
    d = {"tag": "SENSOR_DATA", "run": "7", "node": "3", "from": "3", "seq": str(seq),
         "unique": "1", "delay_valid": "1", "delay_ticks": str(seq * 32), "timer_hz": "32768",
         "tx_net_ticks": "4294967280", "rx_slot_end_ticks": str((0xfffffff0 + seq * 32) & 0xffffffff),
         "hop_est_valid": "1", "relay_cnt": "2", "hop_est": "3"}
    d.update({k: str(v) for k, v in kw.items()})
    return d


def report(tag="PERF_REPORT", **kw):
    d = {"tag": tag, "run": "7", "source": "3", "generated": "10", "queued": "10",
         "tx_started": "10", "queue_failed": "0", "deadline_missed": "0",
         "tx_start_failed": "0", "discarded": "0", "drain_timeout": "0"}
    d.update({k: str(v) for k, v in kw.items()})
    return d


class AnalyzerTests(unittest.TestCase):
    def test_tail_loss_and_p95(self):
        r = m.analyze([config()] + [rx(s) for s in range(1, 10)] + [report()])[0]
        self.assertEqual(r["flood_delivery_pct"], 90)
        self.assertEqual(r["delay_count"], 9)
        self.assertEqual(r["delay_p95_ms"], 9 * 32 * 1000 / 32768)
        self.assertIsNone(r["multihop_proven"])

    def test_unknown_denominator(self):
        r = m.analyze([config(), rx(9)])[0]
        self.assertEqual(r["status"], "incomplete")
        self.assertIsNone(r["flood_delivery_pct"])

    def test_report_lost_source_uart_fallback(self):
        host = [config(), rx(1)]
        source = [config(3, "SOURCE"), report("PERF_SOURCE_SUMMARY")]
        r = m.analyze(host, source, coverage_confirmed=True)[0]
        self.assertEqual(r["status"], "final")
        self.assertEqual(r["flood_delivery_pct"], 10)
        self.assertEqual(r["denominator_origin"], "source_uart")
        r = m.analyze(host, source)[0]
        self.assertIsNone(r["flood_delivery_pct"])
        self.assertIn("host_end_coverage_unverified", r["issues"])

    def test_zero_reception_source_retained(self):
        rs = m.analyze([config(sources="2:3"), report()])
        self.assertEqual(len(rs), 2)
        self.assertEqual(rs[0]["source"], 2)
        self.assertEqual(rs[0]["received_unique"], 0)

    def test_duplicates_and_reordering(self):
        r = m.analyze([config(), rx(2), rx(1), rx(2, unique=0), report()])[0]
        self.assertEqual((r["received_unique"], r["duplicates"], r["out_of_order"]), (2, 1, 1))
        self.assertEqual(r["delay_count"], 2)

    def test_queue_loss_and_skip_separate_from_rf(self):
        r = m.analyze([config(), rx(1), report(queued=8, tx_started=6,
                      queue_failed=1, deadline_missed=1, tx_start_failed=1)])[0]
        self.assertEqual(r["application_yield_pct"], 10)
        self.assertEqual(r["enqueue_delivery_pct"], 12.5)
        self.assertAlmostEqual(r["flood_delivery_pct"], 100 / 6, places=5)

    def test_superseded_queue_entries_are_accounted(self):
        # FRESH_ONLY firmware: 2 stale entries were replaced by newer packets.
        counts = dict(queued=10, tx_started=8)
        host = [config(), rx(1), report(**counts)]
        source = [config(3, "SOURCE"), report("PERF_SOURCE_SUMMARY", superseded=2, **counts)]
        r = m.analyze(host, source)[0]
        self.assertEqual(r["status"], "final")
        self.assertNotIn("unaccounted_source_queue_entries", r["issues"])
        # Without the superseded field the same numbers do not add up.
        source = [config(3, "SOURCE"), report("PERF_SOURCE_SUMMARY", **counts)]
        r = m.analyze(host, source)[0]
        self.assertIn("unaccounted_source_queue_entries", r["issues"])

    def test_reboot_and_count_conflicts_rejected(self):
        r = m.analyze([config(), config(), rx(1), report()])[0]
        self.assertEqual(r["status"], "invalid")
        self.assertIsNone(r["flood_delivery_pct"])
        r = m.analyze([config(), rx(1), report(tx_started=0)])[0]
        self.assertEqual(r["status"], "invalid")

    def test_missing_host_data_log_detected(self):
        summary = {"tag": "PERF_SUMMARY", "run": "7", "source": "3", "received": "2"}
        r = m.analyze([config(), rx(1), report(), summary])[0]
        self.assertIn("host_log_missing_data_lines", r["issues"])

    def test_unsynchronized_delays_excluded(self):
        r = m.analyze([config(), rx(1, delay_valid=0), report()])[0]
        self.assertEqual(r["received_unique"], 1)
        self.assertEqual(r["delay_count"], 0)

    def test_join_failure(self):
        abort = {"tag": "PERF_ABORT", "run": "7", "source": "3", "reason": "join_timeout"}
        r = m.analyze([config()], [abort])[0]
        self.assertEqual(r["status"], "join_failed")
        self.assertEqual(r["planned_receipt_pct"], 0)
        self.assertIsNone(r["flood_delivery_pct"])

    def test_parse_timestamp_prefix_and_malformed(self):
        events = list(m.parse_lines(["12:00:00 PERF_TX,run,7,source,3,seq,1\r\n"]))
        self.assertEqual(events[0]["seq"], "1")
        with self.assertRaises(ValueError):
            list(m.parse_lines(["PERF_REPORT,run,7,broken"]))


if __name__ == "__main__":
    unittest.main()
