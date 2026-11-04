#!/usr/bin/env python3


import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


SUITE = Path(os.environ.get("OSS_CAD_SUITE", str(ROOT / "binary" / "formal"))).resolve()
YOSYS = Path(os.environ.get("PMUX_NATIVE_YOSYS", str(SUITE / "bin" / "yosys.exe")))
DLL_REL = "plugin/pmux_opt_rtlil.dll"                                                  


MAKE_DIRS = []


def extra_make_dirs() -> list[Path]:
    out = []
    for raw in os.environ.get("PMUX_MAKE_DIRS", "").split(os.pathsep):
        if raw.strip():
            out.append(Path(raw.strip()))
    return out


def resolve_eqy(path_dirs: list[str]) -> Path | None:


    env = os.environ.get("PMUX_EQY")
    if env and env.strip():
        p = Path(env.strip())
        return p if p.is_file() else None                                                   
    for d in path_dirs:
        for name in ("eqy.exe", "eqy"):
            c = Path(d) / name
            if c.is_file():
                return c
    found = shutil.which("eqy")
    return Path(found) if found else None


def path_dirs() -> list[str]:


    system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    hints = [SUITE / "bin", SUITE / "lib", SUITE / "msys" / "usr" / "bin", *extra_make_dirs()]
    if "OSS_CAD_SUITE" in os.environ:
        hints.extend(Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p)
    hints.extend((system / "System32", system))
    return list(dict.fromkeys(str(d) for d in hints if d.is_dir()))


EQY = resolve_eqy(path_dirs())

OUT = ROOT / "results" / "eval_eqy"
QUAR = OUT / "workdir_archive"
CASES = ["test1", "test2", "test3", "test4"]


ENTRY_DIR = ROOT / "results" / "entry_fallback"
ENTRY_FACTS: dict = {}


def work_set(argv):


    argv = list(argv)
    _mode = (os.environ.get("PMUX_EQY_MODE") or "").strip().lstrip("-")
    if _mode:
        argv.append("--" + _mode)
    if "--hier" in argv:
        return hier_jobs(), "_hier"
    if "--entry" in argv:
        return entry_jobs(), "_entry"
    if "--tier2" in argv:
        return tier2_jobs(), "_tier2"
    jobs = [(t, ROOT / "rtl" / "official" / t / f"{t}.v",
             ROOT / "rtl" / "optimized" / f"{t}.v") for t in CASES]
    return jobs, ""


BUILT_CANDIDATES = [os.environ.get("PMUX_BUILT_YOSYS", ""),
                    r"D:\yosys_build\bucrt\yosys.exe"]


TIER2_CHAIN = ("hierarchy -top {top}; proc; opt_expr; opt_clean; opt -nodffe -nosdff; "
               "fsm; opt; memory -nomap; opt_clean; opt -full; opt_clean; ")
TIER2_MARKER = "opt_clean; opt -full; opt_clean; "


TIER2_PASSLINE = "pmux_opt_rtlil -rewrite; "


TIER2_FACTS: dict = {}

CONFIG = """[options]

[gold]
read -sv {gold}
prep -top {top}
memory_map

[gate]
read -sv {gate}
prep -top {top}
memory_map

[strategy simple]
use sat
depth {depth}
"""

CONFIG_TIER2 = """[options]

[gold]
read_rtlil {gold}
prep -top {top}
memory_map

[gate]
read_rtlil {gate}
prep -top {top}
memory_map

[strategy simple]
use sat
depth {depth}
"""


def built_yosys() -> Path:
    exe = next((Path(c) for c in BUILT_CANDIDATES if c and Path(c).is_file()), None)
    if exe is None:
        print("FAIL: --tier2 需要一份把 pass 编进主程序的 yosys（PMUX_BUILT_YOSYS 或 "
              "D:/yosys_build/bucrt/yosys.exe）。本机没有 —— 这一格是**未实测**，"
              "不是通过。")
        raise SystemExit(3)
    return exe


def tier2_scripts(src: Path, top: str) -> tuple:


    read = f"read_verilog -sv {src.as_posix()}; "
    head = read + TIER2_CHAIN.format(top=top)
    gold = head + "write_rtlil {gold}"
    gate = head + TIER2_PASSLINE + "write_rtlil {gate}"
    if gate.replace(TIER2_PASSLINE, "", 1).replace("{gate}", "{gold}") != gold:
        print("FAIL: --tier2 的两臂不再是「同一条脚本、只差一道 pass」")
        raise SystemExit(3)
    return gold, gate


