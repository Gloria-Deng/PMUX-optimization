"""Focused checks for the official efficiency rules updated on 2026-11-03."""
from __future__ import annotations

from collections import Counter
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import measure_official_efficiency as efficiency


def readings_for(initial=None, repeated=None):
    initial, repeated = initial or {}, repeated or {}
    rows = []

    def add(case, category, version, stage, index, values=None):
        lut = 100 if version == "stock" else 80
        row = dict(sequence=len(rows) + 1, case=case, category=category, version=version,
                   stage=stage, index=index, exit=0, elapsed_s=0.2, cpu_s=1.0,
                   memory_mb=100.0, lut=lut, inv=0, logic=lut, dff=0, io_bits=20,
                   reference_logic_matches=True, output_stat_agrees=True, abc9=True,
                   classic_abc=False, meter_error=None, output=f"executions/item_{len(rows) + 1}")
        row.update(values or {})
        rows.append(row)
        return row

    first, _, category = next(item for item in efficiency.CASES if item[0] == efficiency.WARMUP_CASE)
    for index in range(1, 11):
        add(first, category, "stock", "warmup", index)
    for case, _, category in efficiency.CASES:
        pair = {version: add(case, category, version, "initial", 1, initial.get((case, version)))
                for version in ("stock", "delivered")}
        repeat, _ = efficiency.recheck_rule(pair["stock"], pair["delivered"])
        if repeat:
            for index in range(1, 6):
                for version in ("stock", "delivered"):
                    values = repeated.get((case, version), [{}] * 5)[index - 1]
                    add(case, category, version, "recheck", index, values)
    return rows


