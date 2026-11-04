"""Measure all nine official cases using the 2026-10-31 to 11-02 clarification."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
from functools import lru_cache
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from pmux_preflight import tree_cpu_run
from validation_support import parse_stat
from evaluate_official_nine import CASES, case_source, resource_summary, resource_requirement_errors, top_io_bits
from delivery_runtime import temporary_for_yosys

METRICS = ("elapsed_s", "cpu_s", "memory_mb")
SCORED_METRICS = ("elapsed_s", "memory_mb")
WARMUP_CASE = "pmux_case05_nested"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    if rows:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path, start):
    try:
        return Path(os.path.relpath(path, start)).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


def change(before, after):
    if not math.isfinite(before) or not math.isfinite(after) or before <= 0 or after < 0:
        raise ValueError("Invalid measurement for a relative comparison")
    return 100.0 * (after / before - 1.0)


def recheck_rule(stock, delivered):

    over = any(change(float(stock[key]), float(delivered[key])) > 5.0 + 1e-9
               for key in SCORED_METRICS)
    if not over:
        return False, "INITIAL_WITHIN_5_PERCENT"
    longest = max(float(stock["elapsed_s"]), float(delivered["elapsed_s"]))
    if longest < 10.0:
        return True, "UNDER_10_SECONDS_RECHECK_5_ADDITIONAL_PAIRS"
    return False, "LONG_CASE_INITIAL_ONLY"


def classify(time_pct, memory_pct):
    if time_pct > 15.0 + 1e-9 or memory_pct > 15.0 + 1e-9:
        return "OVER_15_PERCENT"
    if time_pct <= 5.0 + 1e-9 and memory_pct <= 5.0 + 1e-9:
        return "WITHIN_5_PERCENT"
    return "BETWEEN_5_AND_15_PERCENT"


def mean_values(rows):
    if not rows:
        raise ValueError("Cannot average an empty measurement set")
    return {key: math.fsum(float(row[key]) for row in rows) / len(rows) for key in METRICS}


def _case_summary(case, category, initial, selected, rule):
    repeat = rule == "UNDER_10_SECONDS_RECHECK_5_ADDITIONAL_PAIRS"
    means = {version: mean_values(items) for version, items in selected.items()}
    row = dict(case=case, category=category, rule=rule,
               selected_stage="recheck" if repeat else "initial", selected_count=len(selected["stock"]),
               trigger_metrics=",".join(key for key in SCORED_METRICS
                   if change(initial["stock"][key], initial["delivered"][key]) > 5.0 + 1e-9))
    for key in METRICS:
        label = {"elapsed_s": "elapsed", "cpu_s": "cpu", "memory_mb": "memory"}[key]
        row[label + "_before"] = means["stock"][key]
        row[label + "_after"] = means["delivered"][key]
        row[label + "_pct"] = change(means["stock"][key], means["delivered"][key])
    row["elapsed_memory_class"] = classify(row["elapsed_pct"], row["memory_pct"])
    row["cpu_memory_class"] = classify(row["cpu_pct"], row["memory_pct"])
    for version, label in (("stock", "before"), ("delivered", "after")):
        row["logic_" + label] = int(initial[version]["logic"])
        row["dff_" + label] = int(initial[version]["dff"])
        row["io_bits_" + label] = int(initial[version]["io_bits"])
    return row


def summary_from_readings(readings, refs=None):
    """Validate the complete latest official sequence and recalculate its nine-case summary.

    Input may contain numeric Python values or text read from readings.csv.
    Rechecks use five additional pairs, excluding the initial pair. This is our
    implementation convention because the official reply does not specify this detail.
    """
    readings = list(readings)
    position, outputs = 0, set()
    resources = {}

    def take(case, category, version, stage, index):
        nonlocal position
        if position >= len(readings):
            raise RuntimeError(f"Missing efficiency measurement: {case} {version} {stage} {index}")
        original = readings[position]
        row = dict(original)
        try:
            if (int(row["sequence"]) != position + 1 or row["case"] != case
                    or row["category"] != category or row["version"] != version
                    or row["stage"] != stage or int(row["index"]) != index):
                raise ValueError("unexpected measurement order")
            if int(row["exit"]) != 0:
                raise ValueError("unsuccessful synthesis")
            for key in METRICS:
                row[key] = float(row[key])
                if not math.isfinite(row[key]) or row[key] <= 0:
                    raise ValueError(f"invalid measurement: {key}")
            for key in ("lut", "inv", "logic", "dff", "io_bits"):
                row[key] = int(row[key])
                if row[key] < 0:
                    raise ValueError(f"negative resource count: {key}")
            if row["logic"] != row["lut"] + row["inv"]:
                raise ValueError("logical-cell total differs")
            for key in ("reference_logic_matches", "output_stat_agrees", "abc9"):
                if str(row[key]) != "True":
                    raise ValueError(f"unsuccessful measurement check: {key}")
            if str(row["classic_abc"]) != "False" or row["meter_error"] not in (None, "", "None"):
                raise ValueError("unexpected mapper or measurement failure")
            output = row["output"]
            if not output or output in outputs:
                raise ValueError("missing or repeated output location")
            outputs.add(output)
            counts = (row["lut"], row["inv"], row["dff"], row["io_bits"])
            key = (case, version)
            if key in resources and resources[key] != counts:
                raise ValueError("resources changed between measurements")
            resources[key] = counts
            if refs is not None:
                reference = refs[key]
                if counts != (int(reference["lut"]), int(reference["not"]), int(reference["dff"]), int(reference["io_bits"])):
                    raise ValueError("resources differ from the assessment")
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            raise RuntimeError(f"Invalid efficiency measurement {position + 1}: {exc}") from exc
        position += 1
        return row

    warmup, _, warmup_category = next(item for item in CASES if item[0] == WARMUP_CASE)
    for index in range(1, 11):
        take(warmup, warmup_category, "stock", "warmup", index)
    summary = []
    for case, _, category in CASES:
        initial = {version: take(case, category, version, "initial", 1)
                   for version in ("stock", "delivered")}
        repeat, rule = recheck_rule(initial["stock"], initial["delivered"])
        selected = {version: [initial[version]] for version in ("stock", "delivered")}
        if repeat:
            selected = {"stock": [], "delivered": []}
            for index in range(1, 6):
                for version in ("stock", "delivered"):
                    selected[version].append(take(case, category, version, "recheck", index))
        summary.append(_case_summary(case, category, initial, selected, rule))
    if position != len(readings):
        raise RuntimeError("Unexpected efficiency measurements after the ninth case")
    return summary


def score_requirement_errors(summary, require_full_score=False):

    if len(summary) != 9 or len({row["case"] for row in summary}) != 9:
        raise RuntimeError("Expected nine distinct efficiency results")
    resource_rows = []
    for row in summary:
        for version, key in (("stock", "logic_before"), ("delivered", "logic_after")):
            suffix = "before" if version == "stock" else "after"
            resource_rows.append(dict(case=row["case"], version=version, lut=row[key],
                                      dff=row["dff_" + suffix], io_bits=row["io_bits_" + suffix], **{"not": 0}))
    resources, mean_reduction = resource_summary(resource_rows)
    errors = resource_requirement_errors(resources, mean_reduction, require_full_score)
    limit = 5.0 if require_full_score else 15.0
    for row in summary:
        for key in ("elapsed_pct", "memory_pct"):
            value = float(row[key])
            if not math.isfinite(value):
                errors.append(f"Invalid efficiency result: {row['case']} {key}")
            elif value > limit + 1e-9:
                errors.append(f"{row['case']} {key}={value:+.9f}% exceeds {limit:g}%")
    return errors, mean_reduction


@lru_cache(maxsize=1)
def _restored_assessment_runtime():
    temporary = tempfile.TemporaryDirectory(prefix="pmux_assessment_")
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


def checked_inputs(assessment):
    runtime = assessment / "runtime"
    current = {"stock": ROOT / "binary" / "baseline" / "yosys.exe",
               "delivered": ROOT / "binary" / "yosys.exe"}
    recorded = read_csv(assessment / "inputs.csv")
    if not recorded:
        raise RuntimeError("Assessment input list is empty")
    identities = []
    names = set()
    for row in recorded:
        relative_name = row["file"].replace("\\", "/")
        path = (ROOT / relative_name).resolve()
        if (not path.is_relative_to(ROOT) or relative_name in names or not path.is_file()
                or path.stat().st_size != int(row["bytes"]) or digest(path) != row["digest"]):
            raise RuntimeError(f"Assessment source has changed: {row['file']}")
        names.add(relative_name)
        identities.append((path, row["digest"]))
    for version, path in current.items():
        if not path.is_file() or not any(
                (ROOT / row["file"].replace("\\", "/")).resolve() == path.resolve()
                and row["digest"] == digest(path) for row in recorded):
            raise RuntimeError(f"Assessment executable differs from recorded input: {version}")
    references = read_csv(assessment / "metrics.csv")
    if len(references) != 18:
        raise RuntimeError("Expected 18 reference measurements")
    refs = {(row["case"], row["version"]): row for row in references}
    cases = []
    for row in references:
        if row["version"] != "stock":
            continue
        case, category = row["case"], row["category"]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", case):
            raise RuntimeError(f"Unsupported top module name: {case}")
        source = case_source(case)
        if not source.is_file() or not any(path == source.resolve() for path, _ in identities):
            raise RuntimeError(f"Official input absent from verified assessment list: {case}")
        if (case, "delivered") not in refs:
            raise RuntimeError(f"Optimized reference absent: {case}")
        cases.append((case, category, source))
    if len(cases) != 9 or len({case for case, _, _ in cases}) != 9 or len(refs) != 18:
        raise RuntimeError("Expected nine distinct official cases and two versions each")
    resource_summary(references)
    by_name = {case: (case, category, source) for case, category, source in cases}
    cases = [by_name[case] for case, _, _ in CASES]
    if not runtime.exists():
        runtime = Path(_restored_assessment_runtime().name)
    programs = {"stock": runtime / "yosys_stock.exe", "delivered": runtime / "yosys.exe"}
    for version, path in programs.items():
        if not path.is_file() or digest(path) != digest(current[version]):
            raise RuntimeError(f"Assessment executable differs from current package: {version}")
    for path in runtime.rglob("*"):
        if not path.is_file() or path.name == "yosys_stock.exe":
            continue
        counterpart = ROOT / "binary" / path.relative_to(runtime)
        if not counterpart.is_file() or digest(path) != digest(counterpart):
            raise RuntimeError(f"Assessment runtime dependency differs: {path.relative_to(runtime)}")
    return programs, cases, refs, identities


def top_counts(path, top):
    body = path.read_text(encoding="utf-8")
    match = re.search(r"^module \\" + re.escape(top) + r"\n(.*?)^end$", body, re.M | re.S)
    if match is None:
        raise RuntimeError(f"Top module absent from output: {top}")
    return Counter(re.findall(r"^  cell (\S+)", match.group(1), re.M))


def environment(out):
    system = os.environ.get("SystemRoot", r"C:\Windows")
    temporary = temporary_for_yosys(out / "tmp")
    return {"SystemRoot": system, "windir": system,
            "PATH": system + r"\System32;" + system,
            "TMP": temporary, "TEMP": temporary}


def defender_status():
    program = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    try:
        result = subprocess.run([str(program), "-NoProfile", "-NonInteractive", "-Command",
                                 "(Get-MpComputerStatus).RealTimeProtectionEnabled"],
                                capture_output=True, text=True, timeout=30)
        value = result.stdout.strip()
        return value if result.returncode == 0 and value in ("True", "False") else "UNKNOWN"
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN"


def registered_antivirus():
    """Read Windows' registered antivirus inventory without changing its settings."""
    program = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    command = ("$ErrorActionPreference='Stop'; "
               "$products=@(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntivirusProduct); "
               "if ($products.Count -eq 0) { 'NONE_REGISTERED' } else { "
               "$products | Sort-Object displayName | ForEach-Object { "
               "'{0} (reported productState={1})' -f $_.displayName,$_.productState } }")
    try:
        result = subprocess.run([str(program), "-NoProfile", "-NonInteractive", "-Command", command],
                                capture_output=True, text=True, timeout=30)
        return " | ".join(result.stdout.splitlines()).strip() if result.returncode == 0 and result.stdout.strip() else "UNKNOWN"
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN"


