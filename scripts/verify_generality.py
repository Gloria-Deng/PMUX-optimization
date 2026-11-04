"""Check priority wiring, comparison polarity and shallow arithmetic sharing."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import re
import subprocess
import sys

from evaluate_official_nine import ROOT, env, identity, prepared_runtime, save_csv
from validation_support import config, quote
import run_eqy as eqy


CASES = [
    ("decode_narrow", "decode_counterexample", "-decode-share", None, True),
    ("decode_wide", "decode_wide_counterexample", "", None, True),
    ("decode_disabled", "decode_wide_counterexample", "-no-decode-share", None, False),
    ("shallow_w6", "shallow_w6", "", True, None),
    ("shallow_w17_signed", "shallow_w17_signed", "", True, None),
    ("shallow_w5", "shallow_w5", "", False, None),
    ("shallow_constants", "shallow_constants", "", True, None),
    ("shallow_external", "shallow_external", "", False, None),
    ("shallow_priority", "shallow_priority", "", True, None),
]


def public_behavior_config(source, netlist, top, directory):
    # Unselected arithmetic branches may change internally after sharing.
    # Keep every real port, but do not match temporary values by their names.
    return config(source, netlist, top, directory).replace("\nprep -top ", "\nrename -hide\nprep -top ")


def check_changed_output(source, directory, top):
    body = (directory / "after.il").read_text(encoding="utf-8")
    module = re.search(r"^module \\" + re.escape(top) + r"\n(.*?)^end$", body, re.M | re.S)
    if module is None:
        raise RuntimeError("The output control needs the original top module")
    output = re.search(r"^  wire(?: width (\d+))? output (\d+) (\\data_out)$", module[1], re.M)
    if output is None:
        raise RuntimeError("The output control needs the real data_out port")
    width, port, name = int(output[1] or 1), output[2], output[3]
    internal = "\\generality_original_output"
    altered = re.sub(re.escape(name) + r"(?=\s|$)", lambda _: internal, module[1])
    altered = altered.replace(f" output {port} {internal}", f" {internal}", 1)
    altered += (f"  wire width {width} output {port} {name}\n"
                "  cell $not \\generality_changed_output\n"
                f"    parameter \\A_SIGNED 0\n    parameter \\A_WIDTH {width}\n"
                f"    parameter \\Y_WIDTH {width}\n    connect \\A {internal}\n"
                f"    connect \\Y {name}\n  end\n")
    changed = directory / "changed_output.il"
    changed.write_text(body[:module.start(1)] + altered + body[module.end(1):], encoding="utf-8")
    (directory / "changed_output.eqy").write_text(public_behavior_config(source, changed, top, directory), encoding="utf-8")
    code, proof = eqy.run(["-d", "changed_output", "changed_output.eqy"], directory, timeout=180)
    verdict, reason = eqy.verdict_of(code, proof)
    (directory / "changed_output.txt").write_text(proof, encoding="utf-8")
    (directory.parent / "control.txt").write_text(f"changed_real_output=True\nexit={code}\nverdict={verdict}\n{reason}\n", encoding="utf-8")
    if code != 2 or verdict == "PROVEN" or "partitions not equivalent" not in proof:
        raise RuntimeError("The deliberately inverted real output was not rejected")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    eqy.preflight()
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts" / "verify_priority_safety.py"),
                             "--root", str(ROOT), "--out", str(out / "priority")],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    (out / "priority_output.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError("Priority safety checks failed; see priority_output.txt")
    with (out / "priority" / "formal.csv").open(encoding="utf-8-sig", newline="") as handle:
        priority_rows = list(csv.DictReader(handle))
    rows = [dict(case=row["case"], exit=0, verdict=row["verdict"],
                 arithmetic_shared="", comparison_shared="", priority_rewritten=row["rewritten"], reason=row["reason"])
            for row in priority_rows]
    save_csv(out / "formal.csv", rows)
    with prepared_runtime() as runtime:
        program = Path(runtime) / "yosys.exe"
        program_id = identity(program)
        (out / "program.txt").write_text(program_id + "\n", encoding="utf-8")
        if (out / "priority" / "program.txt").read_text(encoding="utf-8").strip() != program_id:
            raise RuntimeError("The priority checks used a different program")
        for name, top, options, expected_sharing, expected_comparison in CASES:
            source = ROOT / "scripts" / "generality_cases" / (top + ".v")
            directory = out / name
            directory.mkdir()
            recipe = (f"read_verilog -sv {quote(source, directory)}; hierarchy -check -top {top}; proc; "
                      "setundef -undriven -zero; setundef -init -zero; "
                      f"pmux_opt_rtlil -rewrite -sclr-promo-rom-only -no-probe {options}; "
                      "opt_clean; write_rtlil after.il; check")
            (directory / "synthesis.ys").write_text(recipe + "\n", encoding="utf-8")
            result = subprocess.run([str(program), "-s", "synthesis.ys"], cwd=directory, env=env(out),
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            output = result.stdout + result.stderr
            (directory / "synthesis.txt").write_text(output, encoding="utf-8")
            if result.returncode:
                raise RuntimeError(f"Custom transformation failed: {name}")
            sharing = "nested-arithmetic:" in output
            comparison = any(int(value) for value in re.findall(r"(\d+) decode-shared", output))
            if expected_sharing is not None and sharing != expected_sharing:
                raise RuntimeError(f"Arithmetic sharing did not follow the expected restriction: {name}")
            if expected_comparison is not None and comparison != expected_comparison:
                raise RuntimeError(f"Comparison sharing did not follow the selected option: {name}")
            (directory / "check.eqy").write_text(public_behavior_config(source, directory / "after.il", top, directory), encoding="utf-8")
            code, proof = eqy.run(["-d", "proof", "check.eqy"], directory, timeout=180)
            (directory / "proof_output.txt").write_text(proof, encoding="utf-8")
            verdict, reason = eqy.verdict_of(code, proof)
            rows.append(dict(case=name, exit=code, verdict=verdict, arithmetic_shared=sharing,
                             comparison_shared=comparison, priority_rewritten="", reason=reason))
            save_csv(out / "formal.csv", rows)
            print(f"{name}: {verdict}, arithmetic={sharing}, comparison={comparison}", flush=True)
            if verdict != "PROVEN":
                raise RuntimeError(f"Equivalence failed: {name}")
            if name == "shallow_w6":
                check_changed_output(source, directory, top)
    if len(rows) != 12 or any(row["verdict"] != "PROVEN" for row in rows):
        raise RuntimeError("The twelve targeted checks are incomplete")
    (out / "status.txt").write_text(f"checks={len(rows)}\nall_proven=True\n", encoding="utf-8")


if __name__ == "__main__":
    main()
