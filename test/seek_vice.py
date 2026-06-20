#!/usr/bin/env python3
# Prueba del SEEK (motor paso a paso) en VICE (true drive emulation).
#
# El cabezal de la 1541 no tiene sensor de posicion: la pista actual se conoce
# leyendo una cabecera y se mantiene por software. El motor paso a paso se controla
# con los bits 0-1 de VIA2_PB (contador de cuatro fases); cada pista son dos medios
# pasos. py65 no emula nada de esto, asi que la verificacion es solo en VICE.
#
# El ROM se ensambla con -D SEEK_TEST: el reset llama a disk_seek_test, que lee la
# pista de arranque, hace seek hacia adentro a la pista 24 y luego hacia afuera a la
# 17, confirmando cada destino con una lectura de cabecera valida (con reintentos).
#
# Comprueba que tras cada seek el cabezal queda en la pista pedida.
# Requiere: cc65, VICE (x64sc, c1541), Xvfb. Uso: python3 seek_vice.py

import os, sys, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
WORK = '/tmp/dos1541_seek'
TEST_BIN = os.path.join(WORK, 'dos_seek.bin')
DISK = os.path.join(WORK, 'disco.d64')
PORT = 6523

sys.path.insert(0, HERE)
from vice_monitor import ViceMonitor, launch_x64sc

def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('fallo: %s\n%s\n%s' % (cmd, r.stdout, r.stderr))

def main():
    os.makedirs(WORK, exist_ok=True)
    sh('ca65 -g -D SEEK_TEST -o %s/dos_seek.o %s/dos.s' % (WORK, SRC))
    sh('ld65 -C %s/dos1541.cfg -o %s %s/dos_seek.o' % (SRC, TEST_BIN, WORK))
    if not os.path.exists(DISK):
        sh('c1541 -format "prueba,01" d64 %s' % DISK)
        sh('c1541 %s -write %s/dos_seek.o objeto' % (DISK, WORK))

    extra = ['-dos1541', TEST_BIN, '-drive8type', '1541', '-drive8truedrive',
             '-virtualdev8', '-8', DISK]
    p = launch_x64sc(WORK, port=PORT, extra=extra, logpath=WORK + '/vice.log')
    ok = False
    try:
        time.sleep(9)
        m = ViceMonitor(PORT); m.connect()
        m.resume(); time.sleep(4)
        mid = m.mem_get(0x0021, 0x0021, memspace=1)[0]   # want_sector: pista tras seek a 24
        fin = m.mem_get(0x0017, 0x0017, memspace=1)[0]   # hdr_track: pista tras seek a 17
        he = m.mem_get(0x0019, 0x0019, memspace=1)[0]
        m.quit()
        print('seek hacia adentro a 24 -> pista %d' % mid)
        print('seek hacia afuera a 17 -> pista %d (hdr_error=$%02X)' % (fin, he))
        ok = (mid == 24 and fin == 17 and he == 0)
    finally:
        p.terminate()
        try: p.wait(timeout=5)
        except Exception: p.kill()
    print('RESULTADO:', 'OK' if ok else 'FALLO', ' SEEK del cabezal en ambas direcciones en VICE')
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
