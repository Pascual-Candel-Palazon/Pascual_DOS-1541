#!/usr/bin/env python3
# Prueba de lectura completa de un sector del disco fisico en VICE.
#
# El ROM se ensambla con -D SECTOR_TEST: el reset llama a disk_sector_test, que
# posiciona el cabezal (seek a la pista 18), busca el sector 1 (distinguiendo
# cabecera de bloque de datos por el primer byte GCR) y lee y decodifica su bloque
# de datos con verificacion de checksum. El ROM de produccion arranca limpio.
#
# Comprueba que los 256 bytes leidos del hardware coinciden BYTE A BYTE con el
# sector 18/1 del .d64 (la cadena seek + busqueda + lectura + GCR + checksum).
#
# Requiere: cc65 (ca65/ld65), VICE (x64sc, c1541), Xvfb.

import os, sys, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
WORK = '/tmp/dos1541_sector'
TEST_BIN = os.path.join(WORK, 'dos_test.bin')
DISK = os.path.join(WORK, 'disco.d64')
PORT = 6520

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
    sh('ca65 -g -D SECTOR_TEST -o %s/dos_test.o %s/dos.s' % (WORK, SRC))
    sh('ld65 -C %s/dos1541.cfg -Ln %s/dos_test.lbl -o %s %s/dos_test.o'
       % (SRC, WORK, TEST_BIN, WORK))
    lbl = load_labels(WORK + '/dos_test.lbl')
    sh('c1541 -format "prueba,01" d64 %s' % DISK)
    sh('c1541 %s -write %s/dos_test.o objeto' % (DISK, WORK))
    # sector 18/1: tras 17 pistas de 21 sectores = 357; +1 = 358; offset 358*256
    with open(DISK, 'rb') as f:
        f.seek(358 * 256)
        ref = f.read(256)

    extra = ['-dos1541', TEST_BIN, '-drive8type', '1541', '-drive8truedrive',
             '-virtualdev8', '-8', DISK]
    p = launch_x64sc(WORK, port=PORT, extra=extra, logpath=WORK + '/vice.log')
    ok = False
    try:
        time.sleep(9)
        m = ViceMonitor(PORT); m.connect()
        m.resume(); time.sleep(4)
        fse = m.mem_get(lbl['fsec_error'], lbl['fsec_error'], memspace=1)[0]
        de = m.mem_get(lbl['data_error'], lbl['data_error'], memspace=1)[0]
        data = bytes(m.mem_get(0x0401, 0x0500, memspace=1))  # DATA_DEC_BUF+1 .. +256
        m.quit()
        print('fsec_error=$%02X data_error=$%02X' % (fse, de))
        ok = (fse == 0 and de == 0 and data == ref)
        print('256 bytes del hardware == sector 18/1 del .d64:', data == ref)
        if not ok:
            print('  leido[:16]:', ' '.join('%02X' % b for b in data[:16]))
            print('  ref  [:16]:', ' '.join('%02X' % b for b in ref[:16]))
    finally:
        p.terminate()
        try: p.wait(timeout=5)
        except Exception: p.kill()
    print('RESULTADO:', 'OK' if ok else 'FALLO', ' lectura de sector del disco fisico en VICE')
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
