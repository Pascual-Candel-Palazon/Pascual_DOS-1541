#!/usr/bin/env python3
# Prueba de la capa fisica de lectura del disco en VICE (true drive emulation).
#
# A diferencia de las baterias py65, esta capa lee el flujo GCR real del cabezal a
# traves de la VIA2 (puerto de datos PA, handshake byte-ready -> flag V, bit SYNC
# en PB7). py65 no emula nada de eso, asi que la verificacion es solo en VICE.
#
# El ROM se ensambla con -D PHYS_TEST: asi el reset llama a disk_phys_test, que
# lee la cabecera y el bloque de datos del primer sector bajo el cabezal y los
# decodifica. El ROM de produccion (sin -D PHYS_TEST) arranca limpio.
#
# Comprueba:
#   - sync_error / hdr_error = 0 (SYNC localizado, cabecera valida con checksum)
#   - la marca del bloque de datos decodificada = $07 (DATA_MARK)
#
# Requiere: cc65 (ca65/ld65), VICE (x64sc, c1541), Xvfb. Uso: python3 disco_fisico_vice.py

import os, sys, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
WORK = '/tmp/dos1541_phys'
TEST_BIN = os.path.join(WORK, 'dos_test.bin')
DISK = os.path.join(WORK, 'disco.d64')
PORT = 6519

sys.path.insert(0, HERE)
from vice_monitor import ViceMonitor, launch_x64sc

def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('fallo: %s\n%s\n%s' % (cmd, r.stdout, r.stderr))

def main():
    os.makedirs(WORK, exist_ok=True)
    # ensamblar el ROM de prueba con el hook de la capa fisica activado
    sh('ca65 -g -D PHYS_TEST -o %s/dos_test.o %s/dos.s' % (WORK, SRC))
    sh('ld65 -C %s/dos1541.cfg -o %s %s/dos_test.o' % (SRC, TEST_BIN, WORK))
    # disco de prueba: formatear y escribir un fichero para que haya sectores con datos
    if not os.path.exists(DISK):
        sh('c1541 -format "prueba,01" d64 %s' % DISK)
        sh('c1541 %s -write %s/dos_test.o objeto' % (DISK, WORK))

    extra = ['-dos1541', TEST_BIN, '-drive8type', '1541', '-drive8truedrive',
             '-virtualdev8', '-8', DISK]
    p = launch_x64sc(WORK, port=PORT, extra=extra, logpath=WORK + '/vice.log')
    ok = False
    try:
        time.sleep(9)
        m = ViceMonitor(PORT); m.connect()
        m.resume(); time.sleep(2)
        se = m.mem_get(0x001A, 0x001A, memspace=1)[0]
        he = m.mem_get(0x0019, 0x0019, memspace=1)[0]
        ht = m.mem_get(0x0017, 0x0017, memspace=1)[0]
        hs = m.mem_get(0x0018, 0x0018, memspace=1)[0]
        dmark = m.mem_get(0x0400, 0x0400, memspace=1)[0]
        m.quit()
        print('sync_error=$%02X hdr_error=$%02X cabecera pista=%d sector=%d' % (se, he, ht, hs))
        print('marca del bloque de datos = $%02X (esperado $07)' % dmark)
        ok = (se == 0 and he == 0 and dmark == 0x07)
    finally:
        p.terminate()
        try: p.wait(timeout=5)
        except Exception: p.kill()
    print('RESULTADO:', 'OK' if ok else 'FALLO', ' lectura fisica de cabecera y bloque de datos en VICE')
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
