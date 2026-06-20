# Requiere las ROMs originales del C64 en /mnt/user-data/uploads (no incluidas en el repo).
import os, sys, subprocess, time
sys.path.insert(0,'test')
from vice_monitor import ViceMonitor, launch_x64sc
U='/mnt/user-data/uploads'; WORK='/tmp/dos1541_savebus'; os.makedirs(WORK,exist_ok=True)
DISK=WORK+'/disco.d64'
subprocess.run('cp dos.bin %s/'%WORK,shell=True)
subprocess.run('c1541 -format "p,01" d64 %s >/dev/null 2>&1'%DISK,shell=True)
prog=bytes([i for i in range(16)])
extra=['-kernal',U+'/kernal-original_mio.bin','-basic',U+'/basic_original_mio.bin',
       '-chargen',U+'/set_car_original_mio.bin','-dos1541',WORK+'/dos.bin',
       '-drive8type','1541','-drive8truedrive','-8',DISK]
p=launch_x64sc(WORK,port=6571,extra=extra,logpath=WORK+'/v.log')
try:
    time.sleep(10); m=ViceMonitor(6571); m.connect()
    m.mem_set(0x0801, prog, memspace=0)                 # programa en $0801
    m.mem_set(0x2D, bytes([0x11,0x08]), memspace=0)     # VARTAB = $0811
    cmd=bytes([0x53,0x41,0x56,0x45,0x22,0x54,0x22,0x2C,0x38,0x0D])  # SAVE"T",8 CR
    m.mem_set(0x0277, cmd, memspace=0)
    m.mem_set(0x00C6, bytes([len(cmd)]), memspace=0)    # contador del buffer de teclado
    m.resume(); time.sleep(18)
    m.connect(); m.resume(); m.quit()
finally:
    p.terminate()
    try: p.wait(timeout=5)
    except Exception: p.kill()
time.sleep(1)
print('--- directorio ---')
print(subprocess.run('c1541 %s -dir'%DISK,shell=True,capture_output=True,text=True).stdout.strip())
os.chdir(WORK); subprocess.run('rm -f t; c1541 %s -extract'%DISK,shell=True,capture_output=True,text=True)
if os.path.exists(WORK+'/t'):
    got=open(WORK+'/t','rb').read(); exp=bytes([0x01,0x08])+prog
    print('fichero "t": %d bytes, contenido == [01 08]+patron 0..15: %s'%(len(got),got==exp))
    print('  got:', ' '.join('%02X'%b for b in got))
else:
    print('NO se creo el fichero')