def il_semantic(data: bytes) -> bytes:


    return b"\n".join(l for l in data.splitlines() if not l.startswith(b"autoidx "))


def tier2_jobs() -> list:

    import tempfile
    from pmux_preflight import built_yosys_env
    exe = built_yosys()
    e = built_yosys_env(exe)
    d = Path(tempfile.mkdtemp(prefix="pmux_eqy_tier2_"))
    jobs = []
    for t in CASES:
        src = ROOT / "rtl" / "official" / t / f"{t}.v"
        gold, gate = d / f"{t}_gold.il", d / f"{t}_tier2.il"
        sg, st = tier2_scripts(src, t)
        rw = None
        for out, prog in ((gold, sg.format(gold=gold.as_posix())),
                          (gate, st.format(gate=gate.as_posix()))):
            p = subprocess.run([str(exe), "-p", prog], cwd=str(ROOT), env=e,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=300)
            if p.returncode != 0 or not out.is_file():
                print(f"FAIL: tier-2 网表生成失败 {t} ({out.name}) rc={p.returncode}: "
                      f"{((p.stdout or '') + (p.stderr or ''))[-200:]}")
                raise SystemExit(3)
            for line in (p.stdout or "").splitlines():
                if "PMUX_OPT_RTLIL:" in line:
                    m = re.search(r"(\d+) rewritten", line)
                    rw = int(m.group(1)) if m else None
        raw_same = gold.read_bytes() == gate.read_bytes()
        same = il_semantic(gold.read_bytes()) == il_semantic(gate.read_bytes())
        TIER2_FACTS[t] = {"identical": same, "byte_identical": raw_same,
                          "rewritten": rw, "exe": str(exe)}
        print(f"[tier2] {t}: 两臂（去 autoidx 后）{'相同' if same else '不同'} "
              f"rewritten={rw} 逐字节相同={raw_same}  <- {exe.name} @ {exe.parent}")
        jobs.append((t, gold, gate))
    return jobs


def entry_arms_verdict(same, claims, row: dict) -> str:


    if not row:
        return ("FAIL: results/entry_fallback has no row for this case -- the bytes being "
                "proved are not tied to any archive that says what the entry did")
    if same is None:
        return "FAIL: one of the two netlists is missing"
    base, t2 = row.get("base_lut"), row.get("tier2_lut")
    if same:
        if claims is False:
            return "FAIL: the two files are byte-identical but the archive says they differ"
        if base is not None and t2 is not None and base != t2:
            return f"FAIL: arms identical yet the archive reads LUT {base}->{t2}"
        return "SELF_EQUAL (0 改写直通：证的是同一张网表等于自己，不构成对优化的验证)"
    if claims is True:
        return "FAIL: the files differ but the archive says identical_to_source=True"
    if base is None or t2 is None:
        return "FAIL: the archive row carries no LUT reading to check the delta against"
    if t2 >= base:
        return (f"FAIL: the two arms differ but nothing was saved ({base}->{t2}) -- that "
                f"difference is not the optimisation we are claiming")
    return f"MEANINGFUL (两臂因这道 pass 不同；归档 LUT {base}->{t2})"


def entry_jobs() -> list:


    arch = {}
    raw = {}
    try:
        raw = json.loads((ENTRY_DIR / "summary_entry_fallback.json")
                         .read_text(encoding="utf-8"))
        rows = raw["rows"]
        arch = {r.get("case"): r for r in rows}
    except Exception as exc:                                                 
        print(f"[entry] 读不到降级入口归档（{type(exc).__name__}: {exc}）—— 无法核对"
              "两臂是否真的因 pass 不同；先跑 verify_entry_fallback.py")
    jobs = []
    for top in CASES:
        gold = ROOT / "rtl" / "official" / top / f"{top}.v"
        gate = ENTRY_DIR / f"{top}_tier2.v"
        same = None
        if gold.exists() and gate.exists():
            same = gold.read_bytes() == gate.read_bytes()
        row = arch.get(top) or {}
        claims = row.get("identical_to_source")
        ENTRY_FACTS[top] = {"identical": same, "archive_identical": claims,
                            "base_lut": row.get("base_lut"),
                            "tier2_lut": row.get("tier2_lut"),
                            "gate": str(gate), "has_archive_row": bool(row)}
        if same is not None and claims is not None and same != bool(claims):
            ENTRY_FACTS[top]["contradiction"] = (
                f"the files hash {'equal' if same else 'different'} but "
                f"summary_entry_fallback.json says identical_to_source={claims}")
        ENTRY_FACTS[top]["arms"] = entry_arms_verdict(same, claims, row)
        print(f"[entry] {top}: 两臂{'相同' if same else '不同' if same is not None else '(缺文件)'}"
              f" 归档 identical_to_source={claims} LUT {row.get('base_lut')}->"
              f"{row.get('tier2_lut')} ⇒ {ENTRY_FACTS[top]['arms'][:44]}")
        jobs.append((top, gold, gate))
    _entry_product_ties(raw)
    return jobs