def execute(out, programs, refs, readings, case, category, source, version, stage, index):
    target = out / "executions" / case / f"{stage}_{index:02d}" / version
    target.mkdir(parents=True, exist_ok=False)
    input_path = relative(source, target)
    recipe = (f'read_verilog -sv "{input_path}"; hierarchy -check -top {case}; '
              f'proc; setundef -undriven -zero; setundef -init -zero; synth_intel -family cycloneiv -top {case}; '
              "write_verilog -noattr final.v; write_rtlil final.il; stat")
    (target / "synthesis.ys").write_text(recipe + "\n", encoding="utf-8")
    (target / "command.txt").write_text(
        f'"{relative(programs[version], target)}" -s synthesis.ys\n', encoding="utf-8")
    original_popen = subprocess.Popen
    elapsed = {}

    class TimedPopen(original_popen):
        def __init__(self, *args, **kwargs):
            self.started_at = time.perf_counter()
            super().__init__(*args, **kwargs)

        def communicate(self, *args, **kwargs):
            result = super().communicate(*args, **kwargs)
            elapsed["seconds"] = time.perf_counter() - self.started_at
            return result

    subprocess.Popen = TimedPopen
    try:
        rc, stdout, stderr, metrics = tree_cpu_run(
            [str(programs[version]), "-s", "synthesis.ys"], cwd=str(target),
            env=environment(out), timeout=180)
    finally:
        subprocess.Popen = original_popen
    stdout, stderr = stdout or "", stderr or ""
    metrics = dict(metrics, elapsed_s=elapsed.get("seconds"))
    (target / "stdout.txt").write_text(stdout, encoding="utf-8")
    (target / "stderr.txt").write_text(stderr, encoding="utf-8")
    (target / "measurement.txt").write_text(repr(metrics) + "\n", encoding="utf-8")
    counts = top_counts(target / "final.il", case) if (target / "final.il").is_file() else Counter()
    reference = refs[case, version]
    lut, inv, dff = counts.get("\\cycloneiv_lcell_comb", 0), counts.get("$not", 0), counts.get("\\dffeas", 0)
    io_bits = top_io_bits(target / "final.il", case) if (target / "final.il").is_file() else 0
    stat = parse_stat(stdout, case) if rc == 0 else {}
    stat_types = {key if key.startswith("$") else "\\" + key: value for key, value in stat.items()
                  if key not in ("wires", "ports", "cells")}
    counts_match = (lut == int(reference["lut"]) and inv == int(reference["not"])
                    and dff == int(reference["dff"]) and io_bits == int(reference["io_bits"]))
    row = dict(sequence=len(readings) + 1, case=case, category=category, version=version,
               stage=stage, index=index, exit=rc, elapsed_s=elapsed.get("seconds"),
               cpu_s=metrics.get("cpu_tree_s"), memory_mb=metrics.get("peak_main_working_set_mb"),
               memory_bytes=metrics.get("peak_main_working_set_bytes"),
               cpu_user_100ns=metrics.get("cpu_user_100ns"), cpu_kernel_100ns=metrics.get("cpu_kernel_100ns"),
               lut=lut, inv=inv, logic=lut + inv, dff=dff, io_bits=io_bits,
               reference_logic_matches=counts_match, output_stat_agrees=dict(counts) == stat_types,
               abc9="Executing ABC9 pass" in stdout, classic_abc="Executing ABC pass" in stdout,
               meter_error=metrics.get("job_error"), output=relative(target, out))
    readings.append(row)
    write_csv(out / "readings.csv", readings)
    write_csv(out / "output_files.csv", [
        dict(sequence=item["sequence"], case=item["case"], version=item["version"],
             stage=item["stage"], index=item["index"],
             measurement_file=item["output"] + "/measurement.txt",
             stdout_file=item["output"] + "/stdout.txt")
        for item in readings if item["stage"] != "warmup"])
    valid_values = all(isinstance(row[key], (int, float)) and math.isfinite(row[key]) and row[key] > 0
                       for key in METRICS)
    if (rc != 0 or not valid_values or not counts_match or not row["output_stat_agrees"]
            or stdout.count("Executing ABC9 pass") != 1 or row["classic_abc"] or row["meter_error"]):
        raise RuntimeError(f"Measurement failed: {case} {version} {stage} {index}; see {target}")
    print(f"{case} {stage} {index:02d} {version}: "
          f"time={row['elapsed_s']:.6f}s cpu={row['cpu_s']:.6f}s memory={row['memory_mb']:.2f}MB", flush=True)
    return row


