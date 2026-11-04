from __future__ import annotations

import ast
import csv
import math
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "plugin" / "dffeas_formal.v"


_STAT_LINE = re.compile(r"^\s*(\d+)\s+(\S+)\s*$")


def parse_stat(out: str, top: str | None = None) -> dict:


    headers = list(re.finditer(r"^=== (.+?) ===\s*$", out, re.M))
    if not headers or (top is not None and headers[-1].group(1).lstrip("\\") != top):
        return {}


    table: dict[str, int] = {}
    for ln in out[headers[-1].end():].splitlines():
        if re.match(r"^\d+(?:\.\d+)*\.\s|^End of script|^Warnings:", ln):
            break
        m = _STAT_LINE.match(ln)
        if not m:
            continue
        n, name = int(m.group(1)), m.group(2)
        if name in ("wires", "ports", "cells") or " " not in name:
            table[name] = n
    return table if "cells" in table else {}


def quote(path: Path, start: Path | None = None) -> str:
    path = path.resolve()
    if start is not None:
        try:
            return '"' + Path(os.path.relpath(path, start)).as_posix() + '"'
        except ValueError:
            pass
    return '"' + path.as_posix() + '"'


def config(rtl: Path, il: Path, top: str, directory: Path | None = None) -> str:
    def location(path):
        return quote(path, directory)
    return f"""[options]

[gold]
read_verilog -sv {location(rtl)}
hierarchy -check -top {top}
proc
setundef -undriven -zero
setundef -init -zero
prep -top {top} -flatten
setundef -undriven -zero
setundef -init -zero
hierarchy -purge_lib -top {top}
memory_map
async2sync
setundef -undriven -zero
setundef -init -zero

[gate]
read_rtlil {location(il)}
read_verilog -overwrite {location(MODEL)}
prep -top {top} -flatten
setundef -undriven -zero
setundef -init -zero
hierarchy -purge_lib -top {top}
memory_map
async2sync
setundef -undriven -zero
setundef -init -zero

[collect {top}]
group *
bind *

[strategy whole]
use sat
depth 12
"""


FORMAL_CELLS = """\
module cycloneiv_lcell_comb
  (output combout, cout,
   input dataa, datab, datac, datad, cin);

   parameter lut_mask = 16'hFFFF;
   parameter sum_lutc_input = "datac";
   parameter dont_touch = "off";
   parameter lpm_type = "cycloneiv_lcell_comb";

   function lut_data;
      input [15:0] mask;
      input        a, b, c, d;
      reg [7:0]    s3;
      reg [3:0]    s2;
      reg [1:0]    s1;
      begin
         s3 = d ? mask[15:8] : mask[7:0];
         s2 = c ?   s3[7:4]  :   s3[3:0];
         s1 = b ?   s2[3:2]  :   s2[1:0];
         lut_data = a ? s1[1] : s1[0];
      end
   endfunction

   wire arithmetic = (sum_lutc_input == "cin");
   assign combout = lut_data(lut_mask, dataa, datab, arithmetic ? cin : datac, datad);
   assign cout    = lut_data(lut_mask, dataa, datab, cin, 1'b0);
endmodule

module dffeas
  (output reg q = 1'b0,
   input d, clk, clrn, prn, ena, asdata, aload, sclr, sload);

   parameter is_wysiwyg = "false";
   parameter power_up = "dontcare";

   always @(posedge clk or negedge clrn) begin
      if (!clrn) q <= 1'b0;
      else if (ena) begin
         if (sclr)      q <= 1'b0;
         else if (sload) q <= asdata;
         else            q <= d;
      end
   end
endmodule
"""


DRIVEN_PINS = {"clk", "d", "q", "ena", "clrn", "sclr"}


TIED_CONST = {"prn": "1'h1", "asdata": "1'h0", "aload": "1'h0",
              "sload": "1'h0"}


CONST_RE = re.compile(r"1'h[01]")


