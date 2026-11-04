"""Check standalone PMUX commands, equivalent defaults and rejected options."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

from evaluate_official_nine import ROOT, env, identity, prepared_runtime, save_csv
from validation_support import config, quote
import run_eqy as eqy


COMMANDS = (
    ("default", "", None),
    ("explicit_no_probe", "-no-probe", None),
    ("reject_probe_all", "-probe-all", "-probe-all is unavailable"),
    ("reject_counter", "-counter", "-counter is unavailable"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    eqy.preflight()
    source = ROOT / "cases" / "test2.v"
    rows = []
    default_output = None
    same_outputs = False
    with prepared_runtime() as runtime:
        program = Path(runtime) / "yosys.exe"
        program_id = identity(program)
        (out / "program.txt").write_text(program_id + "\n", encoding="utf-8")
        save_csv(out / "inputs.csv", [dict(file=str(path.relative_to(ROOT)), digest=identity(path))
                                     for path in (ROOT / "binary" / "yosys.exe", source,
                                                  Path(__file__).resolve())])
        for name, options, expected_error in COMMANDS:
            directory = out / name
            directory.mkdir()
            recipe = (f"read_verilog -sv {quote(source, directory)}; hierarchy -check -top test2; proc; "
                      "setundef -undriven -zero; setundef -init -zero; "
                      f"pmux_opt_rtlil -rewrite -sclr-promo-rom-only {options}; "
                      "opt_clean; write_rtlil after.il; check")
            (directory / "synthesis.ys").write_text(recipe + "\n", encoding="utf-8")
            result = subprocess.run([str(program), "-s", "synthesis.ys"], cwd=directory,
                                    env=env(out), capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=60)
            output = (result.stdout or "") + (result.stderr or "")
            (directory / "stdout.txt").write_text(result.stdout or "", encoding="utf-8")
            (directory / "stderr.txt").write_text(result.stderr or "", encoding="utf-8")
            (directory / "synthesis.txt").write_text(output, encoding="utf-8")
            after = directory / "after.il"
            abc_calls = output.count("Executing ABC pass")
            abc9_calls = output.count("Executing ABC9 pass")
            pmux_calls = output.count("Executing PMUX_OPT_RTLIL pass")
            row = dict(case=name, synthesis_exit=result.returncode, abc_calls=abc_calls,
                       abc9_calls=abc9_calls, pmux_calls=pmux_calls, after_exists=after.is_file(),
                       exit="", verdict="", same_output_as_default="", passed=False, reason="")
            no_mapping = abc_calls == 0 and abc9_calls == 0
            if expected_error is not None:
                rejected_before_rewrite = not re.search(r"PMUX_OPT_RTLIL: \d+ mux cells", output)
                row["passed"] = (result.returncode != 0 and expected_error in output
                                 and no_mapping and pmux_calls == 1 and not after.exists()
                                 and rejected_before_rewrite)
                row["exit"] = result.returncode
                row["verdict"] = "REJECTED_AS_EXPECTED" if row["passed"] else "FAILED"
                row["reason"] = (f"expected_message={expected_error in output}; "
                                 f"rejected_before_rewrite={rejected_before_rewrite}")
            elif result.returncode == 0 and after.is_file() and no_mapping and pmux_calls == 1:
                body = after.read_bytes()
                if name == "default":
                    default_output = body
                else:
                    same_outputs = default_output is not None and body == default_output
                    row["same_output_as_default"] = same_outputs
                (directory / "check.eqy").write_text(
                    config(source, after, "test2", directory), encoding="utf-8")
                code, proof = eqy.run(["-d", "proof", "check.eqy"], directory, timeout=180)
                (directory / "proof_output.txt").write_text(proof, encoding="utf-8")
                verdict, reason = eqy.verdict_of(code, proof)
                row["exit"], row["verdict"], row["reason"] = code, verdict, reason
                row["passed"] = (verdict == "PROVEN" and code == 0
                                 and (name == "default" or same_outputs))
            else:
                row["verdict"] = "FAILED"
                row["reason"] = "Standalone transformation failed or invoked an unexpected mapper"
            rows.append(row)
            save_csv(out / "formal.csv", rows)
            print(f"{name}: {row['verdict']}, ABC={abc_calls}, ABC9={abc9_calls}, "
                  f"after={after.exists()}, passed={row['passed']}", flush=True)
        if identity(ROOT / "binary" / "yosys.exe") != program_id:
            raise RuntimeError("The packaged program changed during command checks")
    passed = len(rows) == len(COMMANDS) and all(row["passed"] for row in rows)
    lines = ["# 独立 PMUX 命令检查", "", f"整体结果：{'通过' if passed else '未通过'}。",
             "", "本组单列记录，未计入九例正式十八项 EQY。test2 经过 proc 与相同补零处理后，分别执行省略和显式加入 `-no-probe` 的独立命令。",
             "", "| 检查 | 结果 | ABC次数 | ABC9次数 | 是否产生after.il |", "|---|---|---|---|---|"]
    lines += [f"| {row['case']} | {row['verdict']} | {row['abc_calls']} | {row['abc9_calls']} | {row['after_exists']} |"
              for row in rows]
    lines += ["", f"两种正常命令的 after.il 内容逐字节一致：{same_outputs}。两份结果各自与原始 RTL 完成 EQY。",
              "", "两个禁止选项要求程序立即返回失败，出现对应提示，不调用 ABC，不产生后续 after.il，也不进入改写完成阶段。",
              "", "`formal.csv` 记录逐项结果，`program.txt` 记录使用的程序。每项目录保存实际命令、程序输出；正常项另有 after.il、EQY 配置及完整证明输出。"]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "status.txt").write_text(f"checks={len(rows)}\neqy_checks=2\nall_expected={passed}\n"
                                    f"same_outputs={same_outputs}\n", encoding="utf-8")
    if not passed:
        raise RuntimeError("One or more standalone PMUX command checks failed")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
