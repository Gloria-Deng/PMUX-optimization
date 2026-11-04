#!/usr/bin/env python3


from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

PROBE_VERILOG = "module pmux_probe(input a, b, output y); assign y = a & b; endmodule\n"


OFFICIAL_CASES = ("test1", "test2", "test3", "test4")

PROBE_SCRIPT = """read_verilog {v}
hierarchy -check -top pmux_probe
proc
opt -fast
stat
"""


PACKAGE_SKIP_DIRS = frozenset({"__pycache__", "build", "workdir_archive", "arms_log", "logs",
                              ".git", ".mimosa"})


PACKAGE_SKIP_FILES = ("*.draft.json",)


def delivered_files(root: Path, skip=frozenset(), anchor=None):


    a = Path(anchor) if anchor is not None else Path(root)
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file():
            continue
        if skip and any(part in skip for part in p.relative_to(a).parts[:-1]):
            continue
        if any(fnmatch.fnmatch(p.name, pat) for pat in PACKAGE_SKIP_FILES):
            continue
        yield p


def suite_root(fallback: Optional[Path] = None) -> Path:

    env = os.environ.get("OSS_CAD_SUITE")
    if env and Path(env).exists():
        return Path(env)
    if fallback is not None:
        return Path(fallback)
    return Path(r"E:\Yosys\oss-cad-suite\oss-cad-suite")


def tool_env(suite: Path) -> dict:

    e = os.environ.copy()
    e["YOSYSHQ_ROOT"] = str(suite)
    e["PATH"] = f"{suite / 'bin'};{suite / 'lib'};" + e.get("PATH", "")
    return e


def _self_env(yosys: Path) -> dict:

    e = os.environ.copy()
    e.pop("YOSYSHQ_ROOT", None)
    e["PATH"] = str(yosys.parent) + os.pathsep + e.get("PATH", "")
    return e


def _run(cmd, env, timeout, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, env=env, cwd=cwd)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as ex:
        raw = ex.stdout or ""
        s = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        return 124, s + "\n[TIMEOUT]"
    except Exception as ex:
        return None, str(ex)


def yosys_probe(yosys: Path, suite: Optional[Path] = None,
                env: Optional[dict] = None, timeout: int = 120,
                cwd: Optional[Path] = None) -> None:


    tmp = Path(tempfile.mkdtemp(prefix="pmux_probe_"))
    work = Path(cwd) / "pmux_probe_tmp" if cwd is not None else tmp
    if cwd is not None:
        work.mkdir(parents=True, exist_ok=True)
    try:
        v = work / "probe.v"
        ys = work / "probe.ys"
        v.write_text(PROBE_VERILOG, encoding="ascii")
        ys.write_text(PROBE_SCRIPT.format(v=v.as_posix()), encoding="ascii")

        run_env = env if env is not None else tool_env(suite or suite_root())
        run_cwd = str(cwd) if cwd is not None else str(tmp)
        code, out = _run([str(yosys), "-s", ys.as_posix()], run_env, timeout, run_cwd)
        ok = (code == 0 and "pmux_probe" in out and "ERROR" not in out
              and "End of script" in out)
        if not ok:
            print("PREFLIGHT FAIL - yosys cannot complete a minimal synthesis under "
                  "the caller's environment:", yosys)
            print("  ", out.strip().replace("\n", "\n   ")[:400]
                  or "(no output; missing DLLs / share dir?)")

            dcode, banner = _run([str(yosys), "-V"], _self_env(yosys), timeout)
            if dcode != 0 or "Yosys" not in banner:
                print("  diagnosis: binary cannot start standalone (missing DLLs?)")
            else:
                print("  diagnosis: binary starts but cannot do work (share/ dir missing?)")
            print("  NO evidence files were touched.")
            print("  Fix OSS_CAD_SUITE / PMUX_YOSYS / PATH and rerun.")
            raise SystemExit(3)
        print(f"preflight OK: yosys runs a minimal synthesis -> {yosys}")
    finally:

        for d in {tmp, work}:
            try:
                if d.exists():
                    shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass


