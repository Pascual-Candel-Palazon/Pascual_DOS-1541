#!/usr/bin/env python3
# Prueba de ESCRITURA fisica de un sector del disco en VICE.
#
# El ROM se ensambla con -D WRITE_TEST: el reset llama a disk_write_test, que
# rellena un patron conocido (byte i = i), lo codifica a GCR, lo escribe en el
# sector 20/0 con disk_write_sector_hw (poniendo la cabeza en modo escritura por
# el PCR de la VIA2 y grabando SYNC + bloque "in place" tras localizar la cabecera
# comparando GCR crudo), y luego relee el mismo sector con disk_read_sector_hw.
# El ROM de produccion arranca limpio.
#
# Verifica dos cosas:
#   1) relectura en la misma sesion: DATA_DEC_BUF+1 == 00 01 02 ... FF y
#      fsec_error == 0 (la escritura y la relectura por hardware son coherentes).
#   2) persistencia: el sector 20/0 del .d64 contiene el patron tras cerrar VICE.
#
# Requiere: cc65 (ca65/ld65), VICE (x64sc, c1541), Xvfb.

import os, sys, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
WORK = '/tmp/dos1541_write'
TEST_BIN = os.path.join(WORK, 'dos_test.bin')
DISK = os.path.join(WORK, 'disco.d64')
PORT = 6522

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

def sectors_per_track(t):
    if t <= 17: return 21
    if t <= 24: return 19
    if t <= 30: return 18
    return 17

def sector_offset(track, sector):
    off = sum(sectors_per_track(t) for t in range(1, track)) + sector
    return off * 256

def main():
    os.makedirs(WORK, exist_ok=True)
    sh('ca65 -g -D WRITE_TEST -o %s/dos_test.o %s/dos.s' % (WORK, SRC))
    sh('ld65 -C %s/dos1541.cfg -Ln %s/dos_test.lbl -o %s %s/dos_test.o'
       % (SRC, WORK, TEST_BIN, WORK))
    lbl = load_labels(WORK + '/dos_test.lbl')
    sh('c1541 -format "prueba,01" d64 %s' % DISK)
    # contenido inicial distinto del patron, para que la comprobacion sea real
    off = sector_offset(20, 0)
    with open(DISK, 'r+b') as f:
        f.seek(off)
        f.write(bytes([0xEE] * 256))
    expected = bytes(range(256))

    extra = ['-dos1541', TEST_BIN, '-drive8type', '1541', '-drive8truedrive',
             '-virtualdev8', '-8', DISK]
    p = launch_x64sc(WORK, port=PORT, extra=extra, logpath=WORK + '/vice.log')
    ok_ram = False
    try:
        time.sleep(9)
        m = ViceMonitor(PORT); m.connect()
        m.resume(); time.sleep(6)   # escritura + relectura
        fse = m.mem_get(lbl['fsec_error'], lbl['fsec_error'], memspace=1)[0]
        data = bytes(m.mem_get(0x0401, 0x0500, memspace=1))  # DATA_DEC_BUF+1 .. +256
        m.quit()
        print('fsec_error (relectura) = $%02X' % fse)
        ok_ram = (fse == 0 and data == expected)
        print('relectura en sesion: 256 bytes == patron 00..FF:', data == expected)
        if not ok_ram:
            print('  leido[:16]:', ' '.join('%02X' % b for b in data[:16]))
    finally:
        p.terminate()
        try: p.wait(timeout=5)
        except Exception: p.kill()

    time.sleep(1)
    with open(DISK, 'rb') as f:
        f.seek(off)
        on_disk = f.read(256)
    ok_disk = (on_disk == expected)
    print('persistencia: sector 20/0 del .d64 == patron 00..FF:', ok_disk)
    if not ok_disk:
        print('  en disco[:16]:', ' '.join('%02X' % b for b in on_disk[:16]))

    ok = ok_ram and ok_disk
    print('RESULTADO:', 'OK' if ok else 'FALLO', ' escritura de sector del disco fisico en VICE')
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