def cell_instances(txt: str, cell: str) -> tuple:


    declared = len(re.findall(r"\b" + cell + r"\s*#", txt))
    out, params = [], []
    for m in re.finditer(r"\b" + cell + r"\s*#", txt):
        pos = m.end()
        for _ in range(2):                                                   
            if pos >= len(txt) or txt.find("(", pos) < 0:
                return declared, out, params
            i = txt.index("(", pos)
            depth, j = 0, i
            while j < len(txt):
                if txt[j] == "(":
                    depth += 1
                elif txt[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if _ == 0:
                params.append(txt[i:j + 1])                             
            if _ == 1:
                out.append({k: v.strip() for k, v in
                            re.findall(r"\.(\w+)\s*\(\s*([^()]*)\)", txt[i:j + 1])})
            pos = j + 1
    return declared, out, params


POWER_UP_TO_INIT = {"low": "0", "high": "1"}


def model_power_up_values() -> dict[str, str]:
    text = MODEL.read_text(encoding="utf-8")
    values = dict(re.findall(
        r'if\s*\(\s*power_up\s*==\s*"(\w+)"\s*\)\s*q\s*=\s*1\'b([01])', text))
    if any(values.get(name) != value for name, value in POWER_UP_TO_INIT.items()):
        raise RuntimeError("The EQY register model must preserve both low and high power_up values")
    return values


def pin_audit(netlist: Path) -> list:


    txt = netlist.read_text(encoding="utf-8", errors="replace")
    declared, ins, params = cell_instances(txt, "dffeas")
    bad = []
    if len(ins) != declared:
        return [f"{netlist.name}: parsed {len(ins)} dffeas instances but the netlist declares "
                f"{declared} -- the pin audit is looking at nothing, so it cannot vouch for the "
                f"cell model"]
    for n, conns in enumerate(ins, 1):
        for pin, val in conns.items():
            if pin in DRIVEN_PINS:
                continue
            if not CONST_RE.fullmatch(val):
                bad.append(f"{netlist.name} instance {n}: .{pin}({val}) is driven by a signal, "
                           f"but the formal dffeas ignores .{pin} -- the proof would be unsound")
        for pin, want in TIED_CONST.items():
            if pin not in conns:
                bad.append(f"{netlist.name} instance {n}: .{pin}() absent -- cannot assume it "
                           f"is tied {want}")
            elif conns[pin] != want:
                bad.append(f"{netlist.name} instance {n}: .{pin}({conns[pin]}) must be {want} "
                           "for the current register model")


    supported = model_power_up_values()
    seen_pu = 0
    for n, block in enumerate(params, 1):
        found = re.findall(r'power_up\s*\(\s*"(\w+)"', block)
        if len(found) != 1:
            bad.append(f"{netlist.name} instance {n}: {len(found)} power_up params in the param "
                       f"block -- cannot tell the model what this FF powers up to")
            continue
        seen_pu += 1
        if found[0] not in supported and found[0] != "dontcare":
            bad.append(f"{netlist.name} instance {n}: unsupported power_up(\"{found[0]}\")")
    if len(params) != declared:
        bad.append(f"{netlist.name}: parsed {len(params)} param blocks but {declared} dffeas "
                   f"are declared -- the power_up cross-check would silently skip the rest")
    print(f"[PIN-AUDIT] {netlist.name}: {declared} dffeas parsed, {seen_pu}/{declared} carry a "
          f"power_up reading, explicit initialization preserved, {len(bad)} problem(s)")
    return bad


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_output_files(efficiency):
    from evaluate_official_nine import top_io_bits
    readings = rows(efficiency / "readings.csv")
    formal = {row["sequence"]: row for row in readings if row["stage"] != "warmup"}
    if len(formal) != sum(row["stage"] != "warmup" for row in readings):
        raise RuntimeError("Duplicate efficiency measurement sequence")
    references = rows(efficiency / "output_files.csv")
    if len(references) != len(formal) or {row["sequence"] for row in references} != set(formal):
        raise RuntimeError("Expected one output reference per formal efficiency measurement")
    directory = efficiency.resolve()
    for row in references:
        expected = formal[row["sequence"]]
        if any(row[key] != expected[key] for key in ("case", "version", "stage", "index")):
            raise RuntimeError("Efficiency output reference identifies a different measurement")
        measurement = (directory / row["measurement_file"]).resolve()
        expected_measurement = (directory / expected["output"] / "measurement.txt").resolve()
        if measurement != expected_measurement:
            raise RuntimeError("Efficiency measurement file reference differs")
        for key in ("measurement_file", "stdout_file"):
            path = (directory / row[key]).resolve()
            if not path.is_relative_to(directory) or not path.is_file():
                raise RuntimeError(f"Efficiency output absent: {row[key]}")
        try:
            measured = ast.literal_eval(measurement.read_text(encoding="utf-8"))
            pairs = (("elapsed_s", "elapsed_s"), ("cpu_s", "cpu_tree_s"),
                     ("memory_mb", "peak_main_working_set_mb"),
                     ("memory_bytes", "peak_main_working_set_bytes"),
                     ("cpu_user_100ns", "cpu_user_100ns"),
                     ("cpu_kernel_100ns", "cpu_kernel_100ns"))
            for recorded_key, measured_key in pairs:
                saved_value, original_value = float(expected[recorded_key]), float(measured[measured_key])
                if (not math.isfinite(saved_value) or not math.isfinite(original_value)
                        or not math.isclose(saved_value, original_value, rel_tol=1e-12, abs_tol=1e-12)):
                    raise ValueError(f"different {recorded_key}")
            if measured.get("job_error") or measured.get("mem_job_error"):
                raise ValueError("measurement tool reported an error")
        except (ValueError, SyntaxError, KeyError, TypeError) as exc:
            raise RuntimeError(f"Efficiency reading differs from the original measurement: {row['sequence']}") from exc
        stdout = (directory / row["stdout_file"]).read_text(encoding="utf-8")
        counts = parse_stat(stdout, expected["case"])
        if (not counts or counts.get("cycloneiv_lcell_comb", 0) != int(expected["lut"])
                or counts.get("$not", 0) != int(expected["inv"])
                or counts.get("dffeas", 0) != int(expected["dff"])
                or top_io_bits(measurement.parent / "final.il", expected["case"]) != int(expected["io_bits"])
                or stdout.count("Executing ABC9 pass") != 1 or "Executing ABC pass" in stdout):
            raise RuntimeError(f"Efficiency output differs from the saved resources: {row['sequence']}")
    return references


def validate_results(assessment, efficiency, require_full_score=False):
    from evaluate_official_nine import CASES, resource_summary, resource_requirement_errors
    from measure_official_efficiency import checked_inputs, digest, summary_from_readings, score_requirement_errors
    programs, _, refs, _ = checked_inputs(assessment)
    resources, mean = resource_summary(list(refs.values()))
    errors = resource_requirement_errors(resources, mean, require_full_score)
    if errors:
        raise RuntimeError("; ".join(errors))
    recorded = rows(assessment / "resources.csv")
    if len(recorded) != 9 or len({row["case"] for row in recorded}) != 9:
        raise RuntimeError("Expected nine distinct saved resource results")
    expected_resources = {row["case"]: row for row in resources}
    for row in recorded:
        expected = expected_resources.get(row["case"])
        count_keys = ("logic_before", "logic_after", "dff_before", "dff_after", "io_bits_before", "io_bits_after")
        if (expected is None or any(int(row[key]) != expected[key] for key in count_keys)
                or not math.isclose(float(row["reduction_pct"]), expected["reduction_pct"], rel_tol=1e-12, abs_tol=1e-12)):
            raise RuntimeError(f"Saved resource result differs from actual synthesis: {row['case']}")
        for key in ("dff_growth_pct", "io_growth_pct"):
            if not math.isclose(float(row[key]), expected[key], rel_tol=1e-12, abs_tol=1e-12):
                raise RuntimeError(f"Saved DFF/IO growth differs: {row['case']} {key}")
        for key in ("dff_over_limit", "io_over_limit"):
            if row[key] != str(expected[key]):
                raise RuntimeError(f"Saved DFF/IO comparison differs: {row['case']} {key}")
    formal = rows(assessment / "formal.csv")
    expected_pairs = {(case, version) for case, _, _ in CASES for version in ("stock", "delivered")}
    if (len(formal) != 18 or {(row["case"], row["version"]) for row in formal} != expected_pairs
            or any(row["verdict"] != "PROVEN" or str(row["exit"]) != "0" for row in formal)):
        raise RuntimeError("All eighteen distinct current equivalence results must pass")
    control_dir = assessment / "formal_ascii"
    control = (control_dir / "control.txt").read_text(encoding="utf-8").splitlines()
    try:
        if not control[0].startswith("changed=") or not control[1].startswith("exit="):
            raise ValueError("missing changed/exit labels")
        changed = int(control[0].removeprefix("changed="))
        exit_code = int(control[1].removeprefix("exit="))
        verdict, reason = ast.literal_eval(control[2])
    except (ValueError, IndexError, SyntaxError, TypeError) as exc:
        raise RuntimeError("Invalid changed-design comparison result") from exc
    control_output = (control_dir / "changed_luts_output.txt").read_text(encoding="utf-8")
    if (changed < 1 or exit_code != 2 or verdict != "FAIL_OR_UNPROVEN" or not isinstance(reason, str)
            or "whole_design_sentence=False" not in reason
            or "successfully proved designs equivalent" in control_output.lower()):
        raise RuntimeError("The deliberately changed design was not rejected")
    validate_output_files(efficiency)
    timing = rows(efficiency / "summary.csv")
    if len(timing) != 9 or {row["case"] for row in timing} != set(expected_resources):
        raise RuntimeError("Expected the same nine efficiency cases")
    actual_timing = summary_from_readings(rows(efficiency / "readings.csv"), refs)
    actual_by_case = {row["case"]: row for row in actual_timing}
    for row in timing:
        actual = actual_by_case[row["case"]]
        if set(row) != set(actual):
            raise RuntimeError(f"Saved efficiency summary is incomplete: {row['case']}")
        for key, value in actual.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                try:
                    same = math.isfinite(float(row[key])) and math.isclose(
                        float(row[key]), float(value), rel_tol=1e-12, abs_tol=1e-12)
                except (ValueError, TypeError):
                    same = False
            else:
                same = row[key] == str(value)
            if not same:
                raise RuntimeError(f"Saved efficiency summary differs from the original readings: {row['case']} {key}")
    errors, _ = score_requirement_errors(actual_timing, require_full_score)
    if errors:
        raise RuntimeError("; ".join(errors))
    conditions = dict(line.split("=", 1) for line in (efficiency / "conditions.txt").read_text(encoding="utf-8").splitlines()
                      if "=" in line)
    if not conditions.get("completed"):
        raise RuntimeError("Efficiency assessment has not completed")
    for version, program in programs.items():
        if conditions.get(f"program_{version}_digest") != digest(program):
            raise RuntimeError(f"Efficiency result used a different program: {version}")
    for row in timing:
        expected = expected_resources[row["case"]]
        if any(int(row[key]) != expected[key] for key in
               ("logic_before", "logic_after", "dff_before", "dff_after", "io_bits_before", "io_bits_after")):
            raise RuntimeError(f"Efficiency resource result differs: {row['case']}")
    worst = {key: max(float(row[key]) for row in timing) for key in ("elapsed_pct", "cpu_pct", "memory_pct")}
    return resources, timing, mean, worst