class OfficialEfficiencyTests(unittest.TestCase):
    def test_cpu_is_reference_only(self):
        rows = readings_for({("test1", "delivered"): {"cpu_s": 9.0}})
        summary = efficiency.summary_from_readings(rows)
        self.assertEqual(len(rows), 28)
        self.assertEqual(summary[0]["selected_count"], 1)
        self.assertEqual(summary[0]["trigger_metrics"], "")
        self.assertEqual(summary[0]["cpu_pct"], 800.0)
        self.assertEqual(efficiency.score_requirement_errors(summary, True)[0], [])

    def test_intermediate_case_repeats_and_excludes_initial(self):
        initial = {("test1", "stock"): {"elapsed_s": 2.0},
                   ("test1", "delivered"): {"elapsed_s": 2.2}}
        repeated = {("test1", "stock"): [{"elapsed_s": 4.0}] * 5,
                    ("test1", "delivered"): [{"elapsed_s": 4.04}] * 5}
        result = efficiency.summary_from_readings(readings_for(initial, repeated))[0]
        self.assertEqual(result["selected_count"], 5)
        self.assertEqual(result["selected_stage"], "recheck")
        self.assertAlmostEqual(result["elapsed_pct"], 1.0)
        self.assertEqual(result["elapsed_before"], 4.0)

    def test_ratio_uses_means_of_original_values(self):
        initial = {("test1", "delivered"): {"memory_mb": 110.0}}
        repeated = {("test1", "stock"): [{"elapsed_s": value} for value in (1, 2, 3, 4, 5)],
                    ("test1", "delivered"): [{"elapsed_s": value} for value in (1, 2, 3, 4, 6)]}
        result = efficiency.summary_from_readings(readings_for(initial, repeated))[0]
        self.assertAlmostEqual(result["elapsed_pct"], 100 * (3.2 / 3 - 1))
        self.assertEqual(result["trigger_metrics"], "memory_mb")

    def test_ten_seconds_is_initial_only(self):
        stock = dict(elapsed_s=9.0, cpu_s=1, memory_mb=100)
        delivered = dict(elapsed_s=10.0, cpu_s=1, memory_mb=120)
        self.assertEqual(efficiency.recheck_rule(stock, delivered), (False, "LONG_CASE_INITIAL_ONLY"))
        delivered["elapsed_s"] = 9.999
        self.assertTrue(efficiency.recheck_rule(stock, delivered)[0])

    def test_exact_five_percent_does_not_repeat(self):
        self.assertFalse(efficiency.recheck_rule(
            dict(elapsed_s=1, cpu_s=1, memory_mb=100),
            dict(elapsed_s=1.05, cpu_s=9, memory_mb=105))[0])

    def test_text_values_from_csv_are_supported(self):
        rows = [{key: "" if value is None else str(value) for key, value in row.items()}
                for row in readings_for()]
        self.assertEqual(len(efficiency.summary_from_readings(rows)), 9)

    def test_wrong_order_is_rejected(self):
        rows = readings_for()
        rows[10], rows[11] = rows[11], rows[10]
        with self.assertRaises(RuntimeError):
            efficiency.summary_from_readings(rows)

    def test_missing_recheck_is_rejected(self):
        rows = readings_for({("test1", "delivered"): {"elapsed_s": 0.23}})
        del rows[13]
        with self.assertRaises(RuntimeError):
            efficiency.summary_from_readings(rows)

    def test_extra_recheck_is_rejected(self):
        rows = readings_for()
        rows.append(copy.deepcopy(rows[-1]))
        with self.assertRaises(RuntimeError):
            efficiency.summary_from_readings(rows)

    def test_old_per_case_warmup_is_rejected(self):
        rows = readings_for()
        extra = copy.deepcopy(rows[0])
        extra.update(sequence=13, case="test2", stage="warmup", index=1)
        rows.insert(12, extra)
        with self.assertRaises(RuntimeError):
            efficiency.summary_from_readings(rows)

    def test_nested_stock_is_the_only_warmup(self):
        rows = readings_for()
        self.assertEqual({row["case"] for row in rows[:10]}, {"pmux_case05_nested"})
        self.assertEqual({row["version"] for row in rows[:10]}, {"stock"})
        for replacement in ({"case": "test1", "category": "original"}, {"version": "delivered"}):
            changed = copy.deepcopy(rows)
            changed[0].update(replacement)
            with self.assertRaises(RuntimeError):
                efficiency.summary_from_readings(changed)

    def test_all_five_rechecks_count_even_when_the_result_is_worse(self):
        initial = {("test1", "delivered"): {"memory_mb": 106.0}}
        repeated = {("test1", "delivered"): [{"memory_mb": value} for value in (101, 101, 101, 101, 140)]}
        rows = readings_for(initial, repeated)
        summary = efficiency.summary_from_readings(rows)
        self.assertEqual(len(rows), 38)
        self.assertAlmostEqual(summary[0]["memory_after"], 108.8)
        self.assertTrue(efficiency.score_requirement_errors(summary, True)[0])

    def test_invalid_readings_and_resource_changes_are_rejected(self):
        for key, value in (("elapsed_s", float("nan")), ("memory_mb", 0), ("exit", 1),
                           ("reference_logic_matches", False), ("classic_abc", True),
                           ("logic", 99), ("meter_error", "unavailable")):
            with self.subTest(key=key):
                rows = readings_for()
                rows[10][key] = value
                with self.assertRaises(RuntimeError):
                    efficiency.summary_from_readings(rows)
        rows = readings_for()
        nested_initial = next(row for row in rows if row["case"] == efficiency.WARMUP_CASE
                              and row["version"] == "stock" and row["stage"] == "initial")
        nested_initial.update(lut=99, logic=99)
        with self.assertRaises(RuntimeError):
            efficiency.summary_from_readings(rows)

    def test_reference_counts_are_checked(self):
        rows = readings_for()
        refs = {(case, version): {"lut": 100 if version == "stock" else 80, "not": 0, "dff": 0, "io_bits": 20}
                for case, _, _ in efficiency.CASES for version in ("stock", "delivered")}
        self.assertEqual(len(efficiency.summary_from_readings(rows, refs)), 9)
        refs["test1", "stock"]["dff"] = 1
        with self.assertRaises(RuntimeError):
            efficiency.summary_from_readings(rows, refs)

    def test_elapsed_and_memory_control_score(self):
        summary = efficiency.summary_from_readings(readings_for())
        summary[0]["elapsed_pct"] = 5.01
        self.assertTrue(efficiency.score_requirement_errors(summary, True)[0])
        self.assertEqual(efficiency.score_requirement_errors(summary, False)[0], [])
        summary[0]["memory_pct"] = 15.01
        self.assertTrue(efficiency.score_requirement_errors(summary, False)[0])

    def test_dff_and_io_twenty_percent_boundaries(self):
        for quantity in ("dff", "io_bits"):
            with self.subTest(quantity=quantity):
                summary = efficiency.summary_from_readings(readings_for())
                summary[0][quantity + "_before"] = 5
                summary[0][quantity + "_after"] = 6
                self.assertEqual(efficiency.score_requirement_errors(summary, True)[0], [])
                summary[0][quantity + "_after"] = 7
                self.assertTrue(efficiency.score_requirement_errors(summary, True)[0])
                summary[0][quantity + "_before"] = 0
                summary[0][quantity + "_after"] = 0
                self.assertEqual(efficiency.score_requirement_errors(summary, True)[0], [])
                summary[0][quantity + "_after"] = 1
                self.assertTrue(efficiency.score_requirement_errors(summary, True)[0])

    def test_execution_imports_saved_script(self):
        class FakeProcess:
            def __init__(self, *args, **kwargs):
                pass

            def communicate(self, *args, **kwargs):
                return "", ""

        seen = []

        def measured(command, cwd, **kwargs):
            seen.append(command)
            (Path(cwd) / "final.il").write_text("", encoding="utf-8")
            efficiency.subprocess.Popen().communicate()
            return 0, "Executing ABC9 pass", "", dict(cpu_tree_s=1.0, peak_main_working_set_mb=100.0)

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            refs = {("test1", "stock"): {"lut": 100, "not": 0, "dff": 0, "io_bits": 20}}
            with patch.object(efficiency.subprocess, "Popen", FakeProcess), \
                    patch.object(efficiency, "tree_cpu_run", measured), \
                    patch.object(efficiency, "top_counts", return_value=Counter({"\\cycloneiv_lcell_comb": 100})), \
                    patch.object(efficiency, "top_io_bits", return_value=20), \
                    patch.object(efficiency, "parse_stat", return_value={"cycloneiv_lcell_comb": 100}):
                result = efficiency.execute(directory, {"stock": Path("yosys.exe")}, refs, [],
                                            "test1", "original", directory / "test1.v", "stock", "initial", 1)
            self.assertEqual(seen[0][1:], ["-s", "synthesis.ys"])
            content = (directory / result["output"] / "measurement.txt").read_text(encoding="utf-8")
            self.assertIn("elapsed_s", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
