"""Check bus ordering and external readers in the default priority-chain rule."""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--program',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--expect-unsafe',action='store_true')
    args=parser.parse_args()
    root=args.root.resolve()
    sys.path.insert(0,str(root/'scripts'))
    from evaluate_official_nine import prepared_runtime,env,identity,save_csv
    import run_eqy as eqy
    eqy.preflight()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    rows=[]
    with prepared_runtime() as runtime:
        program=Path(runtime)/'yosys.exe'
        if args.program: shutil.copy2(args.program.resolve(),program)
        (out/'program.txt').write_text(identity(program)+'\n',encoding='utf-8')
        for name in ('permuted_inner','register_reader','plain_chain'):
            directory=out/name;directory.mkdir()
            source=Path(__file__).parent/'priority_cases'/(name+'.il')
            shutil.copy2(source,directory/'before.il')
            recipe=('read_rtlil before.il; hierarchy -top audit; '
                    'pmux_opt_rtlil -rewrite -sclr-promo-rom-only -no-probe; '
                    'opt_clean; write_rtlil after.il; check')
            (directory/'synthesis.ys').write_text(recipe+'\n',encoding='utf-8')
            result=subprocess.run([str(program),'-s','synthesis.ys'],cwd=directory,env=env(out),
                                  capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
            output=result.stdout+result.stderr
            (directory/'synthesis.txt').write_text(output,encoding='utf-8')
            if result.returncode:raise RuntimeError(f'{name}: transformation failed')
            rewritten=bool(re.search(r'chain of 3 \$mux',output))
            config='''[options]
[gold]
read_rtlil before.il
prep -top audit -flatten
setundef -undriven -zero
setundef -init -zero
[gate]
read_rtlil after.il
prep -top audit -flatten
setundef -undriven -zero
setundef -init -zero
[collect audit]
group *
bind *
[strategy whole]
use sat
depth 12
'''
            (directory/'check.eqy').write_text(config,encoding='utf-8')
            code,proof=eqy.run(['-d','proof','check.eqy'],directory,timeout=120)
            (directory/'proof_output.txt').write_text(proof,encoding='utf-8')
            verdict,reason=eqy.verdict_of(code,proof)
            expected_fail=args.expect_unsafe and name!='plain_chain'
            passed=(('partitions not equivalent' in proof and 'DONE (FAIL' in proof) if expected_fail else verdict=='PROVEN')
            expected_rewrite=args.expect_unsafe or name=='plain_chain'
            passed=passed and rewritten==expected_rewrite
            rows.append(dict(case=name,verdict=verdict,rewritten=rewritten,expected_fail=expected_fail,passed=passed,reason=reason))
            save_csv(out/'formal.csv',rows)
            print(f'{name}: {verdict}, rewritten={rewritten}, expected_result={passed}',flush=True)
            if not passed:raise RuntimeError(f'{name}: unexpected result')
    (out/'status.txt').write_text(f'checks={len(rows)}\nall_expected=True\n',encoding='utf-8')

if __name__=='__main__':main()