ENTRY_TOOL: dict = {}


def _entry_product_ties(raw: dict) -> None:


    from pmux_preflight import _sha256
    dll = ROOT / "plugin" / "pmux_opt_rtlil.dll"
    cc = ROOT / "plugin" / "pmux_opt_rtlil.cc"
    t = {"written_by": {"dll": str(dll),
                        "load": "plugin -i inside plugin/pmux_opt.tcl (tier 2 = the C++ pass "
                                "in-process)",
                        "not": "not the compiled-into-main-program form (that is --tier2)"},
         "dll_sha256_now": _sha256(dll) if dll.is_file() else None,
         "cc_sha256_now": _sha256(cc) if cc.is_file() else None,
         "archive_tool": (raw or {}).get("tool")}
    problems = []
    if not t["dll_sha256_now"]:
        problems.append("no plugin/pmux_opt_rtlil.dll on disk: nothing to tie these products to")
    at = t["archive_tool"] or {}
    if not at:
        problems.append("summary_entry_fallback.json carries no `tool` block, so these products "
                        "cannot be attributed to any binary -- re-run verify_entry_fallback.py "
                        "(it records the yosys/DLL/.cc hashes now)")
    elif at.get("dll_sha256") and t["dll_sha256_now"] and at["dll_sha256"] != t["dll_sha256_now"]:
        problems.append(f"the DLL on disk is {t['dll_sha256_now'][:12]}\u2026 but the archive says "
                        f"these products came from {at['dll_sha256'][:12]}\u2026 -- EQY would be "
                        f"certifying bytes an older plugin produced")
    elif at.get("cc_sha256") and t["cc_sha256_now"] and at["cc_sha256"] != t["cc_sha256_now"]:
        problems.append("the shipped .cc is not the source of the DLL that wrote these products")
    for top in CASES:
        g = ENTRY_DIR / f"{top}_tier2.v"
        src = ROOT / "rtl" / "official" / top / f"{top}.v"
        if not (g.exists() and cc.exists() and src.exists()):
            continue


        if g.read_bytes() == src.read_bytes():
            continue
        if g.stat().st_mtime < cc.stat().st_mtime:
            problems.append(f"{g.name} predates plugin/pmux_opt_rtlil.cc -- it was written "
                            f"before the source we deliver")
    t["problems"] = problems
    ENTRY_TOOL.clear()
    ENTRY_TOOL.update(t)
    for m in problems:
        print("[entry-tie] FAIL:", m)


