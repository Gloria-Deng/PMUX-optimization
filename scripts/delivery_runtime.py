
from __future__ import annotations

from contextlib import contextmanager
import atexit
import ctypes
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=None)
def temporary_for_yosys(scratch: Path) -> str:

    scratch.mkdir(parents=True, exist_ok=True)
    if not any(char.isspace() for char in str(scratch)):
        return str(scratch)
    bases = [Path(tempfile.gettempdir()), Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp"]
    for base in bases:
        try:
            directory = Path(tempfile.mkdtemp(prefix="pmux_", dir=base))
        except OSError:
            continue
        selected = str(directory)
        if any(char.isspace() for char in selected) and os.name == "nt":
            get_short = ctypes.windll.kernel32.GetShortPathNameW
            get_short.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
            get_short.restype = ctypes.c_uint32
            buffer = ctypes.create_unicode_buffer(32768)
            if get_short(selected, buffer, len(buffer)):
                selected = buffer.value
        if not any(char.isspace() for char in selected):
            def remove_empty(path=directory):
                try:
                    path.rmdir()
                except OSError:
                    pass                                                     
            atexit.register(remove_empty)
            return selected
        directory.rmdir()
    raise RuntimeError("ABC9 requires a writable temporary directory without spaces")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_env(scratch: Path) -> dict:
    scratch.mkdir(parents=True, exist_ok=True)
    system = os.environ.get("SystemRoot", r"C:\Windows")
    temporary = temporary_for_yosys(scratch)
    return {"SystemRoot": system, "windir": system,
            "PATH": os.pathsep.join([str(Path(system) / "System32"), system]),
            "TEMP": temporary, "TMP": temporary}


@contextmanager
def packaged_arms():


    bundle = ROOT / "binary"
    delivered = Path(os.environ.get("PMUX_DELIVERED_YOSYS", str(bundle / "yosys.exe"))).resolve()
    baseline = Path(os.environ.get("PMUX_STOCK_YOSYS", str(bundle / "baseline" / "yosys.exe"))).resolve()
    for path in (delivered, baseline):
        if not path.is_file():
            raise FileNotFoundError(f"Yosys executable absent: {path}")
    if sha256(delivered) == sha256(baseline):
        raise ValueError("baseline and delivered binaries must be different")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="delivery_runtime_", dir=build)).resolve()
    try:
        for source in bundle.iterdir():
            if source.is_file() and source.suffix.lower() in (".exe", ".dll"):
                shutil.copy2(source, stage / source.name)
        shutil.copytree(bundle / "share", stage / "share")
        staged_stock = stage / "yosys_stock.exe"
        shutil.copy2(baseline, staged_stock)


        stock = baseline if "PMUX_STOCK_YOSYS" in os.environ else staged_stock
        yield {"stock": stock, "delivered": delivered}, clean_env(stage / "tmp")
    finally:
        if not stage.is_relative_to(build.resolve()) or not stage.name.startswith("delivery_runtime_"):
            raise RuntimeError(f"refusing to remove scratch outside build/: {stage}")
        shutil.rmtree(stage)
