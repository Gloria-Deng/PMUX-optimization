"""Check parameter changes and signed arithmetic with the packaged programs."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import shutil
import subprocess

from evaluate_official_nine import ROOT, case_source, env, identity, save_csv, top_counts, prepared_runtime
from validation_support import config, quote
from validation_support import pin_audit
import run_eqy as eqy


def arithmetic_source(name, operator, signed, a_width, b_width, y_width):
    qualifier = "signed " if signed else ""
    inputs = ",\n".join(f"input {qualifier}[{a_width-1}:0] a{i}, input {qualifier}[{b_width-1}:0] b{i}" for i in range(4))
    arms = "\n".join(f"2'd{i}: y = a{i} {operator} b{i};" for i in range(3))
    return (f"module {name}(input [1:0] s, {inputs}, output reg {qualifier}[{y_width-1}:0] y);\n"
            f"always @* case(s)\n{arms}\ndefault: y = a3 {operator} b3;\nendcase\nendmodule\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    eqy.preflight()
    with prepared_runtime() as runtime_directory:
        runtime = Path(runtime_directory)
        programs = {"stock": runtime / "yosys_stock.exe", "delivered": runtime / "yosys.exe"}
        (out / "programs.txt").write_text("\n".join(f"{version}={identity(exe)}" for version, exe in programs.items()), encoding="utf-8")
        cases = []
        for name, width, lanes in [("pmux_case01_balanced", 4, 2), ("pmux_case02_pipeline", 5, 1),
                                   ("pmux_case03_crossbar", 4, 1), ("pmux_case04_feedback", 5, 1),
                                   ("pmux_case05_nested", 4, 2)]:
            src = case_source(name)
            cases.append((name, name + f"_w{width}_l{lanes}", src,
                          f"chparam -set WIDTH {width} -set LANES {lanes} {name};", ("stock", "delivered")))
        for name, op, signed, aw, bw, yw in [
            ("signed_add_wide", "+", True, 5, 3, 7), ("signed_add_narrow", "+", True, 8, 8, 4),
            ("signed_sub_truncated", "-", True, 8, 8, 4), ("unsigned_add_extended", "+", False, 5, 3, 7),
            ("unsigned_sub_truncated", "-", False, 8, 8, 4)]:
            cases.append((name, name, arithmetic_source(name, op, signed, aw, bw, yw), "", ("delivered",)))
        name = "dependent_selections"
        source = "module dependent_selections(input [31:0] a,b,c, input [1:0] s,t, output reg [7:0] y); reg [7:0] u;\n"
        for sel, output, lhs, rhs in (("s", "u", "a", "b"), ("t", "y", "u", "c")):
            source += f"always @* case ({sel})\n"
            for i in range(4):
                aa = f"{lhs}[{8*i} +: 8]" if lhs != "u" else "u"
                source += f"{'default' if i == 3 else str(i)}: {output} = {aa} + {rhs}[{8*i} +: 8];\n"
            source += "endcase\n"
        source += "endmodule\n"
        cases.append((name, name, source, "", ("delivered",)))


        name = "shared_upstream_cones"
        source = """module shared_upstream_cones(input [7:0] a,b,c,d,
    input [1:0] s,t, input [127:0] wide, output [127:0] untouched,
    output reg [7:0] y);
    wire [7:0] u=(a^b)+(c&d);
    wire [7:0] v=(a&c)^(b|d);
    wire [7:0] p=u^v;
    assign untouched=wide^{16{p}};
    always @* case(s)
    0:y=(u^a)+(v^b);
    1:y=(u^b)+(v^c);
    2:y=(u^c)+(v^d);
    default:y=(u^d)+(v^a);
    endcase
    endmodule
    """
        cases.append((name, name, source, "", ("delivered",)))
        rows = []
        for top, label, source, change, versions in cases:
            folder = out / label
            folder.mkdir()
            rtl = source if isinstance(source, Path) else folder / "source.v"
            if not isinstance(source, Path):
                rtl.write_text(source, encoding="utf-8")
            for version in versions:
                dest = folder / version
                dest.mkdir()
                recipe = (f"read_verilog -sv {quote(rtl)}; {change} hierarchy -check -top {top}; "
                          f"proc; setundef -undriven -zero; setundef -init -zero; synth_intel -family cycloneiv -top {top} "
                          "-run begin:map_cells; write_rtlil postabc.il; write_verilog -noattr postabc.v; "
                          f"synth_intel -family cycloneiv -top {top} -run map_cells:; write_rtlil final.il; stat")
                (dest / "synthesis.ys").write_text(recipe + "\n", encoding="utf-8")
                p = subprocess.run([str(programs[version]), "-s", "synthesis.ys"], cwd=dest, env=env(out), capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=180)
                (dest / "synthesis.txt").write_text(p.stdout + p.stderr, encoding="utf-8")
                if p.returncode or pin_audit(dest / "postabc.v"):
                    raise RuntimeError(f"Synthesis failed: {label} {version}")
                body = config(rtl, dest / "postabc.il", top, dest)
                if change:
                    body = body.replace("\nhierarchy -check", f"\n{change}\nhierarchy -check", 1)
                (folder / "check.eqy").write_text(body, encoding="utf-8")
                rc, raw = eqy.run(["-d", "proof", "../check.eqy"], dest, timeout=180)
                (dest / "proof_output.txt").write_text(raw, encoding="utf-8")
                verdict, reason = eqy.verdict_of(rc, raw)
                counts = top_counts(dest / "final.il", top)
                row = dict(case=label, version=version, exit=rc, verdict=verdict,
                           logic=counts.get("\\cycloneiv_lcell_comb", 0) + counts.get("$not", 0), reason=reason)
                rows.append(row)
                save_csv(out / "formal.csv", rows)
                print(f"{label} {version}: {verdict}", flush=True)
                if verdict != "PROVEN":
                    raise RuntimeError(f"Equivalence failed: {label} {version}")
        regressions = []
        for label in dict.fromkeys(row["case"] for row in rows if row["version"] == "stock"):
            pair = {row["version"]: row["logic"] for row in rows if row["case"] == label}
            if pair["delivered"] > pair["stock"]:
                regressions.append(label)
        (out / "status.txt").write_text(f"checks={len(rows)}\nall_proven=True\nparameter_resource_increases={regressions!r}\n", encoding="utf-8")
        if regressions:
            raise RuntimeError(f"Parameter resource increases: {regressions}")
        print(f"Passed {len(rows)} functional checks and all parameter resource comparisons.", flush=True)


if __name__ == "__main__":
    main()