def hier_jobs() -> list:


    import tempfile
    d = Path(tempfile.mkdtemp(prefix="pmux_eqy_hier_"))
    files = [ROOT / "rtl" / "hier" / "hier_pmux_sub.v", ROOT / "rtl" / "hier" / "hier_pmux_top.v"]
    pre = ("plugin -i " + DLL_REL + "\n"
           + "".join(f"read_verilog -sv {p.as_posix()}\n" for p in files)
           + "hierarchy -check -top hier_pmux_top\nproc\n")
    jobs = []
    for case in ("hier_pmux_top",):
        gold, gate = d / f"{case}_gold.il", d / f"{case}_gate.il"


        for path, extra in ((gold, ""), (gate, "pmux_opt_rtlil -rewrite\n")):
            p = subprocess.run([str(YOSYS), "-p", pre + extra +
                                f"write_rtlil {path.as_posix()}"],
                               cwd=str(ROOT), env=env_for_suite(), capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=600)
            if p.returncode != 0 or not path.is_file():
                print(f"[hier] {case}: 生成 {path.name} 失败 rc={p.returncode} "
                      + ((p.stdout or "") + (p.stderr or ""))[-200:])
            TIER2_FACTS[case] = {
                "exe": str(YOSYS),
                "exe_resolution": "PMUX_NATIVE_YOSYS, else OSS_CAD_SUITE/bin/yosys.exe",
                "rewritten": None, "identical": None, "arms_dir": str(d)}
            log = (p.stdout or "") + (p.stderr or "")
            m = re.search(r"PMUX_OPT_RTLIL: (.*?), (\d+) rewritten", log)
            if extra:
                TIER2_FACTS[case]["rewritten"] = int(m.group(2)) if m else None
        if gold.is_file() and gate.is_file():
            TIER2_FACTS[case]["identical"] = (
                il_semantic(gold.read_bytes()) == il_semantic(gate.read_bytes()))
        f = TIER2_FACTS[case]
        print(f"[hier] {case}: 两臂（去 autoidx 后）"
              f"{'相同' if f['identical'] else '不同' if f['identical'] is not None else '(缺文件)'}"
              f" rewritten={f['rewritten']}  <- 发行套件 yosys + DLL（包内产物）")
        jobs.append((case, gold, gate))
    return jobs


def env_for_suite() -> dict:
    return env()


def env():
    e = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "BASH_ENV", "ENV"):
        e.pop(name, None)
    e["YOSYSHQ_ROOT"] = str(SUITE)
    e["PATH"] = os.pathsep.join(path_dirs())
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    return e


def eqy_command() -> list[str]:

    python = SUITE / "lib" / "python3.exe"
    script = SUITE / "bin" / "eqy-script.py"
    if EQY == SUITE / "bin" / "eqy.exe" and python.is_file() and script.is_file():
        return [str(python), "-B", "-X", "utf8", str(script)]
    return [str(EQY)]


def preflight():


    e = env()
    missing = []
    for tool in ("make", "bash", "sh", "grep"):
        if shutil.which(tool, path=e["PATH"]) is None:
            missing.append(tool)
    print(f"  eqy  -> {EQY if EQY else 'NOT RESOLVED'}")
    print(f"  yosys-> {YOSYS if YOSYS.is_file() else 'NOT RESOLVED'}")
    if EQY is None:
        named = os.environ.get("PMUX_EQY")
        print("PREFLIGHT FAIL — no eqy binary resolved." + (
            f"  PMUX_EQY={named!r} is not a file, and this script deliberately does not fall back"
            " to a different binary when an explicit one was named."
            if named else
            "  Set PMUX_EQY to the eqy executable, or put it on PATH (or install the oss-cad-suite"
            " and set OSS_CAD_SUITE). NO evidence files were touched."))
        raise SystemExit(3)
    if not YOSYS.is_file():
        print(f"PREFLIGHT FAIL — yosys not reachable at {YOSYS}; set PMUX_NATIVE_YOSYS or "
              "OSS_CAD_SUITE. NO evidence files were touched.")
        raise SystemExit(3)
    if missing:
        print("PREFLIGHT FAIL — tools missing from effective PATH:", ", ".join(missing))
        print("  EQY's make recipes shell out to bash/sh/grep; without them every case")
        print("  ends UNKNOWN. Add their directories to PATH (PMUX_MAKE_DIRS, or MAKE_DIRS in")
        print("  this file) or run from a shell that has them. NO evidence files were touched.")
        raise SystemExit(3)
    print("preflight OK: eqy/make/bash/sh/grep all reachable")


def run(args, cwd, timeout=600):
    try:
        p = subprocess.run(eqy_command() + args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env(), cwd=str(cwd))
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as ex:
        raw = ex.stdout or ""
        s = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        return 124, s + "\n[TIMEOUT]"


def stash_workdir(d: Path):


    if not d.exists():
        return
    QUAR.mkdir(parents=True, exist_ok=True)
    dst = QUAR / f"{d.name}_{int(time.time())}"
    try:
        shutil.move(str(d), str(dst))                                           
        print(f"      (stashed old workdir -> {dst.name})")
    except Exception as ex:
        print(f"      !! could not stash workdir: {ex}")