import ctypes as _ct
import ctypes.wintypes as _wt
import subprocess as _sp
import time as _time


class _JobBasicAccounting(_ct.Structure):


    _fields_ = [
        ("TotalUserTime", _ct.c_longlong),
        ("TotalKernelTime", _ct.c_longlong),
        ("ThisTimeTotalUserTime", _ct.c_longlong),
        ("ThisTimeTotalKernelTime", _ct.c_longlong),
        ("TotalPageFaultCount", _wt.DWORD),
        ("TotalProcesses", _wt.DWORD),
        ("ActiveProcesses", _wt.DWORD),
        ("TotalTerminatedProcesses", _wt.DWORD),
    ]


class _JobBasicLimit(_ct.Structure):


    _fields_ = [
        ("PerProcessUserTimeLimit", _ct.c_longlong),
        ("PerJobUserTimeLimit", _ct.c_longlong),
        ("LimitFlags", _wt.DWORD),
        ("MinimumWorkingSetSize", _ct.c_size_t),
        ("MaximumWorkingSetSize", _ct.c_size_t),
        ("ActiveProcessLimit", _wt.DWORD),
        ("Affinity", _ct.c_void_p),
        ("PriorityClass", _wt.DWORD),
        ("SchedulingClass", _wt.DWORD),
    ]


class _IoCounters(_ct.Structure):
    _fields_ = [
        ("ReadOperationCount", _ct.c_ulonglong),
        ("WriteOperationCount", _ct.c_ulonglong),
        ("OtherOperationCount", _ct.c_ulonglong),
        ("ReadTransferCount", _ct.c_ulonglong),
        ("WriteTransferCount", _ct.c_ulonglong),
        ("OtherTransferCount", _ct.c_ulonglong),
    ]


class _JobExtendedLimit(_ct.Structure):


    _fields_ = [
        ("BasicLimitInformation", _JobBasicLimit),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", _ct.c_size_t),
        ("JobMemoryLimit", _ct.c_size_t),
        ("PeakProcessMemoryUsed", _ct.c_size_t),
        ("PeakJobMemoryUsed", _ct.c_size_t),
    ]


_JOB_BASIC_ACCOUNTING = 1                                   
_JOB_EXTENDED_LIMIT = 9                                                           
_ticks = _ct.sizeof(_ct.c_longlong) and 1e7                    


def _kernel32():
    k32 = _ct.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = _wt.HANDLE
    k32.CreateJobObjectW.argtypes = [_ct.c_void_p, _ct.c_wchar_p]
    k32.AssignProcessToJobObject.restype = _wt.BOOL
    k32.AssignProcessToJobObject.argtypes = [_wt.HANDLE, _wt.HANDLE]
    k32.QueryInformationJobObject.restype = _wt.BOOL
    k32.QueryInformationJobObject.argtypes = [_wt.HANDLE, _ct.c_int, _ct.c_void_p,
                                              _wt.DWORD, _ct.POINTER(_wt.DWORD)]
    k32.TerminateJobObject.restype = _wt.BOOL
    k32.TerminateJobObject.argtypes = [_wt.HANDLE, _wt.UINT]
    k32.SetProcessAffinityMask.restype = _wt.BOOL
    k32.SetProcessAffinityMask.argtypes = [_wt.HANDLE, _wt.DWORD]
    k32.CloseHandle.restype = _wt.BOOL
    k32.CloseHandle.argtypes = [_wt.HANDLE]


    k32.OpenProcess.restype = _wt.HANDLE
    k32.OpenProcess.argtypes = [_wt.DWORD, _wt.BOOL, _wt.DWORD]
    k32.QueryProcessCycleTime.restype = _wt.BOOL
    k32.QueryProcessCycleTime.argtypes = [_wt.HANDLE, _ct.POINTER(_ct.c_ulonglong)]
    return k32


