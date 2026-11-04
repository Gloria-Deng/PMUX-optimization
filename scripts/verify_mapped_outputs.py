"""Compare the nine saved final Cyclone IV netlists with their source RTL."""
from __future__ import annotations

import argparse
from pathlib import Path

from evaluate_official_nine import CASES, ROOT, check_saved_inputs, identity, save_csv
from validation_support import FORMAL_CELLS, MODEL, config, pin_audit, quote
import run_eqy as eqy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    assessment = args.assessment.resolve()
    check_saved_inputs(assessment)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    eqy.preflight()
    model = out / "cycloneiv_comb.v"
    model.write_text(FORMAL_CELLS.split("module dffeas", 1)[0], encoding="utf-8")
    programs = (ROOT / "binary" / "baseline" / "yosys.exe", ROOT / "binary" / "yosys.exe")
    (out / "programs.txt").write_text(
        "\n".join(f"{label}={identity(program)}" for label, program in zip(("stock", "delivered"), programs)) + "\n",
        encoding="utf-8")
    rows = []
    for top, rtl, category in CASES:
        directory = out / top
        directory.mkdir()
        netlist = assessment / top / "delivered" / "final.il"
        pins = pin_audit(assessment / top / "delivered" / "final.v")
        if pins:
            raise RuntimeError(f"Unsupported register connections: {top}: {pins}")
        body = config(rtl, netlist, top, directory)
        marker = "read_verilog -overwrite " + quote(MODEL, directory)
        if marker not in body:
            raise RuntimeError("Register model loading command absent")
        body = body.replace(marker, "read_verilog -overwrite " + quote(model, directory) + "\n" + marker, 1)
        (directory / "check.eqy").write_text(body, encoding="utf-8")
        code, output = eqy.run(["-d", "proof", "check.eqy"], directory, timeout=180)
        (directory / "proof_output.txt").write_text(output, encoding="utf-8")
        verdict, reason = eqy.verdict_of(code, output)
        rows.append(dict(case=top, category=category, version="delivered", exit=code,
                         verdict=verdict, netlist_digest=identity(netlist), reason=reason))
        save_csv(out / "formal.csv", rows)
        print(f"{top} final Cyclone IV: {verdict}", flush=True)
        if verdict != "PROVEN":
            raise RuntimeError(f"Final mapped netlist differs from RTL: {top}")
    check_saved_inputs(assessment)
    (out / "status.txt").write_text(f"checks={len(rows)}\nall_proven=True\n", encoding="utf-8")


if __name__ == "__main__":
    main()
