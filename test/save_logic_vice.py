import os, sys, subprocess, time
sys.path.insert(0,'test')
from vice_monitor import ViceMonitor, launch_x64sc
SRC='src'; WORK='/tmp/dos1541_savelogic'; os.makedirs(WORK, exist_ok=True)
TB=WORK+'/dos_test.bin'; DISK=WORK+'/disco.d64'
def sh(c):
    r=subprocess.run(c,shell=True,capture_output=True,text=True)
    if r.returncode!=0: raise SystemExit('fallo: %s\n%s\n%s'%(c,r.stdout,r.stderr))
sh('ca65 -g -D SAVE_TEST -o %s/d.o %s/dos.s && ld65 -C %s/dos1541.cfg -o %s %s/d.o'%(WORK,SRC,SRC,TB,WORK))
sh('c1541 -format "p,01" d64 %s'%DISK)
extra=['-dos1541',TB,'-drive8type','1541','-drive8truedrive','-virtualdev8','-8',DISK]
p=launch_x64sc(WORK,port=6560,extra=extra,logpath=WORK+'/v.log')
try:
    time.sleep(9); m=ViceMonitor(6560); m.connect(); m.resume()
    time.sleep(16)   # el SAVE hace varias operaciones de disco
    sa=m.mem_get(0x0000,0x0000,memspace=1)[0]; m.resume()  # toque para asegurar vivo
    m.quit()
finally:
    p.terminate()
    try: p.wait(timeout=5)
    except Exception: p.kill()
time.sleep(1)
# directorio del disco
d=subprocess.run('c1541 %s -dir'%DISK,shell=True,capture_output=True,text=True).stdout
print('--- directorio ---'); print(d.strip())
# extraer el fichero TEST
sh('rm -f %s/test; cd %s && c1541 %s -extract'%(WORK,WORK,DISK))
got=open(WORK+'/test','rb').read()
expected=bytes([0x00,0x10])+bytes([i&0xFF for i in range(300)])
print('fichero extraido: %d bytes (esperado %d)'%(len(got),len(expected)))
print('contenido == esperado:', got==expected)
if got!=expected:
    n=min(len(got),len(expected))
    diff=[i for i in range(n) if got[i]!=expected[i]]
    print('  primeras difs:', diff[:6], 'total', len(diff)+abs(len(got)-len(expected)))
    print('  got[:8]:', ' '.join('%02X'%b for b in got[:8]))
