from pathlib import Path
import time,threading,csv,pyautogui as p,pyperclip,cv2,numpy as np,mss,pygetwindow
root=Path(r'D:\Desktop\PMUX_20261028\results\video_eqy_review_vgl9s0eb')
old=pyperclip.paste()
w=pygetwindow.getWindowsWithTitle('Windows PowerShell 5.1')[0]
try: w.activate()
except Exception: pass
time.sleep(.5)
p.click(400,200)
start=time.monotonic(); stop=False; marks=[]
def capture():
 global stop
 with mss.mss() as s:
  writer=cv2.VideoWriter(str(root/'真实补录.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),12,(1920,1080))
  deadline=time.monotonic()
  while not stop:
   frame=np.asarray(s.grab({'left':0,'top':45,'width':2560,'height':1440}))[:,:,:3]
   writer.write(cv2.resize(frame,(1920,1080),interpolation=cv2.INTER_AREA))
   deadline+=1/12
   time.sleep(max(0,deadline-time.monotonic()))
  writer.release()
def cmd(label,command,hold):
 marks.append([label,round(time.monotonic()-start,2),0])
 pyperclip.copy('clear');p.hotkey('ctrl','v');p.press('enter');time.sleep(.35)
 pyperclip.copy(command);p.hotkey('ctrl','v');time.sleep(.6);p.press('enter');time.sleep(hold)
 marks[-1][2]=round(time.monotonic()-start,2)
t=threading.Thread(target=capture); t.start()
try:
 cmd('tcl_source',r'Get-Content results/video_eqy_review_vgl9s0eb/example.tcl',7)
 cmd('tcl_execute',r".\binary\yosys.exe -Q -T -c results/video_eqy_review_vgl9s0eb/example.tcl | Select-String 'Executing PMUX_OPT_RTLIL|merges 7 mutually exclusive'",9)
 cmd('eqy_inputs',r"Get-Content results/video_eqy_review_vgl9s0eb/ports_only.eqy | Select-String '^\[gold\]|^\[gate\]|^read_rtlil'",8)
 cmd('eqy_execute',r"Set-Location results/video_eqy_review_vgl9s0eb; & 'E:\Yosys\oss-cad-suite\oss-cad-suite\lib\python3.exe' -B -X utf8 'E:\Yosys\oss-cad-suite\oss-cad-suite\bin\eqy-script.py' -d recording_1 ports_only.eqy",13)
finally:
 stop=True;t.join();pyperclip.copy(old)
 with (root/'录屏时间.csv').open('w',newline='',encoding='utf-8') as f:
  cw=csv.writer(f);cw.writerow(['part','start','end']);cw.writerows(marks)
 print(marks)
 try: w.minimize()
 except Exception: pass
