from pathlib import Path
import os,sys,datetime
root=Path(r"D:\Desktop\PMUX_20261028")
here=Path(__file__).resolve().parent
os.environ["OSS_CAD_SUITE"]=r"E:\Yosys\oss-cad-suite\oss-cad-suite"
os.environ["PMUX_MAKE_DIRS"]=r"E:\msys64\usr\bin"
sys.path.insert(0,str(root / "scripts"))
import run_eqy
run_eqy.preflight()
name="live_"+datetime.datetime.now().strftime("%H%M%S_%f")
rc,out=run_eqy.run(["-d",name,"ports_only.eqy"],here,timeout=180)
print(out,flush=True)
sys.exit(rc)