def write_report(out, summary, conditions, require_full_score=False, skip_score_requirements=False):
    words = {"WITHIN_5_PERCENT": "时间和内存增幅均不超过5%",
             "BETWEEN_5_AND_15_PERCENT": "至少一项超过5%，均未超过15%",
             "OVER_15_PERCENT": "至少一项超过15%"}
    elapsed_status = classify(max(row["elapsed_pct"] for row in summary), max(row["memory_pct"] for row in summary))
    cpu_status = classify(max(row["cpu_pct"] for row in summary), max(row["memory_pct"] for row in summary))
    errors, mean_reduction = score_requirement_errors(summary, require_full_score)
    lines = ["# 九例效率测量报告", "",
             f"本组九例的平均逻辑单元缩减率为 {mean_reduction:.6f}%。"
             f"按完整经过时间与内存比较，{words[elapsed_status]}。CPU 时间只作为参考，不参与评分和复测触发。", "",
             f"检查要求为{'平均缩减至少 20%、逐例逻辑单元不增加、经过时间与内存增幅均不超过 5%' if require_full_score else '平均缩减至少 10%、逐例逻辑单元不增加、经过时间与内存增幅均不超过 15%'}。"
             "按最新第 63 条，另逐例检查 DFF 和顶层端口总位数相对原版均不得增加超过 20%；原版为零而优化版新增时视为超出。"
             f"{'本次启用了跳过评分要求的研究选项。' if skip_score_requirements else '不满足要求时保存完整结果并返回失败状态。'}", "",
             "## 测量方法", "",
             "采用 2026 年 10 月 31 日至 11 月 2 日最新答复。按第 61、63 条，测试开始统一用 pmux_case05_nested 执行原版 10 次预热，只运行原版，随后九例各自依次执行原版、优化版；系统重启后应重新开始测试。每次综合同时采集完整经过时间、包含 ABC 的 CPU 时间和 Yosys 主程序峰值工作集，并检查最终逻辑单元、DFF 和顶层端口总位数与资源测量一致。", "",
             "完整经过时间从创建程序前计至输出收集完成。CPU 时间包含子程序，峰值工作集只统计 Yosys 主程序。程序不调整安全软件、后台运行状态、优先级或 CPU 绑定。", "",
             "按第 63、64 条，两版在同一脚本中先将原始 RTL 转为寄存器结构并对未定义值及未指定初值补零，再进入 synth_intel。明确的初值保留，输入源文件不修改，准备时间完整计入。补零安排在综合前是本工程统一采用的处理方法。", "",
             "按第 63 条，经过时间或内存任一增幅超过 5% 即触发复核判断。两版初次经过时间均不足 10 秒时，固定追加 5 对原版、优化版测量，全部追加读数都计入；两版分别求算术平均，再以优化版平均值除以原版平均值计算增幅。初测不计入平均是本工程的实现约定，官方未明确这项细节。初测和全部复核读数均保存，不因复核结果再次追加测量或挑选次数。", "",
             "按第 47、52 条仍保留的长用例安排，以两版较长的初次经过时间判断：不足 10 秒允许复测，达到 10 秒时只测一次。两版均以 -s synthesis.ys 导入同一内容的综合脚本，并使用相同测量工具和运行依赖。", "",
             "## 逐例结果", "",
              "| 用例 | 每版采用次数 | 经过时间增幅 | CPU 时间增幅（参考） | 峰值工作集增幅 | 初测超 5% 项目 | 处理方式 |",
             "|---|---:|---:|---:|---:|---|---|"]
    for row in summary:
        method = "追加五次平均值" if row["selected_stage"] == "recheck" else "初测"
        trigger_names = {"elapsed_s": "经过时间", "cpu_s": "CPU时间", "memory_mb": "内存"}
        triggers = "、".join(trigger_names[key] for key in row["trigger_metrics"].split(",") if key)
        lines.append(f"| {row['case']} | {row['selected_count']} | {row['elapsed_pct']:+.2f}% | "
                     f"{row['cpu_pct']:+.2f}% | {row['memory_pct']:+.2f}% | {triggers or '无'} | {method} |")
    realtime = next((line.split("=", 1)[1] for line in conditions.splitlines()
                     if line.startswith("real_time_protection_enabled=")), "UNKNOWN")
    realtime_words = {"True": "开启", "False": "关闭"}.get(realtime, "未能读取")
    antivirus = next((line.split("=", 1)[1] for line in conditions.splitlines()
                      if line.startswith("registered_antivirus=")), "UNKNOWN")
    inventory = {"UNKNOWN": "未能读取", "NONE_REGISTERED": "未报告已注册产品"}.get(antivirus, antivirus)
    lines += ["", f"本次测量前读取的 Microsoft Defender 实时保护状态为{realtime_words}；Windows 安全中心报告的防病毒产品为：{inventory}。"
              "产品登记状态不能单独证明其运行期间是否启用实时扫描。程序只读取状态，不修改安全设置。", "",
              "官方第 47 条要求关闭安全软件并保持后台条件一致；本次数值反映上述实际机器状态。评分只采用完整经过时间和主程序峰值工作集。", ""]
    if errors:
        lines += ["## 未满足的数值条件", ""]
        for error in errors:
            match = re.fullmatch(r"(\S+) (elapsed_pct|cpu_pct|memory_pct)=([+\-\d.]+)% exceeds (\d+)%", error)
            if match:
                case, metric, value, limit = match.groups()
                label = {"elapsed_pct": "经过时间", "cpu_pct": "CPU 时间", "memory_pct": "峰值工作集"}[metric]
                lines.append(f"- {case} 的{label}增幅为 {value}%，超过 {limit}% 要求。")
            else:
                lines.append(f"- {error}")
        lines.append("")
    lines += [
              "## 文件", "", "- [逐次读数](readings.csv)保存预热、初测及全部复核。",
              "- [逐例汇总](summary.csv)列出两版原值、平均值及相对变化。",
              "- [输出引用表](output_files.csv)列出正式初测和追加复核的测量文件及程序输出。",
              "- [运行条件](conditions.txt)记录输入、程序和测量约定。",
              "- executions/ 保存每次执行的命令、原始输出和完整网表。", "",
              "## 待确认事项", "",
              "- 现场效率缺少关闭安全软件、统一后台运行条件后的复测。", ""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "conditions.txt").write_text(conditions + f"\ncompleted={datetime.now().astimezone().isoformat()}\n"
                                        f"elapsed_memory_class={elapsed_status}\ncpu_memory_class={cpu_status}\n"
                                        f"mean_reduction_pct={mean_reduction:.12g}\n"
                                        f"score_requirements_met={not errors}\n", encoding="utf-8")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="New output directory; existing paths are refused")
    parser.add_argument("--assessment", required=True, type=Path,
                        help="Existing nine-case assessment containing the current runtime and input list")
    scoring = parser.add_mutually_exclusive_group()
    scoring.add_argument("--require-full-score", action="store_true",
                         help="Require mean reduction >=20%%, no case increasing, and elapsed/memory increases <=5%%")
    scoring.add_argument("--skip-score-requirements", action="store_true",
                         help="Research only: save score failures without failing the command")
    args = parser.parse_args()
    if os.name != "nt":
        raise RuntimeError("This measurement requires Windows")
    out, assessment = args.out.resolve(), args.assessment.resolve()
    if out.exists():
        raise FileExistsError("Output already exists; choose a new directory")
    programs, cases, refs, identities = checked_inputs(assessment)
    out.mkdir(parents=True, exist_ok=False)
    (out / "tmp").mkdir()
    conditions = (f"started={datetime.now().astimezone().isoformat()}\n"
                  f"assessment={relative(assessment, ROOT)}\n"
                  "official_clarification=2026-10-31_to_11-02_items_58_to_65\n"
                  f"cases=9\nwarmup_stock_total=10\nwarmup_case={WARMUP_CASE}\n"
                  "warmup_version=stock_only\n"
                  "warmup_scope=once_at_test_start_restart_after_system_reboot\ninitial_order=stock,delivered\n"
                  "trigger=elapsed_or_main_working_set_increase_over_5_percent\n"
                  "short_case=max_initial_elapsed_both_versions_less_than_10_seconds\n"
                  "recheck=5_additional_pairs_excluding_initial\n"
                  "recheck_initial_exclusion=implementation_convention_not_explicitly_official\n"
                  "aggregation=ratio_of_mean_values_not_mean_of_ratios\n"
                  "long_case_at_least_10_seconds=initial_only\n"
                  "time=creation_start_to_communicate_end\n"
                  "scored_metrics=elapsed,memory\ncpu=reference_only_job_object_including_abc\n"
                  "initialization=original_rtl_zero_before_both_synthesis_flows\n"
                  "memory=main_process_peak_working_set_same_execution\ncommand=-s synthesis.ys\n"
                  "nonlogic_resource_limit=dff_and_top_io_bits_growth_at_most_20_percent\n"
                  "background_programs_unchanged=True\nsecurity_software_unchanged=True\n"
                  "system_settings_unmodified=True\n"
                  "runtime_search_path=windows_system_only\ntemporary_directory=output_tmp\n"
                  f"real_time_protection_enabled={defender_status()}\n"
                  f"registered_antivirus={registered_antivirus()}\n"
                  "cpu_affinity_unchanged=True\nprocess_priority_unchanged=True\n")
    conditions += (f"require_full_score={args.require_full_score}\n"
                   f"score_requirements_skipped={args.skip_score_requirements}\n")
    for version, program in programs.items():
        conditions += f"program_{version}={relative(program, ROOT)}\nprogram_{version}_digest={digest(program)}\n"
    (out / "conditions.txt").write_text(conditions, encoding="utf-8")
    readings, summary = [], []
    try:
        warmup_case, warmup_category, warmup_source = next(item for item in cases if item[0] == WARMUP_CASE)
        for index in range(1, 11):
            execute(out, programs, refs, readings, warmup_case, warmup_category, warmup_source, "stock", "warmup", index)
        for case, category, original in cases:
            source = original
            initial = {version: execute(out, programs, refs, readings, case, category, source, version, "initial", 1)
                       for version in ("stock", "delivered")}
            repeat, rule = recheck_rule(initial["stock"], initial["delivered"])
            selected = {version: [initial[version]] for version in ("stock", "delivered")}
            if repeat:
                selected = {"stock": [], "delivered": []}
                for index in range(1, 6):
                    for version in ("stock", "delivered"):
                        selected[version].append(execute(out, programs, refs, readings, case, category, source,
                                                         version, "recheck", index))
            row = _case_summary(case, category, initial, selected, rule)
            summary.append(row)
            write_csv(out / "summary.csv", summary)
            print(f"SUMMARY {case}: elapsed={row['elapsed_pct']:+.2f}% cpu={row['cpu_pct']:+.2f}% "
                  f"memory={row['memory_pct']:+.2f}% {rule}", flush=True)
        if any(digest(path) != expected for path, expected in identities):
            raise RuntimeError("Assessment source changed during measurement")
        for version, path in programs.items():
            package = ROOT / "binary" / ("baseline" if version == "stock" else "") / "yosys.exe"
            if digest(path) != digest(package):
                raise RuntimeError(f"Executable changed during measurement: {version}")
        summary = summary_from_readings(readings, refs)
        write_csv(out / "summary.csv", summary)
        errors = write_report(out, summary, conditions, args.require_full_score, args.skip_score_requirements)
        if errors and not args.skip_score_requirements:
            raise RuntimeError("; ".join(errors))
    except BaseException as exc:
        (out / "failure.txt").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise
    print(f"Completed nine cases. Report: {out / 'report.md'}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
