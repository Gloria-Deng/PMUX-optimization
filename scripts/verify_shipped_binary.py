#!/usr/bin/env python3
"""Verify the current packaged files and optional nine-case assessment.

Current delivery uses the PMUX pass and the original ABC9 command.
The official requirement permits Yosys 0.69 with different minor revisions;
the two programs must use the same selected revision.
Without --assessment this checks files and source declarations only.  Supply
--assessment to validate a completed nine-case synthesis and EQY result that
matches the current package.  This script never starts synthesis or EQY itself.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path
import re
import os
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "binary"
MANIFEST = BIN / "MANIFEST.json"
ARCH = ROOT / "results" / "binary_bundle" / "summary.json"


def sha16(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def program_version_problems(binary_dir=None):
    binary_dir = Path(binary_dir) if binary_dir is not None else BIN
    problems = []
    revisions = []
    env = dict(os.environ)
    env["PATH"] = str(binary_dir) + os.pathsep + env.get("PATH", "")
    for relative in ("yosys.exe", "baseline/yosys.exe"):
        try:
            result = subprocess.run([str(binary_dir / relative), "-V"], env=env,
                                    capture_output=True, text=True, timeout=30)
            revision = re.search(
                r"\bYosys (0\.69(?:\+\d+)?)\s+\(git sha1 ([0-9a-f]+)(?:-dirty)?[,)]",
                result.stdout)
            if result.returncode != 0 or revision is None:
                problems.append(f"Expected Yosys 0.69: {relative}: {result.stdout.strip()}")
            else:
                revisions.append(revision.groups())
        except (OSError, subprocess.TimeoutExpired) as exc:
            problems.append(f"Cannot check program version: {relative}: {exc}")
    if len(revisions) == 2 and revisions[0] != revisions[1]:
        problems.append("Original and optimized Yosys must use the same selected 0.69 revision")
    return problems


def manifest_problems(man):
    from patch_synth_intel_cc import is_applied, mapping_kind, read_keep_endings
    problems = []
    if man.get("delivery_patch_set") != ["pass"]:
        problems.append("Delivery set must be the PMUX pass with original ABC9 mapping")
    patched = ROOT / "plugin" / "synth_intel.cc.patched"
    cc = ROOT / "plugin" / "pmux_opt_rtlil.cc"
    pass_source = cc.read_text(encoding="utf-8")
    if re.search(r'Pass::call(?:_on_module)?\([^;]*"abc(?:9)?\b', pass_source):
        problems.append("The custom pass must not invoke an additional ABC or ABC9 mapping")
    if "no_probe = false" in pass_source or 'probe_all = true' in pass_source:
        problems.append("The custom command must always use structural optimization without additional synthesis")
    try:
        source = read_keep_endings(patched)
        if not is_applied(source, "pass") or mapping_kind(source) != "stock":
            problems.append("Current synth_intel source must contain the PMUX pass and original ABC9 mapping")
    except (OSError, SystemExit) as exc:
        problems.append(str(exc))
    identities = ((cc, "pass_cc_sha256_16"), (patched, "synth_intel_patched_sha256_16"),
                  (BIN / "yosys.exe", "exe_sha256_16"))
    for path, key in identities:
        if not path.is_file() or sha16(path) != man.get(key):
            problems.append(f"Current file differs from package declaration: {path.name}")
    entries = man.get("files", [])
    if not entries:
        problems.append("Package file list is empty")
    seen = set()
    for entry in entries:
        rel = Path(entry["rel"])
        if rel.is_absolute() or ".." in rel.parts or entry["rel"] in seen:
            problems.append(f"Invalid or duplicate package path: {rel}")
            continue
        seen.add(entry["rel"])
        path = BIN / rel
        if not path.is_file():
            problems.append(f"Package file absent: {rel}")
        elif path.stat().st_size != entry["bytes"] or sha16(path) != entry["sha256_16"]:
            problems.append(f"Package file changed: {rel}")
    problems.extend(program_version_problems())
    return problems


def assessment_facts(assessment, require_full_score=False):
    from evaluate_official_nine import CASES, resource_summary, resource_requirement_errors
    from measure_official_efficiency import checked_inputs, read_csv
    _, _, refs, _ = checked_inputs(assessment)
    resources, mean = resource_summary(list(refs.values()))
    errors = resource_requirement_errors(resources, mean, require_full_score)
    if errors:
        raise RuntimeError("; ".join(errors))
    formal = read_csv(assessment / "formal.csv")
    expected = {(case, version) for case, _, _ in CASES for version in ("stock", "delivered")}
    if (len(formal) != 18 or {(row["case"], row["version"]) for row in formal} != expected
            or any(row["verdict"] != "PROVEN" or str(row["exit"]) != "0" for row in formal)):
        raise RuntimeError("All eighteen current equivalence checks are required")
    control = (assessment / "formal_ascii" / "control.txt").read_text(encoding="utf-8")
    changed = re.search(r"(?m)^changed=(\d+)$", control)
    try:
        verdict, reason = ast.literal_eval(control.splitlines()[2])
    except (IndexError, ValueError, SyntaxError, TypeError) as exc:
        raise RuntimeError("Invalid changed-design comparison result") from exc
    if (not changed or int(changed.group(1)) < 1 or not re.search(r"(?m)^exit=2$", control)
            or verdict != "FAIL_OR_UNPROVEN" or not isinstance(reason, str)
            or "whole_design_sentence=False" not in reason):
        raise RuntimeError("The deliberately changed design was not rejected")
    return {"cases": 9, "equivalence_checks": 18, "mean_reduction_pct": mean,
            "single_case_resource_increases": 0, "dff_over_20_percent_cases": 0,
            "io_over_20_percent_cases": 0, "changed_design_rejected": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, help="Completed nine-case result matching the current package")
    parser.add_argument("--require-full-score", action="store_true", help="Require at least 20 percent mean resource reduction")
    parser.add_argument("--out", type=Path, default=ARCH, help="Verification report; does not modify the package")
    args = parser.parse_args(argv)
    if not MANIFEST.is_file():
        print(f"BINARY-BUNDLE: SETUP-FAIL missing {MANIFEST}")
        return 2
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    problems = manifest_problems(man)
    facts = None
    if args.assessment:
        try:
            facts = assessment_facts(args.assessment.resolve(), args.require_full_score)
        except (OSError, RuntimeError, ValueError) as exc:
            problems.append(str(exc))
    scope = "NINE_CASE_ASSESSMENT" if args.assessment else "FILES_AND_SOURCES_ONLY"
    payload = {"scope": scope, "delivery_patch_set": ["pass"], "mapping_script": "stock",
               "required_yosys": "0.69; same selected revision for both programs", "require_full_score": args.require_full_score,
               "manifest_entries": len(man.get("files", [])), "assessment": facts,
               "problems": problems,
               "note": "File and source checks alone do not establish synthesis, equivalence, efficiency or full score."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for problem in problems:
        print(f"PROBLEM: {problem}")
    print(f"BINARY-BUNDLE: {'FAIL' if problems else 'OK'} scope={scope} problems={len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
