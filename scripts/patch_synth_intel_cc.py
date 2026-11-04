#!/usr/bin/env python3

"""Add the PMUX pass to the official Yosys 0.69+24 synth_intel source.

Default delivery changes only the PMUX call and retains the original ABC9
mapping command from d0e71cfb7.  --check reads without writing; --apply updates
only the selected source.  The explicit area9 option is for local experiments
outside plugin/ and is not part of the current submission. Classic ABC is rejected.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import shutil
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugin"

PASS_CALL = 'run("pmux_opt_rtlil -rewrite -sclr-promo-rom-only -no-probe");'
PASS_COMMENT = "// PMUX_OPT: add the PMUX pass; keep the official ABC9 mapping command."
STOCK_CALL = 'run("abc9 -lut 4 -W 300" + string(dff ? " -dff" : ""));'
AREA9_SCRIPT = "&sweep; &dch -f -r; &if {W} {D} {R} -a -F 2 -v"
AREA9_CALL = ('run("abc9 -lut 4 -W 300 -script \\"+' + AREA9_SCRIPT
              + '\\"" + string(dff ? " -dff" : ""));')
CLASSIC_CALL = 'run("abc -lut 4" + string(dff ? " -dff" : ""));'
ANCHORS = {
    "pass": {
        "re": re.compile(r'^([ \t]*)run\("proc"\);[ \t]*(?=\r?$)', re.M),
        "label": "coarse", "mode": "insert_after", "patch": "synth_intel_pass.patch",
    },
    "area9": {
        "re": re.compile(r'^([ \t]*)run\("abc9 -lut 4 -W 300"?.*\);[ \t]*(?=\r?$)', re.M),
        "label": "map_luts", "mode": "replace_line", "patch": "synth_intel_area9.patch",
    },
}
NEW_LINE = {"pass": PASS_CALL, "area9": AREA9_CALL}
NOTE_LINE = {"pass": PASS_COMMENT, "area9": ""}

def _balanced(line: str) -> bool:
    depth = 0
    in_str = False
    esc = False
    for ch in line:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_str


def locate(txt: str, which: str):

    spec = ANCHORS[which]
    hits = list(spec["re"].finditer(txt))
    if not hits:
        raise SystemExit(f"[ANCHOR-MISSING] {which}: no line matching {spec['re'].pattern!r} "
                         f"-- this tree's synth_intel.cc is not the shape the patch was written "
                         f"against; refusing to guess an insertion point")
    if len(hits) > 1:
        raise SystemExit(f"[ANCHOR-DUP] {which}: anchor matched {len(hits)} spots "
                         f"(lines " + ",".join(str(txt[:h.start()].count(chr(10)) + 1) for h in hits)
                         + ") -- uniqueness is the whole basis of this patch")
    m = hits[0]
    line = m.group(0)


    if not _balanced(line):
        raise SystemExit(f"[ANCHOR-UNBALANCED] {which}: anchor line has unbalanced parentheses: "
                         f"{line!r} -- inserting after it would splice code into an open construct")

    before = txt[:m.start()]
    labels = re.findall(r'check_label\("([a-z_]+)"\)', before)
    if not labels:
        raise SystemExit(f"[ANCHOR-NO-SECTION] {which}: no check_label() before the anchor, so the "
                         f"inserted line belongs to no script section")
    owner = labels[-1]
    if owner != spec["label"]:
        raise SystemExit(f"[ANCHOR-WRONG-SECTION] {which}: anchor sits in section {owner!r}, "
                         f"expected {spec['label']!r}")
    return m, m.group(1)


def mapping_kind(txt: str) -> str:
    lines = re.findall(r'^[ \t]*(run\("abc(?:9)?\b.*\);)[ \t]*(?=\r?$)', txt, re.M)
    if len(lines) != 1:
        raise SystemExit("[MAPPING-COUNT] expected exactly one ABC mapping command")
    line = lines[0]
    if line == CLASSIC_CALL or line.startswith('run("abc '):
        return "classic"
    if line not in (STOCK_CALL, AREA9_CALL):
        return "foreign"
    locate(txt, "area9")
    return "area9" if line == AREA9_CALL else "stock"


def is_applied(txt: str, which: str) -> bool:
    if which not in NEW_LINE:
        return False
    if which == "area9":
        return mapping_kind(txt) == "area9"
    matches = list(re.finditer(r'^[ \t]*' + re.escape(PASS_CALL) + r'[ \t]*(?=\r?$)', txt, re.M))
    if not matches:
        return False
    if len(matches) != 1:
        raise SystemExit("[PASS-COUNT] expected exactly one PMUX pass call")
    anchor, _ = locate(txt, "pass")
    labels = re.findall(r'check_label\("([a-z_]+)"\)', txt[:matches[0].start()])
    if matches[0].start() <= anchor.end() or not labels or labels[-1] != "coarse":
        raise SystemExit("[PASS-WRONG-SECTION] PMUX call must follow proc in coarse")
    return True


def detect_newline(txt: str) -> str:
    return "\r\n" if "\r\n" in txt else "\n"


def apply_one(txt: str, which: str, nl: str = "\n") -> str:
    if which not in NEW_LINE:
        raise SystemExit("[UNSUPPORTED-MAPPER] classic ABC replacement is no longer supported")
    if which == "area9" and mapping_kind(txt) not in ("stock", "area9"):
        raise SystemExit("[UNSUPPORTED-MAPPER] refusing to replace a classic or unknown ABC script")
    if is_applied(txt, which):
        return txt
    m, indent = locate(txt, which)
    note = f"{indent}{NOTE_LINE[which]}{nl}" if NOTE_LINE[which] else ""
    payload = note + indent + NEW_LINE[which]
    if ANCHORS[which]["mode"] == "replace_line":
        return txt[:m.start()] + payload + txt[m.end():]
    return txt[:m.end()] + nl + payload + txt[m.end():]


def status(txt: str, which: str) -> str:
    try:
        if is_applied(txt, which):
            return "APPLIED"
        locate(txt, which)
    except SystemExit as exc:
        tag = re.match(r'\[([A-Z-]+)\]', str(exc))
        return "FOREIGN: " + (tag.group(1) if tag else str(exc)[:40])
    return "PRISTINE"


def read_keep_endings(path: Path) -> str:


    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def write_keep_endings(path: Path, s: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(s)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sha_s(s: str) -> str:


    return hashlib.sha256(s.encode("utf-8", "surrogateescape")).hexdigest()


def lf(s: str) -> str:
    return s.replace("\r\n", "\n")


class PatchApplyError(ValueError):
    pass                                            


def apply_unified_diff(base: str, patch: str, max_offset: int = 25) -> tuple:


    src = base.splitlines(keepends=True)
    tail = patch[patch.find("@@"):] if "@@" in patch else ""
    if not tail:
        raise PatchApplyError("no @@ hunk header in the patch -- there is nothing to apply")
    out: list[str] = []
    si = 0
    shifts = []
    hunks = [h for h in re.split(r"(?m)^(?=@@)", tail) if h.startswith("@@")]
    for no, hunk in enumerate(hunks, 1):
        head = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", hunk)
        if not head:
            raise PatchApplyError(f"hunk {no}: unreadable @@ header {hunk.splitlines()[0]!r}")
        named = int(head.group(1)) - 1 if int(head.group(1)) else 0
        body = hunk.splitlines(keepends=True)[1:]
        old_side = [b[1:] for b in body if b[:1] in (" ", "-")]
        if not old_side:
            raise PatchApplyError(f"hunk {no}: pure insertion with no context -- ambiguous anchor")

        found = None
        for delta in range(0, max_offset + 1):
            for cand in ({named - delta, named + delta} - {named} if delta else {named}):
                if cand < si or cand + len(old_side) > len(src):
                    continue
                if src[cand:cand + len(old_side)] == old_side:
                    found = cand
                    break
            if found is not None:
                break
        if found is None:
            raise PatchApplyError(
                f"hunk {no}: context not found within +/-{max_offset} lines of line {named + 1}. "
                f"Expected its first line to be {old_side[0]!r}; the base there reads "
                f"{(src[named] if named < len(src) else '<EOF>')!r}")
        if found < si:
            raise PatchApplyError(f"hunk {no}: lands at line {found + 1}, behind the previous hunk")
        shifts.append(found - named)
        out.extend(src[si:found])
        si = found
        for b in body:
            tag, text = b[:1], b[1:]
            if tag == " ":
                if src[si] != text:
                    raise PatchApplyError(f"hunk {no}: context moved under us at line {si + 1}")
                out.append(src[si]); si += 1
            elif tag == "-":
                if src[si] != text:
                    raise PatchApplyError(f"hunk {no}: deletion does not match line {si + 1}: "
                                          f"{src[si]!r} vs {text!r}")
                si += 1
            elif tag == "+":
                out.append(text)
            else:
                raise PatchApplyError(f"hunk {no}: body line outside [space/+/-]: {b!r}")
    out.extend(src[si:])
    return "".join(out), shifts


def write_patch(pristine: str, patched: str, name: str, out_dir: Path) -> Path:


    lines = list(difflib.unified_diff(
        lf(pristine).splitlines(keepends=True), lf(patched).splitlines(keepends=True),
        fromfile="a/techlibs/intel/synth_intel.cc", tofile="b/techlibs/intel/synth_intel.cc"))
    dst = out_dir / name
    write_keep_endings(dst, "".join(lines))
    return dst


def write_patched_copy(pristine: str, patched: str, out_dir: Path,
                       name: str = "synth_intel.cc.patched") -> Path:

    dst = out_dir / name
    write_keep_endings(dst, patched)
    return dst


def selected_patches(only):
    if only in ("abc", "both"):
        raise SystemExit("[UNSUPPORTED-MAPPER] classic ABC is disabled; use delivery")
    return ("pass",) if only == "delivery" else (only,)


def apply_selected(text, whiches):
    for which in whiches:
        text = apply_one(text, which, detect_newline(text))
    return text


def select_emit_dir(only, explicit):
    if explicit is not None:
        dest = explicit.resolve()
    elif only in ("delivery", "pass"):
        dest = PLUGIN_DIR.resolve()
    else:
        dest = ROOT / "build" / "local_synth_intel_area9"
    if only == "area9" and dest.resolve() == PLUGIN_DIR.resolve():
        raise SystemExit("[LOCAL-OUTPUT] experimental area9 output must use a directory outside plugin/")
    return dest


def original_source(path, txt, explicit=None):
    candidate = explicit or path.with_suffix(path.suffix + ".pristine")
    if candidate.is_file():
        base = read_keep_endings(candidate)
        if mapping_kind(base) != "stock" or is_applied(base, "pass"):
            raise SystemExit("[INVALID-BASE] use the unmodified Yosys 0.69+24 (d0e71cfb7) synth_intel.cc")
        existing = tuple(which for which in ("pass", "area9") if is_applied(txt, which))
        if lf(apply_selected(base, existing)) != lf(txt):
            raise SystemExit("[SOURCE-DIFFERS] the selected source has changes beyond the recognized pass and area script")
        return base, candidate
    if explicit is not None:
        raise SystemExit(f"[BASE-MISSING] original source is absent: {explicit}")
    if mapping_kind(txt) == "stock" and not is_applied(txt, "pass"):
        locate(txt, "pass")
        return txt, path
    raise SystemExit("[BASE-MISSING] patched input needs --base pointing to the unmodified upstream source")


def selftest() -> int:
    import contextlib
    import io
    import tempfile
    import unittest

    fixture = ('void script() override {\n'
               '\t\tif (check_label("coarse")) {\n\t\t\trun("proc");\n\t\t}\n'
               '\t\tif (check_label("map_luts")) {\n\t\t\t' + STOCK_CALL + '\n\t\t}\n}\n')

    class Checks(unittest.TestCase):
        def test_default_delivery_lf_and_crlf(self):
            for base in (fixture, fixture.replace("\n", "\r\n")):
                got = apply_selected(base, selected_patches("delivery"))
                self.assertTrue(is_applied(got, "pass"))
                self.assertEqual(mapping_kind(got), "stock")
                self.assertNotIn("\r\r\n", got)
                self.assertEqual(apply_selected(got, ("pass",)), got)

        def test_standalone_patches_and_stack(self):
            for which in ("pass", "area9"):
                expected = apply_one(fixture, which)
                body = "".join(difflib.unified_diff(fixture.splitlines(keepends=True), expected.splitlines(keepends=True)))
                got, _ = apply_unified_diff(fixture, body)
                self.assertEqual(got, expected)
            after_pass = apply_one(fixture, "pass")
            area = "".join(difflib.unified_diff(fixture.splitlines(keepends=True), apply_one(fixture, "area9").splitlines(keepends=True), n=1))
            stacked, _ = apply_unified_diff(after_pass, area)
            self.assertEqual(stacked, apply_selected(fixture, ("pass", "area9")))

        def test_unknown_and_classic_script_rejected(self):
            for line in (CLASSIC_CALL, STOCK_CALL.replace("-W 300", "-W 299")):
                with self.assertRaises(SystemExit):
                    apply_one(fixture.replace(STOCK_CALL, line), "area9")
            for only in ("abc", "both"):
                with self.assertRaises(SystemExit):
                    selected_patches(only)

        def test_wrong_section_duplicate_and_unbalanced(self):
            for base in (fixture.replace('check_label("map_luts")', 'check_label("coarse")'),
                         fixture.replace(STOCK_CALL, STOCK_CALL + '\n\t\t\t' + STOCK_CALL),
                         fixture.replace(STOCK_CALL, 'run("abc9 -lut 4 -W 300" + f(());')):
                with self.assertRaises(SystemExit):
                    apply_one(base, "area9")

        def test_current_delivery_and_local_experiment_outputs(self):
            self.assertEqual(select_emit_dir("pass", None), PLUGIN_DIR.resolve())
            with self.assertRaises(SystemExit):
                select_emit_dir("area9", PLUGIN_DIR)
            with tempfile.TemporaryDirectory(prefix="pmux_patch_") as temp:
                source = Path(temp) / "synth_intel.cc"
                source.write_text(apply_selected(fixture, ("pass", "area9")), encoding="utf-8")
                before = source.read_bytes()
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["--file", str(source), "--only", "pass", "--apply"]), 3)
                self.assertEqual(source.read_bytes(), before)

        def test_check_read_only_and_generate_matches(self):
            with tempfile.TemporaryDirectory(prefix="pmux_patch_") as temp:
                source = Path(temp) / "synth_intel.cc"
                source.write_text(fixture, encoding="utf-8")
                out = Path(temp) / "out"
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["--file", str(source), "--check", "--emit-dir", str(out)]), 1)
                    self.assertFalse(out.exists())
                    self.assertEqual(main(["--file", str(source), "--emit-dir", str(out)]), 0)
                self.assertEqual(source.read_text(encoding="utf-8"), fixture)
                self.assertEqual((out / "synth_intel.cc.patched").read_text(encoding="utf-8"), apply_selected(fixture, ("pass",)))
                self.assertGreater((out / "synth_intel_pass.patch").stat().st_size, 0)
                self.assertFalse((out / "synth_intel_area9.patch").exists())

        def test_apply_and_check_upstream_copy(self):
            with tempfile.TemporaryDirectory(prefix="pmux_patch_") as temp:
                source = Path(temp) / "synth_intel.cc"
                source.write_text(fixture, encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["--file", str(source), "--apply", "--emit-dir", str(Path(temp) / "out")]), 0)
                    self.assertEqual(main(["--file", str(source), "--check"]), 0)
                    self.assertEqual(main(["--file", str(source), "--apply", "--emit-dir", str(Path(temp) / "out")]), 0)
                self.assertEqual(source.with_suffix(".cc.pristine").read_text(encoding="utf-8"), fixture)

        def test_original_line_endings_may_differ(self):
            with tempfile.TemporaryDirectory(prefix="pmux_patch_") as temp:
                source = Path(temp) / "synth_intel.cc"
                base = Path(temp) / "original.cc"
                write_keep_endings(base, fixture)
                write_keep_endings(source, apply_selected(fixture, ("pass", "area9")).replace("\n", "\r\n"))
                self.assertEqual(original_source(source, read_keep_endings(source), base)[0], fixture)

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    return 0 if result.wasSuccessful() else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, help="Source to inspect or update")
    ap.add_argument("--tree", type=Path, help="Yosys source-tree root")
    ap.add_argument("--base", type=Path, help="Unmodified upstream source; needed when a patched input has no .pristine sibling")
    ap.add_argument("--only", choices=("delivery", "area9", "pass", "abc", "both"), default="delivery",
                    help="delivery/pass=PMUX pass with original ABC9; area9=local experiment; abc/both disabled")
    action = ap.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true", help="Update the specified source after all checks")
    action.add_argument("--check", action="store_true", help="Read-only check; emit no patched source or patch files")
    ap.add_argument("--emit-dir", type=Path, help="Delivery/pass defaults to plugin/; experimental area9 defaults to build/")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", type=Path, help="Optional result file")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        whiches = selected_patches(a.only)
        path = a.file or (a.tree / "techlibs" / "intel" / "synth_intel.cc" if a.tree else None)
        if path is None or not path.is_file():
            print(f"[ABSENT] no synth_intel.cc at {path}; specify --file or --tree")
            return 3
        txt = read_keep_endings(path)
        kind = mapping_kind(txt)
        if kind in ("classic", "foreign"):
            raise SystemExit("[UNSUPPORTED-MAPPER] input must use the original or current fixed ABC9 script")
        if a.only in ("delivery", "pass") and kind != "stock":
            raise SystemExit("[MAPPING-NOT-STOCK] current delivery requires the original ABC9 command; start from official 0.69+24 source")
        report = {"file": str(path), "delivery_set": "+".join(whiches),
                  "mapping_before": kind, "sha256_before": sha(path), "patches": {}}
        for which in whiches:
            report["patches"][which] = {"status_before": status(txt, which), "new_line": NEW_LINE[which]}
        if a.check:
            rc = 0 if all(is_applied(txt, which) for which in whiches) else 1
            for which in whiches:
                print(f"[CHECK] {which}: {report['patches'][which]['status_before']}")
            if a.base is not None:
                original_source(path, txt, a.base)
            report["read_only"] = True
        else:
            out = select_emit_dir(a.only, a.emit_dir)
            base, base_path = original_source(path, txt, a.base)
            desired = apply_selected(txt, whiches)
            copy_is_source = (out / "synth_intel.cc.patched").resolve() == path.resolve()
            if copy_is_source and not a.apply and desired != txt:
                raise SystemExit("[OUTPUT-IS-SOURCE] use --apply or a separate --emit-dir to change this source")
            patches = {}
            for which in whiches:
                target = apply_one(base, which, detect_newline(base))
                body = "".join(difflib.unified_diff(lf(base).splitlines(keepends=True), lf(target).splitlines(keepends=True),
                                fromfile="a/techlibs/intel/synth_intel.cc", tofile="b/techlibs/intel/synth_intel.cc"))
                if not body or apply_unified_diff(lf(base), body)[0] != lf(target):
                    raise SystemExit(f"[PATCH-INVALID] could not reproduce {which} from original source")
                patches[which] = body
            if a.apply and desired != txt:
                backup = path.with_name(path.name + ".before_patch." + sha_s(txt)[:12])
                if not backup.exists():
                    shutil.copyfile(path, backup)
                original = path.with_suffix(path.suffix + ".pristine")
                if not original.exists():
                    shutil.copyfile(base_path, original)
                write_keep_endings(path, desired)
                if read_keep_endings(path) != desired:
                    raise SystemExit("[WRITE-FAILED] saved source differs from generated source")
            out.mkdir(parents=True, exist_ok=True)
            for which, body in patches.items():
                dst = out / ANCHORS[which]["patch"]
                write_keep_endings(dst, body)
                report["patches"][which]["patch_file"] = str(dst)
                report["patches"][which]["patch_bytes"] = dst.stat().st_size
                print(f"[PATCH] {dst}")
            copy = path if copy_is_source else write_patched_copy(base, desired, out)
            report["patched_copy"] = {"file": str(copy), "sha256": sha(copy)}
            report["sha256_after"] = sha(path)
            report["local_experiment_only"] = a.only == "area9"
            print(f"[COPY] {copy}")
            rc = 0
        report["rc"] = rc
        if a.json:
            a.json.parent.mkdir(parents=True, exist_ok=True)
            a.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"SYNTH_INTEL_PATCH rc={rc} only={a.only} apply={a.apply}")
        return rc
    except (SystemExit, PatchApplyError) as exc:
        print(str(exc))
        return 3


if __name__ == "__main__":
    sys.exit(main())
