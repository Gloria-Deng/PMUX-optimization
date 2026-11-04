"""Check initialized register conversion and nested arithmetic sharing."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess

from evaluate_official_nine import ROOT, env, identity, prepared_runtime, save_csv, top_counts
from validation_support import config, pin_audit, quote
import run_eqy as eqy


NESTED = ("w6", "w9", "w17", "lanes2", "signed", "external_arithmetic",
          "narrow_signed", "partial_result", "indirect_result")
CASES = [("g_init_mixed", "test4"), ("g_init_alias", "test4")]
CASES += [("variant_" + name, "variant_" + name) for name in NESTED]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    eqy.preflight()
    rows = []
    with prepared_runtime() as runtime:
        program = Path(runtime) / "yosys.exe"
        (out / "program.txt").write_text(identity(program) + "\n", encoding="utf-8")
        for name, top in CASES:
            source = ROOT / "scripts" / "algorithm_cases" / (name + ".v")
            directory = out / name
            directory.mkdir()
            recipe = (f"read_verilog -sv {quote(source, directory)}; hierarchy -check -top {top}; "
                      f"proc; setundef -undriven -zero; setundef -init -zero; "
                      f"synth_intel -family cycloneiv -top {top} -run begin:map_cells; "
                      "write_rtlil postabc.il; write_verilog -noattr postabc.v; "
                      f"synth_intel -family cycloneiv -top {top} -run map_cells:; "
                      "write_rtlil final.il; stat")
            (directory / "synthesis.ys").write_text(recipe + "\n", encoding="utf-8")
            result = subprocess.run([str(program), "-s", "synthesis.ys"], cwd=directory,
                                    env=env(out), capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=180)
            (directory / "synthesis.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
            if result.returncode or pin_audit(directory / "postabc.v"):
                raise RuntimeError(f"Synthesis or register model mismatch: {name}")
            sharing = "nested-arithmetic:" in result.stdout
            guarded = name in ("variant_partial_result", "variant_indirect_result")
            if name.startswith("variant_") and sharing == guarded:
                raise RuntimeError(f"Unexpected arithmetic sharing choice: {name}")
            promoted = re.search(r"(\d+) pin-promoted", result.stdout)
            if name.startswith("g_init_") and (not promoted or int(promoted[1]) == 0):
                raise RuntimeError(f"Initialized register conversion was not exercised: {name}")
            (directory / "check.eqy").write_text(config(source, directory / "postabc.il", top, directory),
                                                  encoding="utf-8")
            code, output = eqy.run(["-d", "proof", "check.eqy"], directory, timeout=180)
            (directory / "proof_output.txt").write_text(output, encoding="utf-8")
            verdict, reason = eqy.verdict_of(code, output)
            counts = top_counts(directory / "final.il", top)
            row = dict(case=name, exit=code, verdict=verdict, sharing=sharing,
                       logic=counts.get("\\cycloneiv_lcell_comb", 0) + counts.get("$not", 0),
                       dff=counts.get("\\dffeas", 0), reason=reason)
            rows.append(row)
            save_csv(out / "formal.csv", rows)
            print(f"{name}: {verdict}, logic={row['logic']}, sharing={sharing}", flush=True)
            if verdict != "PROVEN":
                raise RuntimeError(f"Equivalence failed: {name}")
    (out / "status.txt").write_text(f"checks={len(rows)}\nall_proven=True\n", encoding="utf-8")


if __name__ == "__main__":
    main()
