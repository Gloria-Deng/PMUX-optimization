"""Compile one candidate pass and link it into a separate Windows Yosys.

The existing configured tree supplies headers, compiled objects and libraries.
Nothing in that tree is edited and Ninja/CMake are never invoked.  Only the
pmux translation unit is replaced.  The output directory must be independent
of the existing build, and existing outputs are never overwritten.

Example:
  python build_candidate.py --source candidate.cc --out candidate/yosys.exe
  python build_candidate.py --source candidate.cc --out candidate/yosys.exe --plan-only
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

DEFAULT_BUILD = Path(os.environ.get("PMUX_YOSYS_BUILD", "build/yosys"))
REPLACED_OBJECT = "passes/pmux_opt/CMakeFiles/yosys_pmux_opt_rtlil.dir/pmux_opt_rtlil.cc.obj"


def command_tokens(command: str) -> list[str]:

    tokens = shlex.split(command, posix=False)
    return [s[1:-1] if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'" else s for s in tokens]


def ninja_tokens(text: str) -> list[str]:

    out, token = [], []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "$":
            index += 1
            if index == len(text) or text[index] not in "$ :":
                raise ValueError("unexpected variable/escape in Ninja object list")
            token.append(text[index])
        elif char.isspace():
            if token:
                out.append("".join(token))
                token = []
        else:
            token.append(char)
        index += 1
    if token:
        out.append("".join(token))
    return out


def canonical(text: str) -> str:
    return text.replace("\\", "/").casefold()


def rsp_quote(text: str) -> str:


    text = text.replace("\\", "/")
    return '"' + text.replace('"', '\\"') + '"'


def link_section(build_dir: Path) -> tuple[list[str], dict[str, str]]:
    data = (build_dir / "build.ninja").read_text(encoding="utf-8")
    logical_lines = data.replace("$\n", "").splitlines()
    matches = [(i, line) for i, line in enumerate(logical_lines)
               if line.startswith("build yosys.exe yosys.exe.a:")]
    if len(matches) != 1:
        raise ValueError(f"expected one executable rule, found {len(matches)}")
    index, line = matches[0]
    _, body = line.split(": ", 1)
    tokens = ninja_tokens(body)
    if tokens[0] != "CXX_EXECUTABLE_LINKER__yosys_Release":
        raise ValueError(f"unexpected executable rule: {tokens[0]}")
    objects = []
    for token in tokens[1:]:
        if token in ("|", "||"):
            break
        if not token.endswith(".obj"):
            raise ValueError(f"unexpected explicit input: {token}")
        objects.append(token)
    variables = {}
    for line in logical_lines[index + 1:]:
        if not line.startswith("  "):
            break
        key, value = line.strip().split(" = ", 1)
        variables[key] = value
    for key in ("FLAGS", "LINK_FLAGS", "LINK_LIBRARIES", "TARGET_FILE", "TARGET_IMPLIB"):
        if key not in variables:
            raise ValueError(f"missing linker setting: {key}")
    return objects, variables


def plans(build_dir: Path, source: Path, output: Path,
          source_suffix="/passes/pmux_opt/pmux_opt_rtlil.cc",
          replaced_object=REPLACED_OBJECT, object_suffix=".pmux.obj"):
    compilation_db = json.loads((build_dir / "compile_commands.json").read_text(encoding="utf-8"))
    units = [entry for entry in compilation_db
             if canonical(entry["file"]).endswith(source_suffix)]
    append_pass = not units and source_suffix == "/passes/pmux_opt/pmux_opt_rtlil.cc"
    if append_pass:
        units = [entry for entry in compilation_db
                 if canonical(entry["file"]).endswith("/techlibs/intel/synth_intel.cc")]
    if len(units) != 1:
        raise ValueError(f"expected one compilation unit for {source_suffix}, found {len(units)}")
    unit = units[0]
    compiler_args = command_tokens(unit["command"])
    obj = output.with_suffix(object_suffix)
    rsp = output.with_suffix(".link.rsp")
    implib = output.with_suffix(".exe.a")
    compiled_args = []
    index = 0
    saw_source = saw_output = 0
    while index < len(compiler_args):
        token = compiler_args[index]
        if token in ("-MF", "-MT", "-MQ"):
            index += 2
            continue
        if token in ("-MD", "-MMD", "-MP"):
            index += 1
            continue
        if token in ("-c", "-o"):
            if index + 1 == len(compiler_args):
                raise ValueError(f"incomplete compiler option: {token}")
            compiled_args += [token, str(source if token == "-c" else obj)]
            saw_source += token == "-c"
            saw_output += token == "-o"
            index += 2
            continue
        compiled_args.append(token)
        index += 1
    if (saw_source, saw_output) != (1, 1):
        raise ValueError("compiler input/output could not be replaced uniquely")
    objects, variables = link_section(build_dir)
    replaced = [i for i, name in enumerate(objects) if canonical(name) == canonical(replaced_object)]
    if append_pass and not replaced:
        dependencies = [build_dir / name for name in objects]
        objects.append(str(obj))
    elif len(replaced) != 1:
        raise ValueError(f"expected one replaced object, found {len(replaced)}")
    else:
        dependencies = [build_dir / name for i, name in enumerate(objects) if i != replaced[0]]
        objects[replaced[0]] = str(obj)
    libraries = command_tokens(variables["LINK_LIBRARIES"])
    dependencies += [Path(name) if Path(name).is_absolute() else build_dir / name
                     for name in libraries if not name.startswith("-")]
    absent = [str(path) for path in dependencies if not path.is_file()]
    if absent:
        raise FileNotFoundError("required existing objects/libraries absent: " + ", ".join(absent[:8]))
    compiled_args[0] = str(Path(compiled_args[0]).resolve())


    compiled_args[1:1] = ["-x", "c++"]
    if not Path(compiled_args[0]).is_file():
        raise FileNotFoundError(compiled_args[0])
    link_args = [compiled_args[0], *command_tokens(variables["FLAGS"]),
                 *command_tokens(variables["LINK_FLAGS"]), "@" + str(rsp),
                 "-o", str(output), "-Wl,--out-implib," + str(implib),
                 "-Wl,--major-image-version,0,--minor-image-version,0"]
    rsp_text = "\n".join(rsp_quote(name) for name in [*objects, *libraries]) + "\n"
    return compiled_args, link_args, rsp_text, obj, rsp, implib, dependencies, unit


def execute(args, cwd, environ, transcript):
    with transcript.open("w", encoding="utf-8") as handle:
        handle.write(subprocess.list2cmdline(args) + "\n\n")
        handle.flush()
        result = subprocess.run(args, cwd=cwd, env=environ, stdout=handle,
                                stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        tail = transcript.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
        raise RuntimeError(f"command exited {result.returncode}:\n" + "\n".join(tail))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new executable filename, ending in .exe")
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--synth-intel-source", type=Path,
                        help="also compile the supplied synth_intel.cc into this executable")
    parser.add_argument("--plan-only", action="store_true", help="validate and print commands without writing or compiling")
    args = parser.parse_args()
    source, output, build_dir = args.source.resolve(), args.out.resolve(), args.build_dir.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.suffix.lower() != ".exe":
        raise ValueError("--out must name a new .exe file")
    if output.is_relative_to(build_dir) or output == source:
        raise ValueError("output must be outside the existing configured build")
    compile_args, link_args, rsp_text, obj, rsp, implib, dependencies, unit = plans(build_dir, source, output)
    additional = None
    if args.synth_intel_source:
        synth_source = args.synth_intel_source.resolve()
        if not synth_source.is_file():
            raise FileNotFoundError(synth_source)
        synth_object = "techlibs/intel/CMakeFiles/yosys_synth_intel.dir/synth_intel.cc.obj"
        additional = plans(build_dir, synth_source, output,
                           "/techlibs/intel/synth_intel.cc", synth_object, ".synth_intel.obj")
        synth_obj = additional[3]
        old_line = rsp_quote(synth_object) + "\n"
        if rsp_text.count(old_line) != 1:
            raise ValueError("synth_intel link input could not be replaced uniquely")
        rsp_text = rsp_text.replace(old_line, rsp_quote(str(synth_obj)) + "\n")
        dependencies.remove(build_dir / synth_object)
    print(f"configured build: {build_dir}")
    print(f"compiler template: {unit['file']}")
    print(f"reused objects/libraries: {len(dependencies)}")
    print(f"replaced object: {REPLACED_OBJECT}")
    print("compile:", subprocess.list2cmdline(compile_args))
    if additional:
        print("compile synth_intel:", subprocess.list2cmdline(additional[0]))
    print("link:", subprocess.list2cmdline(link_args))
    if args.plan_only:
        print("Plan validated. No files written and no compiler started.")
        return 0
    transcript_compile = output.with_suffix(".compile.txt")
    transcript_link = output.with_suffix(".link.txt")
    manifest = output.with_suffix(".build_inputs.csv")
    transcript_synth = output.with_suffix(".synth_compile.txt")
    artifacts = [output, obj, rsp, implib, transcript_compile, transcript_link, manifest]
    if additional:
        artifacts += [additional[3], transcript_synth]
    for path in artifacts:
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")
    output.parent.mkdir(parents=True, exist_ok=True)
    scratch = output.parent / (output.stem + "_tmp")
    scratch.mkdir(exist_ok=True)
    environ = dict(os.environ)
    compiler_dir = str(Path(compile_args[0]).parent)
    environ["PATH"] = compiler_dir + os.pathsep + environ.get("PATH", "")
    environ["TEMP"] = str(scratch)
    environ["TMP"] = str(scratch)
    rsp.write_text(rsp_text, encoding="utf-8")
    with manifest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("role", "path", "bytes"))
        writer.writerow(("candidate_source", str(source), source.stat().st_size))
        writer.writerow(("source_digest", hashlib.sha256(source.read_bytes()).hexdigest(), ""))
        writer.writerow(("original_compilation_source", unit["file"], ""))
        if additional:
            writer.writerow(("synth_intel_source", str(synth_source), synth_source.stat().st_size))
            writer.writerow(("synth_intel_digest", hashlib.sha256(synth_source.read_bytes()).hexdigest(), ""))
        for path in dependencies:
            writer.writerow(("existing_link_input", str(path.resolve()), path.stat().st_size))
    execute(compile_args, build_dir, environ, transcript_compile)
    if not obj.is_file():
        raise RuntimeError("compiler returned success without creating the candidate object")
    if additional:
        execute(additional[0], build_dir, environ, transcript_synth)
        if not additional[3].is_file():
            raise RuntimeError("compiler returned success without creating synth_intel object")
    execute(link_args, build_dir, environ, transcript_link)
    if not output.is_file():
        raise RuntimeError("linker returned success without creating the executable")
    print(f"Built {output} ({output.stat().st_size} bytes). Existing build files were not edited.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