def exe_version(exe: Path) -> str:


    try:
        command = eqy_command() if exe == EQY else [str(exe)]
        p = subprocess.run(command + ["--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=90, env=env())
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return out.splitlines()[0][:90] if out else "unknown (no output)"
    except Exception as exc:                                                  
        return f"unknown ({type(exc).__name__})"


def verdict_of(rc, out) -> tuple:


    low = (out or "").lower()
    done_fail = "done (fail" in low or "rc=2" in low
    part_fail = ("failed to prove" in low) or ("unproven" in low)
    whole_ok = "successfully proved designs equivalent" in low
    why = (f"exit={rc} whole_design_sentence={whole_ok} "
           f"partition_failure={part_fail} done_fail={done_fail}")
    if rc is None:
        return "TIMEOUT_OR_CRASH", why
    if rc == 0 and whole_ok and not part_fail and not done_fail:
        return "PROVEN", why
    if done_fail or part_fail or rc != 0:
        return "FAIL_OR_UNPROVEN", why
    if "timeout" in low or "no configured strategy" in low:
        return "FAIL_OR_UNPROVEN", why
    return "UNKNOWN", why


def main():
    preflight()
    OUT.mkdir(parents=True, exist_ok=True)
    jobs, tag = work_set(sys.argv[1:])
    summary_path = OUT / f"summary_eqy{tag}.json"
    prev = {}
    if summary_path.exists():
        try:
            prev = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            prev = {}

    if not jobs:


        print(f"!! EQY{'-' + tag.strip('_').upper() if tag else ''}: 取到 0 个用例 —— 0/0 不是证明。"
              f"检查 --tier2/--entry/--hier 的取数路径是否还存在")
        raise SystemExit(5)

    rows = []
    all_proven = True
    for top, gold, gate in jobs:
        cfg = OUT / f"{top}.eqy"
        if not gold.exists() or not gate.exists():


            print(f"[{top}] SKIP — missing source: "
                  f"{gold if not gold.exists() else gate}")
            all_proven = False
            rows.append({"case": top, "exit": None, "eqy": "MISSING_SOURCE", "sec": 0})
            continue


        stash_workdir(OUT / top)


        depth = 12
        if tag in ("_tier2", "_hier"):
            cfg.write_text(CONFIG_TIER2.format(gold=gold.as_posix(),
                                               gate=gate.as_posix(),
                                               top=top, depth=depth),
                           encoding="ascii")
        else:
            cfg.write_text(CONFIG.format(gold=gold.as_posix(),
                                         gate=gate.as_posix(),
                                         top=top, depth=depth),
                           encoding="ascii")


        t_run = time.time()
        c2, o2 = run([cfg.name], OUT, 300 if tag else 900)
        sec = round(time.time() - t_run, 2)

        low = o2.lower()


        verdict, why = verdict_of(c2, o2)
        if verdict != "PROVEN":

            print(f"      verdict evidence: {why}")
        print(f"[{top}] exit={c2}  EQY verdict = {verdict}  wall = {sec}s")
        for l in [x for x in o2.splitlines() if x.strip()][-5:]:
            print("      ", l[:170])


        log = OUT / f"{top}.log" if not tag else OUT / f"{top}{tag}.log"
        prev_proven = any(
            r.get("case") == top and r.get("eqy") == "PROVEN"
            for r in prev.get("rows", [])
        )
        if verdict == "PROVEN" or not log.exists() or not prev_proven:
            log.write_text(o2, encoding="utf-8", errors="replace")
        else:
            fail_log = OUT / f"{top}.fail.log"
            fail_log.write_text(o2, encoding="utf-8", errors="replace")
            print(f"      !! non-PROVEN result — archived {top}.log kept intact, "
                  f"this run saved to {fail_log.name}")

        if verdict != "PROVEN":
            all_proven = False
        vacuous = None
        if tag in ("_tier2", "_hier", "_entry"):
            f = (ENTRY_FACTS if tag == "_entry" else TIER2_FACTS).get(top, {})


            if tag == "_entry":


                vacuous = (("FAIL: " + str(f["contradiction"])) if f.get("contradiction")
                           else (f.get("arms")
                                 or "FAIL: no entry facts computed for this case"))
                if vacuous.startswith("FAIL"):
                    all_proven = False
                    verdict = verdict + " BUT VACUOUS"
                rows.append({"case": top, "exit": c2, "eqy": verdict, "sec": sec,
                             "tier2_arms": vacuous})
                continue
            rw = f.get("rewritten")
            if f.get("identical") and rw:
                vacuous = (f"FAIL: the pass reported {rw} cell(s) rewritten but the "
                           f"two RTLIL arms are byte-identical")
            elif f.get("identical"):
                vacuous = "SELF_EQUAL (0-rewrite case: pass-through, not a proof of " \
                          "the optimisation)"
            elif not rw:
                vacuous = "FAIL: the two arms differ but the pass reported no rewrite " \
                          "(None = its summary line was not even parsed) -- something " \
                          "other than the pass changed the netlist"
            else:
                vacuous = f"MEANINGFUL (arms differ; pass reported {rw} rewrite(s))"
            if f.get("contradiction"):
                vacuous = "FAIL: " + str(f["contradiction"])
            if isinstance(vacuous, str) and vacuous.startswith("FAIL"):
                all_proven = False
                verdict = verdict + " BUT VACUOUS"
        rows.append({"case": top, "exit": c2, "eqy": verdict, "sec": sec,
                     "tier2_arms": vacuous})


    if tag in ("_tier2", "_hier", "_entry"):
        meaningful = [r["case"] for r in rows
                      if (r.get("tier2_arms") or "").startswith("MEANINGFUL")]
        if not meaningful:
            all_proven = False
            print(f"!! {tag or 'official'} 没有任何一例的两臂因这道 pass 而不同 —— 这一趟不构成对交付形态"
                  "的等价性验证（pass 没开火 / 产物不对），不能写成 PROVEN 归档")
        else:
            print(f"[{tag.strip('_')}] 真正构成验证的用例（两臂因 pass 不同）："
                  f"{', '.join(meaningful)}")


    if tag == "_entry" and ENTRY_TOOL.get("problems"):


        all_proven = False
        print(f"!! EQY-ENTRY: 产物绑不住交付物（{len(ENTRY_TOOL['problems'])} 条）——"
              f"这一份不能写成 PROVEN 归档")

    t2 = {t: v.get("exe") for t, v in TIER2_FACTS.items() if v.get("exe")}
    t2bin = {"path": sorted(set(t2.values()))[0] if t2 else None}
    if t2bin["path"] and tag in ("_tier2", "_entry"):


        from pmux_preflight import (built_arm_provenance,
                                    built_arm_provenance_problems)
        _pv = built_arm_provenance(t2bin["path"])
        t2bin["source_provenance"] = _pv
        _pp = built_arm_provenance_problems(_pv)
        for _x in _pp:
            print("[provenance] FAIL:", _x)
        if _pp:
            all_proven = False
    if t2bin["path"]:
        p = Path(t2bin["path"])
        t2bin.update({"mtime": time.strftime("%Y-%m-%d %H:%M:%S",
                                             time.localtime(p.stat().st_mtime)),
                      "bytes": p.stat().st_size})
    summary = {"tool": "EQY (YosysHQ)", "tool_path": str(EQY),


               "tool_version": exe_version(EQY), "yosys_version": exe_version(EQY.parent / "yosys.exe"),
               "rows": rows,
               "arms": {"_tier2": "gold = 自建 yosys(含主程序内 pass) 读官方 RTL 走前端链后的 "
                                  "RTLIL; gate = 同一份产物、同一条链、只多一行 "
                                  "pmux_opt_rtlil -rewrite 的 RTLIL -- 即官方要求的交付形态"
                                  "（write_rtlil 无损，两臂进 eqy 前只差那道 pass）",
                        "": "gold = rtl/official; gate = rtl/optimized (tier-1 源码级产物)",
                        "_hier": "gold/gate = rtl/hier 那对层次化 fixture（子模块里放可识别结构、"
                                  "顶层实例化两次）经发行套件 yosys + 包内 DLL 走同一条前端链后的"
                                  "RTLIL，两臂只差 pmux_opt_rtlil -rewrite",
                        "_entry": "gold = rtl/official 原文; gate = results/entry_fallback/<case>_tier2.v "
                                  "—— 提交的 Tcl 入口在 tier 1 被人为弄失败之后由 tier 2 写出的网表。"
                                  "**tier 2 在这里的确切含义是：发行套件 yosys + `plugin -i` 装载的同一份 "
                                  ".cc（C++ pass 在进程内跑）**，**不是**官方第 1 步要求的『编进主程序』形态"
                                  "——后者另有 --tier2 归档；两者是同一份源码的两种装载方式，不混称。"
                                  "（上一版这里写成『由 tier 2（编进主程序的 pass）写出』，与 "
                                  "verify_entry_fallback.py 实际执行的命令不符，已更正）"}.get(tag, tag),
               "tier2_binary": t2bin if t2 else None,
               "tier2_facts": {t: {k: v for k, v in f.items() if k != "exe"}
                               for t, f in TIER2_FACTS.items()} or None,
               "entry_facts": ENTRY_FACTS or None,
               "entry_product_provenance": ENTRY_TOOL or None,
               "total_sec": round(sum(float(r.get("sec", 0)) for r in rows), 2)}
    if all_proven:
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    else:

        draft = OUT / f"summary_eqy{tag}.draft.json"
        draft.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"!! not all cases PROVEN — archived summary_eqy.json kept intact, "
              f"this run's summary saved to {draft.name}")

    n_proven = sum(1 for r in rows if r["eqy"] == "PROVEN")
    n_mean = sum(1 for r in rows
                 if (r.get("tier2_arms") or "").startswith("MEANINGFUL"))
    n_self = sum(1 for r in rows
                 if (r.get("tier2_arms") or "").startswith("SELF_EQUAL"))
    print(f"EQY-{(tag or 'OFFICIAL').strip('_').upper()}: "
          f"{'OK' if all_proven else 'FAIL'} proven={n_proven}/{len(rows)} "
          f"meaningful={n_mean} self_equal={n_self}")
    print("\n=== EQY summary ===")
    for r in rows:
        print(f"  {r['case']}: {r['eqy']} (exit={r['exit']})")
    if not all_proven:
        raise SystemExit(2)
    return rows


def tool_selftest() -> int:


    import tempfile
    bad = 0
    tmp = Path(tempfile.mkdtemp(prefix="eqy_resolve_"))
    a = tmp / "explicit" / "bin"
    b = tmp / "onpath" / "bin"
    for d in (a, b):
        d.mkdir(parents=True, exist_ok=True)
        (d / "eqy.exe").write_text("stub\n", encoding="utf-8")
    keep = os.environ.get("PMUX_EQY")
    try:
        for why, env_eqy, dirs, want in (
                ("explicit PMUX_EQY wins over the directory list", str(a / "eqy.exe"),
                 [str(b)], "explicit"),
                ("no PMUX_EQY: the first directory containing eqy.exe is chosen", "",
                 [str(b)], "onpath"),
                ("PMUX_EQY naming a MISSING file must not fall back to a guess",
                 str(tmp / "gone.exe"), [str(b), str(a)], None),
                ("nothing anywhere -> None, so preflight exits 3 instead of running a literal",
                 "", [], None)):
            if env_eqy:
                os.environ["PMUX_EQY"] = env_eqy
            else:
                os.environ.pop("PMUX_EQY", None)
            if not dirs:                                                                         
                real_which, shutil.which = shutil.which, lambda *k, **kw: None
            got = resolve_eqy(dirs)
            if not dirs:
                shutil.which = real_which
            if want == "explicit":
                ok = got == a / "eqy.exe"
            elif want == "onpath":
                ok = got == b / "eqy.exe"
            elif want is None:
                ok = got is None
            else:
                ok = False
            print(f"  [{'OK  ' if ok else 'FAIL'}] {why}: got={got}")
            bad += 0 if ok else 1


        dirs = path_dirs()
        ok = (EQY is None) or (str(EQY.parent) in dirs and EQY.is_file())
        print(f"  [{'OK  ' if ok else 'FAIL'}] executed eqy ({EQY}) is inside the list preflight "
              f"searched ({len(dirs)} dirs)")
        bad += 0 if ok else 1


        src_lines = Path(__file__).read_text(encoding="utf-8").splitlines()
        cut = next(i for i, ln in enumerate(src_lines) if ln.startswith("def tool_selftest"))
        above = "\n".join(src_lines[:cut])
        res = [n for n in ('str(SUITE / "bin" / "eqy.exe")', "\nEQY = SUITE") if n in above]
        print(f"  [{'OK  ' if not res else 'FAIL'}] no literal `SUITE/bin/eqy.exe` execution path "
              f"came back above the self-test{'; found ' + str(res) if res else ''}")
        bad += 1 if res else 0
    finally:
        if keep is None:
            os.environ.pop("PMUX_EQY", None)
        else:
            os.environ["PMUX_EQY"] = keep
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"EQY-RESOLVE-SELFTEST: {6 - bad}/6")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        raise SystemExit(tool_selftest())
    main()
