

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.dont_write_bytecode = True
from pmux_preflight import tree_cpu_run
from validation_support import parse_stat
from delivery_runtime import temporary_for_yosys

def case_source(name):
    directory = ROOT / "中科亿海微" / "pmux_case"
    candidates = (ROOT / "cases" / (name + ".v"),
                  directory / (name + ".v"),
                  directory / "competition_case" / name / (name + ".v"),
                  directory / "pmux_cases" / (name + ".v"))
    return next((path for path in candidates if path.is_file()), candidates[0])


CASES = [(f"test{i}", case_source(f"test{i}"), "original") for i in range(1, 5)]
CASES += [(name, case_source(name), "new") for name in (
    "pmux_case01_balanced", "pmux_case02_pipeline", "pmux_case03_crossbar",
    "pmux_case04_feedback", "pmux_case05_nested")]
PROGRAMS = {"stock": ROOT / "binary" / "baseline" / "yosys.exe", "delivered": ROOT / "binary" / "yosys.exe"}


def quote(p, start=None):
    path = Path(p).resolve()
    if start is not None:
        try:
            return '"' + Path(os.path.relpath(path, start)).as_posix() + '"'
        except ValueError:
            pass
    return '"' + path.as_posix() + '"'


def save_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader()
        writer.writerows(rows)


