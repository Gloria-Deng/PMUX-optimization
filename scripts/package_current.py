"""Create a genuine RAR submission, at most 200000000 bytes.

Delivery uses official Yosys 0.69+24 and the PMUX pass with original ABC9.
Videos and external OSS CAD Suite verification tools are excluded by default.
Every file is read from the archive and compared with its source. ZIP output
and --include-formal-tools are for local exchange only, not official upload.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
CACHE_DIRS = {"__pycache__", ".cache", "cache", "caches", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"}
TEMP_DIRS = {"runtime", "tmp", "temp", "_tmp"}
PLUGIN_FILES = ("pmux_opt_rtlil.cc", "synth_intel.cc.patched", "dffeas_formal.v")
MAX_SUBMISSION_BYTES = 200000000
VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv", ".m4v"}


def excluded_history(name):
    value = name.casefold()
    return (value.startswith("history") or value.startswith("历史") or "backup" in value
            or "备份" in value or value.endswith((".bak", ".backup", "~")))


def selected_tree(directory, *, history=False, results=False, suffixes=None, excluded_dirs=()):

    if not directory.is_dir():
        raise FileNotFoundError(f"Required directory absent: {directory}")
    for current, directories, files in os.walk(directory):
        directories[:] = sorted(name for name in directories
                                if name.casefold() not in CACHE_DIRS
                                and name.casefold() not in excluded_dirs
                                and not (history and excluded_history(name))
                                and not (results and (name.casefold() in TEMP_DIRS or name.casefold().endswith("_tmp"))))
        for name in sorted(files):
            path = Path(current) / name
            if path.suffix.casefold() in (".pyc", ".pyo"):
                continue
            if history and excluded_history(name):
                continue
            if results and path.suffix.casefold() in (".tmp", ".partial", ".part"):
                continue
            if suffixes is not None and path.suffix.casefold() not in suffixes:
                continue
            if path.is_file():
                yield path


def collect_files(assessment, efficiency, parameter_results=(), build_record_dirs=(), *,
                  include_formal_tools=False, require_full_score=False):

    from validation_support import validate_results
    validate_results(assessment.resolve(), efficiency.resolve(), require_full_score=require_full_score)
    from verify_shipped_binary import program_version_problems
    version_errors = program_version_problems(ROOT / "binary")
    if version_errors:
        raise RuntimeError("; ".join(version_errors))
    from patch_synth_intel_cc import is_applied, mapping_kind, read_keep_endings
    files, folded = {}, {}
    root = ROOT.resolve()

    def add(source, destination=None):
        source = Path(source).resolve()
        if source.suffix.casefold() in VIDEO_SUFFIXES:
            return
        if not source.is_file():
            raise FileNotFoundError(f"Required file absent: {source}")
        if destination is None:
            destination = source.relative_to(root)
        relative = PurePosixPath(Path(destination).as_posix())
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"Invalid archive path: {relative}")
        name = "submission/" + relative.as_posix()
        if name.casefold() in folded and folded[name.casefold()] != name:
            raise RuntimeError(f"Archive names differ only by letter case: {name}")
        if name in files and files[name] != source:
            raise RuntimeError(f"Two sources would occupy the same archive path: {name}")
        folded[name.casefold()] = name
        files[name] = source

    add(root / "README.md")
    for source in sorted(root.glob("*.md")):
        add(source)
    report = root / "docs" / "技术文档.pdf"
    if not report.is_file():
        raise FileNotFoundError(f"Required PDF report absent: {report}")
    if report.stat().st_size > 50000000:
        raise RuntimeError("The design report exceeds the official 50000000-byte PDF limit")
    add(report)
    editable_report = root / "docs" / "技术文档.docx"
    if editable_report.is_file():
        add(editable_report)
    for source in selected_tree(root / "docs", history=True, suffixes={".md"}):
        add(source)
    for name in PLUGIN_FILES:
        add(root / "plugin" / name)
    for directory in ("plugin", "cases", "results"):
        add(root / directory / "README.md")
    patches = list(selected_tree(root / "plugin", history=True, suffixes={".patch"}))
    if not any(source.name == "synth_intel_pass.patch" for source in patches):
        raise FileNotFoundError("Required source patch absent: plugin/synth_intel_pass.patch")
    for source in patches:
        if "area9" not in source.name.casefold():
            add(source)
    synth = read_keep_endings(root / "plugin" / "synth_intel.cc.patched")
    if not is_applied(synth, "pass") or mapping_kind(synth) != "stock":
        raise RuntimeError("Current source must contain the PMUX pass and original ABC9 command")
    for source in selected_tree(root / "scripts", suffixes={".py", ".ps1", ".cmd", ".cjs", ".v", ".il", ".md"}):
        add(source)
    for relative in ("licenses/yosys/COPYING", "licenses/abc/copyright.txt"):
        add(root / "binary" / relative)
    for source in selected_tree(root / "binary", excluded_dirs=() if include_formal_tools else {"formal"}):
        add(source)

    from evaluate_official_nine import CASES
    for _, source, _ in CASES:
        add(source)

    assessment, efficiency = assessment.resolve(), efficiency.resolve()
    for directory in (assessment, efficiency, *parameter_results):
        if directory.is_dir() and any(path.is_file() and path.name.upper().startswith("INVALID")
                                     for path in directory.iterdir()):
            raise RuntimeError(f"Result directory is marked invalid: {directory}")
    for relative in ("metrics.csv", "resources.csv", "formal.csv", "formal_ascii/control.txt"):
        if not (assessment / relative).is_file():
            raise FileNotFoundError(f"Current assessment is incomplete: {relative}")
    for relative in ("summary.csv", "readings.csv", "output_files.csv", "conditions.txt", "report.md"):
        if not (efficiency / relative).is_file():
            raise FileNotFoundError(f"Current efficiency result is incomplete: {relative}")
    result_roots = []
    for directory in (assessment, efficiency, *parameter_results):
        directory = directory.resolve()
        if any(directory == source for source, _ in result_roots):
            continue
        containing = next(((source, destination) for source, destination in result_roots
                           if directory.is_relative_to(source)), None)
        if containing:
            destination = containing[1] / directory.relative_to(containing[0])
        elif directory.is_relative_to(root / "results"):
            destination = Path("results") / directory.relative_to(root / "results")
        else:
            destination = Path("results") / directory.name
        result_roots.append((directory, destination))
        for source in selected_tree(directory, results=True):
            add(source, destination / source.relative_to(directory))

    for directory in build_record_dirs:
        directory = directory.resolve()
        destination = (Path("results") / directory.relative_to(root / "results")
                       if directory.is_relative_to(root / "results")
                       else Path("build_records") / directory.name)
        for source in selected_tree(directory, results=True, suffixes={".txt", ".csv", ".rsp", ".md", ".json"}):
            add(source, destination / source.relative_to(directory))
    if include_formal_tools and not any(name.startswith("submission/binary/formal/") for name in files):
        raise RuntimeError("Packaged functional-verification tools are absent")
    return dict(sorted(files.items()))


def archive_format(path):
    kind = Path(path).suffix.casefold()
    if kind not in (".rar", ".zip"):
        raise ValueError("--out must end in .rar for official upload, or .zip for local exchange only")
    return kind


def find_rar(explicit=None):
    candidates = [explicit] if explicit is not None else [
        os.environ.get("PMUX_RAR"), shutil.which("rar.exe"), shutil.which("rar"),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "WinRAR" / "Rar.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "WinRAR" / "Rar.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise FileNotFoundError("Genuine RAR creation needs Rar.exe; install WinRAR or specify --rar-tool")


def run_rar(tool, arguments, *, cwd=None):
    result = subprocess.run([str(tool), *map(str, arguments)], cwd=cwd,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f"RAR operation {arguments[0]} failed with exit {result.returncode}")
    return result.stdout


def member_name(name):
    name = str(name).replace("\\", "/")
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or ".." in path.parts or ":" in name
            or "\n" in name or "\r" in name or "\x00" in name or path.parts[0] != "submission"):
        raise ValueError(f"Invalid archive path: {name!r}")
    return path.as_posix()


def compare_files(packed, original, name):
    with packed, original:
        while True:
            left, right = packed.read(1024 * 1024), original.read(1024 * 1024)
            if left != right:
                raise RuntimeError(f"Archived content differs: {name}")
            if not left:
                break


def verify_archive(archive, files, *, rar_tool=None):
    archive = Path(archive)
    kind = archive_format(archive)
    with archive.open("rb") as handle:
        signature = handle.read(8)
    is_rar = signature.startswith((b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"))
    if (kind == ".rar" and not is_rar) or (kind == ".zip" and not signature.startswith(b"PK\x03\x04")):
        raise ValueError("Archive extension does not match its actual format; renaming ZIP to RAR is invalid")
    if kind == ".rar":
        if archive.stat().st_size > MAX_SUBMISSION_BYTES:
            raise ValueError(f"RAR exceeds the {MAX_SUBMISSION_BYTES}-byte submission limit")
        tool = find_rar(rar_tool)
        listed = run_rar(tool, ["lb", "-cfg-", "-scur", archive]).decode("utf-16-le").lstrip("\ufeff")
        names = [member_name(name) for name in listed.splitlines() if name]
        if len(names) != len(files) or set(names) != set(files):
            raise RuntimeError("Archive file list differs from selected sources")
        with tempfile.TemporaryDirectory(prefix="pmux_rar_read_", dir=archive.parent) as temp:
            extracted = Path(temp)
            run_rar(tool, ["x", "-cfg-", "-idq", "-o-", "-y", archive, str(extracted) + os.sep])
            actual = {path.relative_to(extracted).as_posix() for path in extracted.rglob("*") if path.is_file()}
            if actual != set(files):
                raise RuntimeError("Extracted archive file list differs from selected sources")
            for name, source in files.items():
                path = extracted / name
                if path.is_symlink() or path.stat().st_size != source.stat().st_size:
                    raise RuntimeError(f"Archived size or file type differs: {name}")
                compare_files(path.open("rb"), source.open("rb"), name)
        return len(names)

    with ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) != len(files) or {entry.filename for entry in entries} != set(files):
            raise RuntimeError("Archive file list differs from selected sources")
        for entry in entries:
            source = files[entry.filename]
            if entry.file_size != source.stat().st_size:
                raise RuntimeError(f"Archived size differs: {entry.filename}")
            compare_files(package.open(entry), source.open("rb"), entry.filename)
    return len(entries)


def make_archive(files, output, *, rar_tool=None):
    output = output.resolve()
    listing = output.with_suffix(".files.txt")
    kind = archive_format(output)
    partial = output.with_name(output.stem + ".partial" + output.suffix)
    for path in (output, listing, partial):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite: {path}")
    if not files:
        raise RuntimeError("Refusing to create an empty delivery archive")
    for name in files:
        if member_name(name) != name:
            raise ValueError(f"Noncanonical archive path: {name}")
        if PurePosixPath(name).suffix.casefold() in VIDEO_SUFFIXES:
            raise ValueError("Videos are excluded from submission and local exchange archives")
        if kind == ".rar" and name.casefold().startswith("submission/binary/formal/"):
            raise ValueError("Official RAR excludes external OSS CAD Suite tools; use local ZIP for tool exchange")
    if any(path in files.values() for path in (output, listing, partial)):
        raise RuntimeError("Archive output cannot be one of its source files")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if kind == ".zip":
            with ZipFile(partial, "x", ZIP_DEFLATED, compresslevel=6, strict_timestamps=False) as package:
                for name, source in files.items():
                    package.write(source, name)
        else:
            tool = find_rar(rar_tool)
            with tempfile.TemporaryDirectory(prefix="pmux_rar_write_", dir=output.parent) as temp:
                stage = Path(temp)
                for name, source in files.items():
                    destination = stage / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                listing_input = stage / "selected_files.txt"
                listing_input.write_text("\n".join(files) + "\n", encoding="utf-16")
                run_rar(tool, ["a", "-cfg-", "-idq", "-ma5", "-m5", "-scul", partial,
                               "@" + str(listing_input)], cwd=stage)
        count = verify_archive(partial, files, rar_tool=rar_tool)
        listing_text = (f"压缩包：{output.name}\n文件数：{count}\n"
                        f"源文件总字节数：{sum(path.stat().st_size for path in files.values())}\n"
                        "检查结果：每个压缩条目均已读出，并与源文件逐字节比较一致。\n"
                        + ("用途：正式上传格式，RAR文件不超过200000000字节。\n" if kind == ".rar"
                           else "用途：仅供本地交换；ZIP不能用于正式上传。\n") +
                        "本清单仅说明文件内容一致，不表示比赛得分。\n\n"
                        "字节数\t压缩包内位置\n"
                        + "".join(f"{source.stat().st_size}\t{name}\n" for name, source in files.items()))


        if output.exists() or listing.exists():
            raise FileExistsError("Output appeared while the archive was being created")
        partial.rename(output)
        with listing.open("x", encoding="utf-8") as handle:
            handle.write(listing_text)
    except BaseException:
        if partial.is_file():
            partial.unlink()
        raise
    return listing, count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--efficiency", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rar-tool", type=Path, help="Path to WinRAR Rar.exe; discovered automatically when omitted")
    parser.add_argument("--include-formal-tools", action="store_true",
                        help="Include binary/formal only in local ZIP exchange; not permitted for official RAR")
    parser.add_argument("--require-full-score", action="store_true",
                        help="Require average reduction >=20 percent and each time/memory increase <=5 percent; default increase limit is 15 percent")
    parser.add_argument("--parameter-results", "--additional-results", type=Path, action="append", default=[],
                        help="Additional parameter-verification directory; may be supplied more than once")
    parser.add_argument("--build-record-dir", type=Path, action="append", default=[],
                        help="Build records to include (txt/csv/rsp/md/json); may be supplied more than once")
    parser.add_argument("--plan-only", action="store_true", help="List selected paths and sizes without writing an archive")
    args = parser.parse_args(argv)
    kind = archive_format(args.out)
    if args.include_formal_tools and kind != ".zip":
        parser.error("--include-formal-tools is only for local .zip exchange; official .rar uses preinstalled OSS CAD Suite")
    files = collect_files(args.assessment, args.efficiency, args.parameter_results, args.build_record_dir,
                          include_formal_tools=args.include_formal_tools, require_full_score=args.require_full_score)
    total = sum(path.stat().st_size for path in files.values())
    if args.plan_only:
        print(f"Selected files={len(files)} source_bytes={total}; no output was written")
        for name, source in files.items():
            print(f"{source.stat().st_size}\t{name}")
        return 0
    listing, count = make_archive(files, args.out, rar_tool=args.rar_tool)
    print(f"Created {args.out.resolve()} ({args.out.stat().st_size} bytes); verified {count} files")
    print(f"File list: {listing}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
