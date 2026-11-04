from pathlib import Path
import time,threading,pyautogui as p,pyperclip,cv2,numpy as np,mss,pygetwindow
root=Path(r'D:\Desktop\PMUX_20261028\results\video_eqy_review_vgl9s0eb')
old=pyperclip.paste();w=pygetwindow.getWindowsWithTitle('Windows PowerShell 5.1')[0]
try:w.restore()
except Exception:pass
time.sleep(.5)
try:w.maximize();w.activate()
except Exception:pass
time.sleep(.5);p.click(400,200);p.hotkey('ctrl','c');time.sleep(.2)
pyperclip.copy("Set-Location 'D:\\Desktop\\PMUX_20261028'; Clear-Host");p.hotkey('ctrl','v');p.press('enter');time.sleep(1)
stop=False
def capture():
 global stop
 with mss.mss() as s:
  writer=cv2.VideoWriter(str(root/'直接比较补录.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),12,(1920,1080));deadline=time.monotonic()
  while not stop:
   frame=np.asarray(s.grab({'left':0,'top':45,'width':2560,'height':1440}))[:,:,:3]
   writer.write(cv2.resize(frame,(1920,1080),interpolation=cv2.INTER_AREA));deadline+=1/12;time.sleep(max(0,deadline-time.monotonic()))
  writer.release()
t=threading.Thread(target=capture);t.start()
try:
 time.sleep(.5);pyperclip.copy(r'.\scripts\run_python.cmd results/video_eqy_review_vgl9s0eb/eqy_demo.py');p.hotkey('ctrl','v');time.sleep(1);p.press('enter');time.sleep(15)
finally:
 stop=True;t.join();pyperclip.copy(old)
 try:w.minimize()
 except Exception:pass