def identity(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def input_identities():
    bundle = ROOT / "binary"
    dependencies = sorted(
        [path for path in bundle.iterdir()
         if path.is_file() and path.suffix.lower() in (".exe", ".dll") and path.name != "yosys.exe"]
        + [path for path in (bundle / "share").rglob("*") if path.is_file()])
    paths = [source for _, source, _ in CASES]
    paths += [bundle / "baseline" / "yosys.exe", bundle / "yosys.exe"]
    paths += [ROOT / "plugin" / name for name in (
        "pmux_opt_rtlil.cc", "synth_intel.cc.patched", "dffeas_formal.v")]
    paths += [ROOT / "scripts" / name for name in (
        "evaluate_official_nine.py", "measure_official_efficiency.py", "validation_support.py",
        "run_eqy.py", "pmux_preflight.py", "delivery_runtime.py")]
    paths += dependencies
    identities = [{"file": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
                   "digest": identity(path)} for path in paths]
    return identities, dependencies


def check_saved_inputs(out):
    current, _ = input_identities()
    with (out / "inputs.csv").open(encoding="utf-8-sig", newline="") as handle:
        saved = list(csv.DictReader(handle))
    expected = {row["file"].replace("\\", "/"): row for row in current}
    names = [row["file"].replace("\\", "/") for row in saved]
    if len(saved) != len(expected) or set(names) != set(expected):
        raise RuntimeError("Saved synthesis inputs do not include the current programs, model, cases and dependencies")
    for row, name in zip(saved, names):
        actual = expected[name]
        if int(row["bytes"]) != actual["bytes"] or row["digest"] != actual["digest"]:
            raise RuntimeError(f"Saved synthesis input differs from the current file: {name}")


def top_counts(il, top):
    body = Path(il).read_text(encoding="utf-8")
    match = re.search(r"^module \\" + re.escape(top) + r"\n(.*?)^end$", body, re.M | re.S)
    if match is None:
        raise RuntimeError(f"top module absent: {top}")
    return Counter(re.findall(r"^  cell (\S+)", match.group(1), re.M))


def top_io_bits(il, top):
    """Count each declared top-level port bit once, including bidirectional bits."""
    body = Path(il).read_text(encoding="utf-8")
    match = re.search(r"^module \\" + re.escape(top) + r"\n(.*?)^end$", body, re.M | re.S)
    if match is None:
        raise RuntimeError(f"top module absent: {top}")
    count = 0
    for declaration in re.findall(r"^  wire (.+)$", match.group(1), re.M):
        if not re.search(r"\b(?:input|output|inout) \d+\b", declaration):
            continue
        width = re.search(r"\bwidth (\d+)\b", declaration)
        count += int(width.group(1)) if width else 1
    if count <= 0:
        raise RuntimeError(f"No top-level IO bits found: {top}")
    return count


def growth_pct(before, after):
    if before == 0:
        return 0.0 if after == 0 else math.inf
    return 100.0 * (after - before) / before


def resource_summary(rows):

    expected = {case for case, _, _ in CASES}
    by_case = {}
    for row in rows:
        case, version = row["case"], row["version"]
        if case not in expected or version not in ("stock", "delivered"):
            raise RuntimeError(f"Unexpected resource measurement: {case} {version}")
        pair = by_case.setdefault(case, {})
        if version in pair:
            raise RuntimeError(f"Duplicate resource measurement: {case} {version}")
        if "exit" in row and str(row["exit"]) != "0":
            raise RuntimeError(f"Failed synthesis in resource measurements: {case} {version}")
        if "output_stat_agrees" in row and str(row["output_stat_agrees"]) != "True":
            raise RuntimeError(f"Resource counts disagree: {case} {version}")
        lut, inv = int(row["lut"]), int(row["not"])
        dff, io_bits = int(row["dff"]), int(row["io_bits"])
        if min(lut, inv, dff, io_bits) < 0:
            raise RuntimeError(f"Negative resource count: {case} {version}")
        pair[version] = dict(logic=lut + inv, dff=dff, io_bits=io_bits)
    if set(by_case) != expected or any(set(pair) != {"stock", "delivered"}
                                      for pair in by_case.values()):
        raise RuntimeError("Expected both versions of all nine official cases")
    summary = []
    for case, _, category in CASES:
        pair = by_case[case]
        before, after = pair["stock"]["logic"], pair["delivered"]["logic"]
        if before <= 0:
            raise RuntimeError(f"Original logical-cell count must be positive: {case}")
        result = dict(case=case, category=category, logic_before=before, logic_after=after,
                      reduction_pct=100.0 * (before - after) / before,
                      resource_increase=after > before)
        for metric, label in (("dff", "dff"), ("io_bits", "io")):
            original, optimized = pair["stock"][metric], pair["delivered"][metric]
            result[metric + "_before"] = original
            result[metric + "_after"] = optimized
            result[label + "_growth_pct"] = growth_pct(original, optimized)
            result[label + "_over_limit"] = optimized * 5 > original * 6
        summary.append(result)
    return summary, math.fsum(row["reduction_pct"] for row in summary) / len(summary)


def resource_requirement_errors(summary, mean_reduction, require_full_score=False):
    errors = [f"Logical cells increased: {row['case']} {row['logic_before']} -> {row['logic_after']}"
              for row in summary if row["resource_increase"]]
    for row in summary:
        for metric, label in (("dff", "dff"), ("io_bits", "io")):
            if row[label + "_over_limit"]:
                errors.append(f"{label.upper()} growth exceeds 20%: {row['case']} "
                              f"{row[metric + '_before']} -> {row[metric + '_after']}")
    if require_full_score and mean_reduction < 20.0:
        errors.append(f"Mean logical-cell reduction {mean_reduction:.9f}% is below 20%")
    elif not require_full_score and mean_reduction < 10.0:
        errors.append(f"Mean logical-cell reduction {mean_reduction:.9f}% is below the required 10%")
    return errors


def check_resources(out, rows, require_full_score=False, skip_score_requirements=False):
    summary, mean_reduction = resource_summary(rows)
    errors = resource_requirement_errors(summary, mean_reduction, require_full_score)
    save_csv(out / "resources.csv", summary)
    (out / "resource_status.txt").write_text(
        f"mean_reduction_pct={mean_reduction:.12g}\n"
        f"resource_increase_cases={sum(row['resource_increase'] for row in summary)}\n"
        f"dff_over_20_percent_cases={sum(row['dff_over_limit'] for row in summary)}\n"
        f"io_over_20_percent_cases={sum(row['io_over_limit'] for row in summary)}\n"
        f"require_full_score={require_full_score}\n"
        f"score_requirements_skipped={skip_score_requirements}\n"
        f"score_requirements_met={not errors}\n"
        + "".join(f"failure={error}\n" for error in errors), encoding="utf-8")
    print(f"RESOURCES: mean reduction={mean_reduction:.6f}% "
          f"increased cases={sum(row['resource_increase'] for row in summary)}", flush=True)
    if errors and not skip_score_requirements:
        raise RuntimeError("; ".join(errors))


def env(out):
    tmp = out / "tmp"
    tmp.mkdir(exist_ok=True)
    system = os.environ.get("SystemRoot", r"C:\Windows")


    temporary = temporary_for_yosys(tmp)
    return {"SystemRoot": system, "windir": system,
            "PATH": system + r"\System32;" + system, "TMP": temporary, "TEMP": temporary}


def prepared_runtime():
    temporary = tempfile.TemporaryDirectory(prefix="pmux_shared_runtime_")
    runtime = Path(temporary.name)
    try:
        for source in (ROOT / "binary").iterdir():
            if source.is_file() and source.suffix.lower() in (".exe", ".dll"):
                shutil.copy2(source, runtime / source.name)
        shutil.copytree(ROOT / "binary" / "share", runtime / "share")
        shutil.copy2(ROOT / "binary" / "baseline" / "yosys.exe", runtime / "yosys_stock.exe")
    except BaseException:
        temporary.cleanup()
        raise
    return temporary


def synth(out):
    rows = []
    for case, rtl, category in CASES:
        script = (f"read_verilog -sv {quote(rtl, out / case / 'stock')}; hierarchy -check -top {case}; "
                  f"proc; setundef -undriven -zero; setundef -init -zero; synth_intel -family cycloneiv -top {case}; "
                  "write_verilog -noattr final.v; write_rtlil final.il; stat")
        for version, exe in PROGRAMS.items():
            target = out / case / version
            target.mkdir(parents=True, exist_ok=False)
            (out / case / "synthesis.ys").write_text(script + "\n", encoding="utf-8")


            real_popen = subprocess.Popen
            elapsed = {}
            class TimedPopen(real_popen):
                def __init__(self, *args, **kwargs):
                    self.started_at = time.perf_counter()
                    super().__init__(*args, **kwargs)
                def communicate(self, *args, **kwargs):
                    answer = super().communicate(*args, **kwargs)
                    elapsed['seconds'] = time.perf_counter() - self.started_at
                    return answer
            subprocess.Popen = TimedPopen
            try:
                rc, stdout, stderr, metrics = tree_cpu_run([str(exe), "-s", "../synthesis.ys"], cwd=str(target), env=env(out), timeout=180)
            finally:
                subprocess.Popen = real_popen
            (target / "stdout.txt").write_text(stdout or "", encoding="utf-8")
            (target / "stderr.txt").write_text(stderr or "", encoding="utf-8")
            st = parse_stat(stdout or "", case) if rc == 0 else {}
            il = target / "final.il"
            counts = top_counts(il, case) if il.is_file() else Counter()
            table = {k: v for k, v in st.items() if k not in ("wires", "ports", "cells")}
            same = dict(counts) == {k if k.startswith("$") else "\\" + k: v for k, v in table.items()}
            row = {"case": case, "category": category, "version": version, "exit": rc,
                   "lut": counts.get("\\cycloneiv_lcell_comb", 0), "not": counts.get("$not", 0),
                   "dff": counts.get("\\dffeas", 0), "io_bits": top_io_bits(il, case),
                   "total": sum(counts.values()),
                   "output_stat_agrees": same, "abc9": "Executing ABC9 pass" in stdout,
                   "abc9_calls": stdout.count("Executing ABC9 pass"),
                   "classic_abc": "Executing ABC pass" in stdout,
                   "pmux_calls": stdout.count("Executing PMUX_OPT_RTLIL pass"),
                   "cpu_s": metrics.get("cpu_tree_s"), "elapsed_s": elapsed.get("seconds"),
                   "memory_mb": metrics.get("peak_main_working_set_mb"),
                   "memory_bytes": metrics.get("peak_main_working_set_bytes"),
                   "cpu_user_100ns": metrics.get("cpu_user_100ns"),
                   "cpu_kernel_100ns": metrics.get("cpu_kernel_100ns"),
                   "cpu_cycles": metrics.get("cpu_tree_cycles"), "processes": metrics.get("tree_processes"),
                   "processes_with_cycles": metrics.get("procs_with_cycles"),
                   "meter_error": metrics.get("job_error"),
                   "cell_counts": repr(dict(counts)), "metrics_raw": repr(metrics)}
            rows.append(row)
            save_csv(out / "metrics.csv", rows)
            cpu_display = f"{row['cpu_s']:.6f}" if row["cpu_s"] is not None else "unavailable"
            memory_display = f"{row['memory_mb']:.2f}" if row["memory_mb"] is not None else "unavailable"
            print(f"SYNTH {case} {version}: exit={rc} LUT={row['lut']} NOT={row['not']} "
                  f"DFF={row['dff']} CPU={cpu_display}s MEM={memory_display}MB", flush=True)
            if (rc != 0 or not same or row["abc9_calls"] != 1 or row["classic_abc"]
                    or row["pmux_calls"] != (1 if version == "delivered" else 0)
                    or metrics.get("job_error")):
                raise RuntimeError(f"synthesis or measurement failed: {case} {version}")
    return rows


def formal(out):
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    import run_eqy as eqy
    from validation_support import config
    from validation_support import pin_audit
    eqy.preflight()
    dest = out / "formal_ascii"
    dest.mkdir(exist_ok=True)
    rows = []
    for case, rtl, category in CASES:
        script = (f"read_verilog -sv {quote(rtl, out / case / 'stock')}; hierarchy -check -top {case}; "
                  f"proc; setundef -undriven -zero; setundef -init -zero; synth_intel -family cycloneiv -top {case} "
                  "-run begin:map_cells; write_rtlil postabc.il; write_verilog -noattr postabc.v")
        for version, exe in PROGRAMS.items():
            label = case + "_" + version
            target = out / case / version
            post = target / "postabc.il"

            (out / case / "postabc.ys").write_text(script + "\n", encoding="utf-8")
            p = subprocess.run([str(exe), "-s", "../postabc.ys"], cwd=target, env=env(out), capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=180)
            (target / "postabc_stdout.txt").write_text(p.stdout + p.stderr, encoding="utf-8")
            pins = pin_audit(target / "postabc.v") if p.returncode == 0 else ["synthesis failed"]
            cfg = dest / (label + ".eqy")
            cfg.write_text(config(rtl, post, case, dest), encoding="utf-8")
            if (p.returncode or pins or p.stdout.count("Executing ABC9 pass") != 1
                    or "Executing ABC pass" in p.stdout):
                rc, raw = -1, repr(pins)
            else:
                rc, raw = eqy.run(["-d", label, cfg.name], dest, timeout=180)
            (dest / (label + "_output.txt")).write_text(raw, encoding="utf-8")
            verdict, reason = eqy.verdict_of(rc, raw)
            row = {"case": case, "category": category, "version": version, "exit": rc,
                   "verdict": verdict, "reason": reason, "pins": repr(pins), "seconds_limit": 180}
            rows.append(row)
            save_csv(out / "formal.csv", rows)
            print(f"EQY {label}: {verdict} exit={rc}", flush=True)


    case, _, _ = CASES[4]
    rtl = case_source(case)
    original = out / case / "delivered" / "postabc.il"
    body = original.read_text(encoding="utf-8")
    module = re.search(r"^module \\" + re.escape(case) + r"\n(.*?)^end$", body, re.M | re.S)
    if module is None:
        raise RuntimeError("Control top module absent")
    output = re.search(r"^  wire(?: width (\d+))? output (\d+) (\\\S+)$", module[1], re.M)
    if output is None:
        raise RuntimeError("Control needs an observable output")
    width, port, name = int(output[1] or 1), output[2], output[3]
    internal = "\\pmux_control_original_output"
    if internal in module[1]:
        raise RuntimeError("Control wire name already exists")
    altered = re.sub(re.escape(name) + r"(?=\s|$)", lambda _: internal, module[1])
    altered = altered.replace(f" output {port} {internal}", f" {internal}", 1)
    altered += (f"  wire width {width} output {port} {name}\n"
                "  cell $not \\pmux_control_invert_output\n"
                f"    parameter \\A_SIGNED 0\n    parameter \\A_WIDTH {width}\n"
                f"    parameter \\Y_WIDTH {width}\n    connect \\A {internal}\n"
                f"    connect \\Y {name}\n  end\n")
    body = body[:module.start(1)] + altered + body[module.end(1):]
    changed = width
    mutant = dest / "changed_luts.il"
    mutant.write_text(body, encoding="utf-8")
    cfg = dest / "changed_luts.eqy"
    cfg.write_text(config(rtl, mutant, case, dest), encoding="utf-8")
    rc, raw = eqy.run(["-d", "changed_luts", cfg.name], dest, timeout=180)
    (dest / "changed_luts_output.txt").write_text(raw, encoding="utf-8")
    (dest / "control.txt").write_text(f"changed={changed}\nexit={rc}\n{eqy.verdict_of(rc, raw)}\n", encoding="utf-8")
    print(f"EQY changed design: {eqy.verdict_of(rc, raw)[0]} exit={rc}", flush=True)
    if len(rows) != 18 or any(r["verdict"] != "PROVEN" for r in rows):
        raise RuntimeError("not all eighteen equivalence checks passed")
    if changed == 0 or rc != 2 or "Successfully proved designs equivalent" in raw:
        raise RuntimeError("the deliberately changed design was not rejected")


def main():
    global PROGRAMS
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "official_nine_latest")
    ap.add_argument("--phase", choices=("synthesis", "formal", "all"), default="all")
    scoring = ap.add_mutually_exclusive_group()
    scoring.add_argument("--require-full-score", action="store_true",
                         help="Also require the nine-case mean logical-cell reduction to reach 20%%")
    scoring.add_argument("--skip-score-requirements", action="store_true",
                         help="Research only: save resource failures without failing the command")
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if len(CASES) != 9:
        raise RuntimeError(f"expected nine cases, got {len(CASES)}")
    with prepared_runtime() as runtime_directory:
        if args.phase in ("synthesis", "all"):
            identities, dependencies = input_identities()
            unequal = [str(p.relative_to(ROOT / "binary")) for p in dependencies if not (ROOT / "binary" / "baseline" / p.relative_to(ROOT / "binary")).is_file() or identity(p) != identity(ROOT / "binary" / "baseline" / p.relative_to(ROOT / "binary"))]


            runtime = Path(runtime_directory)
            PROGRAMS = {"stock": runtime / "yosys_stock.exe", "delivered": runtime / "yosys.exe"}
            save_csv(out / "inputs.csv", identities)
            (out / "conditions.txt").write_text(f"started={datetime.now().isoformat()}\ncases={len(CASES)}\ncommon_dependency_files={len(dependencies)}\noriginal_dependency_differences={unequal!r}\nversions_run_once_each=True\ninitialization=original_rtl_zero_before_both_synthesis_flows\nsource_files_unchanged=True\n", encoding="utf-8")
            rows = synth(out)
            if any(identity(ROOT / row['file']) != row['digest'] for row in identities):
                raise RuntimeError("input changed during synthesis")
        if args.phase in ("formal", "all"):
            check_saved_inputs(out)
            runtime = Path(runtime_directory)
            PROGRAMS = {"stock": runtime / "yosys_stock.exe", "delivered": runtime / "yosys.exe"}
            formal(out)
        if args.phase == "formal":
            with (out / "metrics.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        check_resources(out, rows, args.require_full_score, args.skip_score_requirements)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