def _job_process_ids(k32, job) -> list:


    buf = _ct.create_string_buffer(8 + 4 * 128)
    got = _wt.DWORD(0)
    if not k32.QueryInformationJobObject(_wt.HANDLE(job), 3, buf, _ct.sizeof(buf),
                                         _ct.byref(got)):
        return []
    d = _ct.cast(buf, _ct.POINTER(_wt.DWORD))
    in_list = d[1]
    if in_list > 128:
        return []
    return [d[2 + i] for i in range(in_list)]


_CYCLE_POLL_S = 0.005                                                                  


_SHELL_WRAPPER_IMAGES = {"cmd.exe", "sh.exe", "bash.exe", "conhost.exe"}


def _process_image_basename(k32, handle) -> str:

    api = _ct.WinDLL("kernel32", use_last_error=True).QueryFullProcessImageNameW
    api.restype = _wt.BOOL
    api.argtypes = [_wt.HANDLE, _wt.DWORD, _wt.LPWSTR, _ct.POINTER(_wt.DWORD)]
    buf = _ct.create_unicode_buffer(1024)
    n = _wt.DWORD(_ct.sizeof(buf) // 2)
    if api(_wt.HANDLE(handle), 0, buf, _ct.byref(n)):
        return buf.value.replace("/", "\\").split("\\")[-1].lower()
    return ""


def calibrate_cycles_per_second() -> Optional[float]:


    global _CYCLES_PER_SECOND
    if _CYCLES_PER_SECOND:
        return _CYCLES_PER_SECOND
    rc, _out, _err, m = tree_cpu_run(
        [sys.executable, "-c", "import time\nt=time.time()\nwhile time.time()-t<0.4: pass"],
        timeout=60)
    cyc = m.get("cpu_tree_cycles")
    wall = m.get("wall_s")
    if rc == 0 and cyc and wall and wall > 0.2:
        _CYCLES_PER_SECOND = cyc / wall
    return _CYCLES_PER_SECOND


_CYCLES_PER_SECOND = None


def built_yosys_env(exe) -> dict:


    import os as _os
    from pathlib import Path as _P
    exe = _P(exe)
    e = _os.environ.copy()
    roots = []
    for root in (r"E:\msys64", r"C:\msys64"):
        for sub in ("ucrt64/bin", "ucrt64/lib", "usr/bin"):
            d = _P(root) / sub
            if d.is_dir():
                roots.append(str(d))
    roots.append(str(exe.parent))
    e["PATH"] = _os.pathsep.join(roots + [e.get("PATH", "")])
    for cand in (exe.parent / "share" / "yosys", exe.parent.parent / "share" / "yosys"):
        if cand.is_dir():
            e["YO_SHARE_PATH"] = str(cand)
            break
    return e


BUILT_PASS_SUBDIR = ("passes", "pmux_opt")                                           


def _sha256(path: Path, chars: int = 16) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()[:chars]


def built_arm_provenance(exe, tree=None) -> dict:


    from pathlib import Path as _P
    exe = _P(exe)
    repo_cc = _P(__file__).resolve().parent.parent / "plugin" / "pmux_opt_rtlil.cc"
    prov = {"repo_cc": str(repo_cc),
            "repo_cc_sha256": _sha256(repo_cc) if repo_cc.is_file() else None,
            "exe": str(exe),
            "exe_sha256": _sha256(exe) if exe.is_file() else None,
            "exe_bytes": (exe.stat().st_size if exe.is_file() else None),
            "exe_mtime": (exe.stat().st_mtime if exe.is_file() else None),
            "tree_src": None,
            "tree_cc": None,
            "tree_cc_sha256": None}
    if tree is None:
        try:                                                                              
            from build_pass_into_yosys import _find_tree
            found = _find_tree()
            tree = found if found else None
        except Exception:                                                                   
            tree = None
    if tree:
        copy = _P(tree) / _P(*BUILT_PASS_SUBDIR) / "pmux_opt_rtlil.cc"
        prov["tree_src"] = str(tree)
        prov["tree_cc"] = str(copy)
        prov["tree_cc_sha256"] = _sha256(copy) if copy.is_file() else None
        prov["tree_cc_mtime"] = (copy.stat().st_mtime if copy.is_file() else None)


    import re as _re
    cache = exe.parent / "CMakeCache.txt"
    prov["cache_home"] = None
    if cache.is_file():
        m = _re.search(r"^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$",
                       cache.read_text(encoding="utf-8", errors="replace"), _re.M)
        prov["cache_home"] = m.group(1).strip().replace("\\", "/") if m else None
    objs = sorted(exe.parent.glob("passes/pmux_opt/CMakeFiles/*/*.obj"))


    mine = [o for o in objs if o.name == "pmux_opt_rtlil.cc.obj"]
    prov["obj"] = str(mine[0]) if mine else None
    prov["obj_mtime"] = (mine[0].stat().st_mtime if mine else None)
    prov["n_objs"] = len(objs)
    prov["n_objs_matching"] = len(mine)
    if objs and not mine:
        prov["obj_ambiguous"] = (
            f"{len(objs)} object(s) under passes/pmux_opt/CMakeFiles but none named "
            f"pmux_opt_rtlil.cc.obj ({[o.name for o in objs][:4]}) -- the build holds no "
            f"compiled copy of the pass we ship, so any mtime tie-down would be judging "
            f"someone else's object file")
    return prov


def built_arm_provenance_problems(prov: dict) -> list:

    p = []
    if prov.get("obj_ambiguous"):
        p.append(prov["obj_ambiguous"])
    if not prov.get("repo_cc_sha256"):
        p.append("cannot hash plugin/pmux_opt_rtlil.cc in this repo")
    if not prov.get("exe_sha256"):
        p.append("cannot hash the self-built yosys.exe that was measured")
    if not prov.get("tree_src"):
        p.append("no yosys source tree found (PMUX_YOSYS_SRC) -- the tag arm's binary "
                 "cannot be tied to any source, so its numbers are UNVERIFIED and must "
                 "not be quoted")
    elif not prov.get("tree_cc_sha256"):
        p.append(f"{prov.get('tree_cc')} is missing: the tree no longer holds the copy "
                 f"the exe was built from")
    elif prov["tree_cc_sha256"] != prov.get("repo_cc_sha256"):
        p.append(f"the tree copy {prov['tree_cc_sha256']} != repo "
                 f"{prov['repo_cc_sha256']}: the self-built exe was compiled from a "
                 f"DIFFERENT pass source than the one being delivered")
    elif (prov.get("exe_mtime") and prov.get("tree_cc_mtime")
            and prov["exe_mtime"] < prov["tree_cc_mtime"]):


        p.append("the exe predates the tree copy of the pass (exe mtime %s < source %s): "
                 "it was never rebuilt after the source it is being matched to"
                 % (prov["exe_mtime"], prov["tree_cc_mtime"]))
    if prov.get("tree_src"):
        if not prov.get("cache_home"):
            p.append("no CMakeCache.txt beside the measured exe: cannot tell WHICH source tree "
                     "built it (this machine has more than one build directory)")
        else:
            from pathlib import Path as _P2
            if _P2(prov["cache_home"]).resolve() != _P2(prov["tree_src"]).resolve():
                p.append(f"the exe was configured from {prov['cache_home']}, but the pass source "
                         f"we hashed came from {prov['tree_src']} -- binary and source belong to "
                         f"different builds")
    if (prov.get("obj_mtime") and prov.get("tree_cc_mtime")
            and prov["obj_mtime"] < prov["tree_cc_mtime"]):
        p.append("the compiled object predates the tree copy of the pass (obj %s < source %s): "
                 "ninja skipped the translation unit, so the relink carries older CODE than the "
                 "source it is matched to" % (prov["obj_mtime"], prov["tree_cc_mtime"]))
    elif prov.get("tree_cc") and not prov.get("obj"):
        p.append("no pmux_opt object file under the build directory: the measured exe cannot be "
                 "tied to a compiled copy of our pass at all")
    return p


PROVENANCE_HEALTHY = {
    "repo_cc": "D:/pmux_fixture/repo/plugin/pmux_opt_rtlil.cc",
    "repo_cc_sha256": "aaa111",
    "exe": "D:/pmux_fixture/build/yosys.exe",
    "exe_sha256": "ccc333",
    "exe_bytes": 1,
    "exe_mtime": 200.0,
    "tree_src": "D:/pmux_fixture/tree",
    "tree_cc": "D:/pmux_fixture/tree/passes/pmux_opt/pmux_opt_rtlil.cc",
    "tree_cc_sha256": "aaa111",
    "tree_cc_mtime": 100.0,
    "cache_home": "D:/pmux_fixture/tree",
    "obj": "D:/pmux_fixture/build/passes/pmux_opt/CMakeFiles/x.dir/pmux_opt_rtlil.cc.obj",
    "obj_mtime": 200.0,
    "n_objs": 1,
    "n_objs_matching": 1,
}


PROVENANCE_RULE_CASES = (
    ("object(s) under passes/pmux_opt/CMakeFiles",
     {"obj_ambiguous": "2 object(s) under passes/pmux_opt/CMakeFiles but none named "
                       "pmux_opt_rtlil.cc.obj"}, True),
    ("cannot hash plugin/", {"repo_cc_sha256": None}, True),
    ("cannot hash the self-built", {"exe_sha256": None}, True),
    ("no yosys source tree found", {"tree_src": None}, True),
    ("is missing: the tree no longer holds", {"tree_cc_sha256": None}, True),
    ("DIFFERENT pass source", {"tree_cc_sha256": "bbb222"}, True),
    ("the exe predates the tree copy", {"exe_mtime": 50.0}, True),
    ("no CMakeCache.txt beside", {"cache_home": None}, True),
    ("different builds", {"cache_home": "D:/pmux_fixture/other_tree"}, True),
    ("the compiled object predates", {"obj_mtime": 50.0}, True),
    ("no pmux_opt object file", {"obj": None}, True),
)


def provenance_fixture() -> dict:

    return dict(PROVENANCE_HEALTHY)


def provenance_rule_census() -> tuple[int, int, list, list]:


    import inspect
    import re as _re
    src = inspect.getsource(built_arm_provenance_problems)
    sites = len(_re.findall(r"p\.append\(", src))
    misses = []
    problems = []
    for sub, mut, _want in PROVENANCE_RULE_CASES:
        got = built_arm_provenance_problems({**PROVENANCE_HEALTHY, **mut})
        problems.append(f"{sub}: {len(got)}")
        if not any(sub in m for m in got):
            misses.append(f"case {sub!r} does not trigger its rule (got {got[:1]})")
    healthy = built_arm_provenance_problems(dict(PROVENANCE_HEALTHY))
    if healthy:
        misses.append(f"the HEALTHY fixture is not healthy: {healthy}")
    return sites, len(PROVENANCE_RULE_CASES), misses, healthy


BUILT_EVIDENCE = (
    ("results/eval_eqy/summary_eqy_tier2.json", ("tier2_binary", "source_provenance")),
    ("results/flow_span/summary.json", ("built_arm_provenance",)),


    ("results/flow_span/summary_probe_all.json", ("built_arm_provenance",)),
    ("results/gate_probes/summary_built_arm.json", ("source_provenance",)),
    ("results/built_yosys/summary.json", ("source_provenance",)),


    ("results/sim/built_arm.json", ("source_provenance",)),
)


def stale_built_evidence(root: Path, exe_sha: str | None) -> list[str]:

    out = []
    if not exe_sha:
        return ["cannot hash the exe being verified -- no evidence can be tied to it"]
    for rel, keys in BUILT_EVIDENCE:
        p = root / rel
        if not p.is_file():
            out.append(f"{rel}: missing (the docs may not cite built-arm results from it)")
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:                                          
            out.append(f"{rel}: unreadable ({type(exc).__name__})")
            continue
        seen = None
        for k in keys:
            v = doc.get(k)
            if isinstance(v, dict):
                seen = v.get("exe_sha256") or seen
                inner = v.get("source_provenance")
                if isinstance(inner, dict):
                    seen = inner.get("exe_sha256") or seen
        if seen is None:
            out.append(f"{rel}: records no exe sha -- written before the provenance gate; "
                       f"re-run the step")
        elif seen != exe_sha:
            out.append(f"{rel}: cites exe {seen} but the delivered self-built exe is {exe_sha} "
                       f"-- this evidence describes an OLDER binary; re-run that step")
    return out


def format_provenance(prov: dict) -> str:
    return ("prov repo=%s tree=%s exe=%s (%s B)"
            % (prov.get("repo_cc_sha256"), prov.get("tree_cc_sha256") or "ABSENT",
               prov.get("exe_sha256"), prov.get("exe_bytes")))


def process_peak_working_set(handle):

    class Counters(_ct.Structure):
        _fields_ = [("cb", _wt.DWORD), ("PageFaultCount", _wt.DWORD)] + [
            (name, _ct.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                "PagefileUsage", "PeakPagefileUsage")]
    api = _ct.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    api.argtypes = [_wt.HANDLE, _ct.POINTER(Counters), _wt.DWORD]
    api.restype = _wt.BOOL
    info = Counters()
    info.cb = _ct.sizeof(info)
    if api(_wt.HANDLE(handle), _ct.byref(info), info.cb):
        return int(info.PeakWorkingSetSize)
    return None


def tree_cpu_run(cmd, cwd=None, env=None, timeout=None, pin_cpu=None, high_priority=False):


    m = {"wall_s": None, "cpu_tree_s": None, "cpu_user_s": None, "cpu_kernel_s": None,
         "tree_processes": None, "job_error": None,
         "peak_job_mem_mb": None, "peak_proc_mem_mb": None, "mem_job_error": None,
         "peak_main_working_set_mb": None, "peak_main_working_set_bytes": None,
         "cpu_user_100ns": None, "cpu_kernel_100ns": None,
         "cpu_tree_cycles": None, "cpu_cycles_by_pid": None, "procs_with_cycles": None,
         "working_set_measurement": "GetProcessMemoryInfo.PeakWorkingSetSize (same run)"}
    if _ct.sizeof(_JobBasicAccounting) != 48:
        m["job_error"] = "BASIC_ACCOUNTING size %d != 48" % _ct.sizeof(_JobBasicAccounting)
        return None, "", "", m
    try:
        k32 = _kernel32()
    except OSError as ex:
        m["job_error"] = "kernel32: %s" % ex
        return None, "", "", m
    job = k32.CreateJobObjectW(None, None)
    if not job:
        m["job_error"] = "CreateJobObjectW err=%d" % _ct.get_last_error()
        return None, "", "", m
    out = err = ""
    rc = None
    try:
        p = _sp.Popen(cmd, cwd=cwd, env=env, stdout=_sp.PIPE, stderr=_sp.PIPE,
                      text=True, encoding="utf-8", errors="replace",
                      creationflags=(0x00008000 if high_priority else 0))
        if pin_cpu is not None:
            k32.SetProcessAffinityMask(_wt.HANDLE(p._handle), 1 << int(pin_cpu))
        if not k32.AssignProcessToJobObject(_wt.HANDLE(job), p._handle):


            m["job_error"] = "Assign err=%d" % _ct.get_last_error()
            out, err = p.communicate()
            return p.returncode, out, err, m
        t0 = _time.perf_counter()
        import threading
        stop_memory = threading.Event()
        main_peaks = []


        stop_cycles = threading.Event()
        cycle_handles = []                                                             
        seen_pids = set()
        k32c = k32

        def collect_cycle_handles():
            while not stop_cycles.is_set():
                for pid in _job_process_ids(k32c, job):
                    if pid and pid not in seen_pids:
                        seen_pids.add(pid)
                        if pid != p.pid:
                            h = k32c.OpenProcess(0x1000, False, pid)                                     
                            if h:
                                cycle_handles.append((pid, int(h)))
                stop_cycles.wait(_CYCLE_POLL_S)

        def collect_memory():
            while True:
                peak = process_peak_working_set(p._handle)
                if peak is not None:
                    main_peaks.append(peak)
                if stop_memory.wait(0.005):
                    break

        memory_thread = threading.Thread(target=collect_memory, daemon=True)
        cycle_thread = threading.Thread(target=collect_cycle_handles, daemon=True)
        memory_thread.start()
        cycle_thread.start()
        try:
            out, err = p.communicate(timeout=timeout)
        except _sp.TimeoutExpired:
            k32.TerminateJobObject(_wt.HANDLE(job), 1)
            out, err = p.communicate()
            m["job_error"] = "timeout; job terminated"
            m["wall_s"] = _time.perf_counter() - t0
            return p.returncode, out, err, m
        finally:
            stop_memory.set()
            memory_thread.join()
            peak = process_peak_working_set(p._handle)
            if peak is not None:
                main_peaks.append(peak)
            if main_peaks:
                m["peak_main_working_set_bytes"] = max(main_peaks)
                m["peak_main_working_set_mb"] = max(main_peaks) / 1048576.0
        m["wall_s"] = _time.perf_counter() - t0
        rc = p.returncode
        acc = _JobBasicAccounting()
        got = _wt.DWORD(0)
        if not k32.QueryInformationJobObject(_wt.HANDLE(job), _JOB_BASIC_ACCOUNTING,
                                             _ct.byref(acc), _ct.sizeof(acc),
                                             _ct.byref(got)):
            m["job_error"] = "query err=%d" % _ct.get_last_error()
            return rc, out, err, m
        u = acc.TotalUserTime / _ticks
        k = acc.TotalKernelTime / _ticks
        m.update({"cpu_user_s": u, "cpu_kernel_s": k,
                  "cpu_user_100ns": int(acc.TotalUserTime),
                  "cpu_kernel_100ns": int(acc.TotalKernelTime),
                  "cpu_tree_s": (acc.TotalUserTime + acc.TotalKernelTime) / _ticks,
                  "tree_processes": int(acc.TotalProcesses)})


        stop_cycles.set()
        cycle_thread.join(timeout=2)
        per_pid = {}
        cval = _ct.c_ulonglong(0)
        if k32c.QueryProcessCycleTime(_wt.HANDLE(p._handle), _ct.byref(cval)):
            per_pid[p.pid] = cval.value
        for pid, h in cycle_handles:
            name = _process_image_basename(k32c, h)
            if name in _SHELL_WRAPPER_IMAGES:
                k32c.CloseHandle(_wt.HANDLE(h))
                continue
            cval = _ct.c_ulonglong(0)
            if k32c.QueryProcessCycleTime(_wt.HANDLE(h), _ct.byref(cval)):
                per_pid[pid] = cval.value
            k32c.CloseHandle(_wt.HANDLE(h))
        if per_pid:
            m["cpu_cycles_by_pid"] = {str(k_): v for k_, v in sorted(per_pid.items())}
            m["cpu_tree_cycles"] = int(sum(per_pid.values()))
            m["procs_with_cycles"] = len(per_pid)


        if _ct.sizeof(_JobExtendedLimit) != 144:
            m["mem_job_error"] = ("EXTENDED_LIMIT size %d != 144"
                                  % _ct.sizeof(_JobExtendedLimit))
            return rc, out, err, m
        ext = _JobExtendedLimit()
        if not k32.QueryInformationJobObject(_wt.HANDLE(job), _JOB_EXTENDED_LIMIT,
                                             _ct.byref(ext), _ct.sizeof(ext),
                                             _ct.byref(got)):
            m["mem_job_error"] = "class 9 query err=%d" % _ct.get_last_error()
            return rc, out, err, m
        m["peak_job_mem_mb"] = ext.PeakJobMemoryUsed / 1048576.0
        m["peak_proc_mem_mb"] = ext.PeakProcessMemoryUsed / 1048576.0
        return rc, out, err, m
    finally:
        k32.CloseHandle(_wt.HANDLE(job))


_SELFTEST_BURN = """import sys, time
secs = float(sys.argv[1])
t = time.time()
while time.time() - t < secs:
    pass
"""

_SELFTEST_KIDS = """import os, subprocess, sys
burn = os.path.join(os.path.dirname(os.path.abspath(__file__)), "burn.py")
ps = [subprocess.Popen([sys.executable, burn, "0.3"]) for _ in range(2)]
[x.wait() for x in ps]
"""


_SELFTEST_ALLOC = """import sys, time
mb = int(sys.argv[1])
buf = bytearray(mb * 1024 * 1024)
for i in range(0, len(buf), 4096):
    buf[i] = 1
time.sleep(0.2)
"""


def tree_cpu_selftest() -> tuple[bool, str]:


    import shutil
    import sys
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="pmux_jobt_"))
    try:
        (d / "burn.py").write_text(_SELFTEST_BURN, encoding="utf-8")
        (d / "kids.py").write_text(_SELFTEST_KIDS, encoding="utf-8")
        (d / "alloc.py").write_text(_SELFTEST_ALLOC, encoding="utf-8")
        rc1, _o, e1, m1 = tree_cpu_run([sys.executable, str(d / "burn.py"), "0.5"],
                                       timeout=60)
        if m1["cpu_tree_s"] is None:
            return False, "burner unreadable: %s" % m1["job_error"]
        if rc1 != 0:
            return False, "burner rc=%s: %s" % (rc1, e1[-160:].replace("\n", " | "))
        if not 0.25 <= m1["cpu_tree_s"] <= 1.5:
            return False, "0.5 s burner measured as %s s" % m1["cpu_tree_s"]
        rc2, _o2, e2, m2 = tree_cpu_run([sys.executable, str(d / "kids.py")], timeout=60)
        if rc2 != 0:
            return False, "kids rc=%s: %s" % (rc2, e2[-160:].replace("\n", " | "))
        if (m2["tree_processes"] or 0) < 3:
            return False, ("parent+2 children seen as %s process(es) -- children escape "
                           "the job, cpu_tree_s would undercount" % m2["tree_processes"])

        rc3, _o3, e3, m3 = tree_cpu_run([sys.executable, str(d / "alloc.py"), "256"],
                                        timeout=120)
        if rc3 != 0:
            return False, "allocator rc=%s: %s" % (rc3, e3[-160:].replace("\n", " | "))
        pm = m3["peak_job_mem_mb"]
        if m3["mem_job_error"]:
            return False, "tree peak memory unreadable: %s" % m3["mem_job_error"]
        if pm is None or pm < 200.0:
            return False, ("a 256 MB-touching child read as %s MB -- the class-9 peak "
                           "would understate real usage" % pm)
        rc4, _o4, _e4, m4 = tree_cpu_run([sys.executable, "-c", "pass"], timeout=60)
        idle = m4["peak_job_mem_mb"]
        if rc4 != 0 or idle is None:
            return False, "idle control unreadable (rc=%s, peak=%s)" % (rc4, idle)
        if idle > pm / 4.0:
            return False, ("idle child read %s MB against a %s MB allocation -- the "
                           "reading is not tracking the workload" % (idle, pm))
        return True, ("burner %s s (wall %s), parent+2 children -> %s processes, "
                      "256 MB allocator -> %s MB tree peak (idle control %s MB)"
                      % (m1["cpu_tree_s"], m1["wall_s"], m2["tree_processes"], pm, idle))
    finally:
        shutil.rmtree(d, ignore_errors=True)
