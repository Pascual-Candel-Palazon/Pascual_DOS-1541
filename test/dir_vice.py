#!/usr/bin/env python3
# Prueba del orquestador del listado de directorio en VICE.
#
# El ROM se ensambla con -D DIR_TEST: el reset llama a disk_dir_test, que ejecuta
# disk_build_dir. Esa rutina lee fisicamente el BAM (18/0) y el sector de
# directorio (18/1), y genera en LIST_BUF el programa BASIC del directorio
# (LOAD "$",8): linea de titulo, una linea por fichero y "BLOCKS FREE".
#
# Comprueba que el listado generado del disco real contiene el nombre del disco,
# el del fichero, su tipo y la linea de bloques libres, igual que c1541 -dir.
#
# Requiere: cc65 (ca65/ld65), VICE (x64sc, c1541), Xvfb.

import os, sys, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
WORK = '/tmp/dos1541_dir'
TEST_BIN = os.path.join(WORK, 'dos_test.bin')
DISK = os.path.join(WORK, 'disco.d64')
PORT = 6521

sys.path.insert(0, HERE)
from vice_monitor import ViceMonitor, launch_x64sc

def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('fallo: %s\n%s\n%s' % (cmd, r.stdout, r.stderr))

def load_labels(path):
    out = {}
    for line in open(path):
        p = line.split()
        if len(p) == 3 and p[0] == 'al':
            out[p[2].lstrip('.')] = int(p[1], 16)
    return out

def main():
    os.makedirs(WORK, exist_ok=True)
    sh('ca65 -g -D DIR_TEST -o %s/dos_test.o %s/dos.s' % (WORK, SRC))
    sh('ld65 -C %s/dos1541.cfg -Ln %s/dos_test.lbl -o %s %s/dos_test.o'
       % (SRC, WORK, TEST_BIN, WORK))
    lbl = load_labels(WORK + '/dos_test.lbl')
    sh('c1541 -format "prueba,01" d64 %s' % DISK)
    sh('c1541 %s -write %s/dos_test.o objeto' % (DISK, WORK))

    extra = ['-dos1541', TEST_BIN, '-drive8type', '1541', '-drive8truedrive',
             '-virtualdev8', '-8', DISK]
    p = launch_x64sc(WORK, port=PORT, extra=extra, logpath=WORK + '/vice.log')
    ok = False
    try:
        time.sleep(9)
        m = ViceMonitor(PORT); m.connect()
        m.resume(); time.sleep(5)
        lp = m.mem_get(lbl['list_ptr'], lbl['list_ptr'] + 1, memspace=1)   # list_ptr (lo, hi)
        end = lp[0] | (lp[1] << 8)
        length = end - 0x0300                          # LIST_BUF = $0300
        data = bytes(m.mem_get(0x0300, 0x0300 + length - 1, memspace=1)) if length > 0 else b''
        m.quit()
        print('longitud del listado = %d bytes' % length)
        needles = [b'PRUEBA', b'OBJETO', b'PRG', b'BLOCKS FREE']
        ok = all(n in data for n in needles)
        for n in needles:
            print('  contiene %-12s: %s' % (n.decode(), n in data))
    finally:
        p.terminate()
        try: p.wait(timeout=5)
        except Exception: p.kill()
    print('RESULTADO:', 'OK' if ok else 'FALLO', ' listado de directorio del disco fisico en VICE')
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
