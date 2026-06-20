#!/usr/bin/env python3
# Verifica el encadenamiento de sectores de directorio: dos1541 graba 10 ficheros
# (hook MULTI_TEST), lo que fuerza un segundo sector de directorio en la pista 18,
# y luego un C64 hace LOAD"F9",8,1 (F9 cae en ese segundo sector), comprobando que
# la busqueda recorre la cadena. Se corre desde la raiz del repo.
import os, sys, subprocess, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import load_vice as L
from vice_monitor import ViceMonitor, launch_x64sc
SRC='src'
def sh(c):
    r=subprocess.run(c,shell=True,capture_output=True,text=True)
    if r.returncode!=0: raise SystemExit('fallo: %s\n%s'%(c,r.stderr))
def main():
    os.makedirs(L.WORK, exist_ok=True)
    DISK=L.WORK+'/multi.d64'
    sh('ca65 -g -D MULTI_TEST -o %s/dosm.o %s/dos.s'%(L.WORK,SRC))
    sh('ld65 -C %s/dos1541.cfg -o %s/dosm.bin %s/dosm.o'%(SRC,L.WORK,L.WORK))
    sh('ca65 -g -o %s/dos.o %s/dos.s'%(L.WORK,SRC))
    sh('ld65 -C %s/dos1541.cfg -o %s %s/dos.o'%(SRC,L.PROD_BIN,L.WORK))
    sh('c1541 -format "p,01" d64 %s'%DISK)
    extra=['-dos1541',L.WORK+'/dosm.bin','-drive8type','1541','-drive8truedrive','-virtualdev8','-8',DISK]
    p=launch_x64sc(L.WORK,port=6590,extra=extra,logpath=L.WORK+'/vm.log')
    try:
        time.sleep(9); m=ViceMonitor(6590); m.connect(); m.resume(); time.sleep(30)
        m.connect(); m.resume(); m.quit()
    finally:
        p.terminate()
        try: p.wait(timeout=5)
        except Exception: p.kill()
    time.sleep(1)
    got=L.load_one(DISK, 'LOAD"F9",8,1', 0x1000, 2, 6591)
    ok = got==bytes([9,9])
    print('LOAD"F9",8,1 (F9 en el 2do sector de directorio) -> $1000:', ' '.join('%02X'%b for b in got))
    print('RESULTADO:', 'OK' if ok else 'FALLO', ' encadenamiento de directorio (SAVE extiende, LOAD recorre)')
    sys.exit(0 if ok else 1)
if __name__=='__main__': main()
