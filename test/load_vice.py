#!/usr/bin/env python3
# Prueba de extremo a extremo del bus IEC en VICE con el ROM de PRODUCCION.
#
# Arranca un C64 con la 1541 (true drive) ejecutando nuestro ROM (dos.bin, sin
# flags de prueba) y teclea ordenes reales por el buffer de teclado del C64:
#
#   1. LOAD"$",8       -> el directorio del disco real se carga en $0801 (BASIC).
#   2. LOAD"DATOS",8,1 -> un fichero por nombre se carga en su direccion ($5000),
#                         siguiendo la cadena de bloques (streaming).
#
# Recorre toda la cadena: recepcion del OPEN/nombre por el bus, iec_talk, lectura
# fisica del disco (seek + busqueda + GCR + checksum), generacion del directorio o
# streaming del fichero, transmision con EOI, y carga en el C64.
#
# Requiere: cc65 (ca65/ld65), VICE (x64sc, c1541), Xvfb.

import os, sys, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
WORK = '/tmp/dos1541_load'
PROD_BIN = os.path.join(WORK, 'dos.bin')
DISK = os.path.join(WORK, 'disco.d64')
PORT = 6522

sys.path.insert(0, HERE)
from vice_monitor import ViceMonitor, launch_x64sc

def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('fallo: %s\n%s\n%s' % (cmd, r.stdout, r.stderr))

def petscii(s):
    return [ord(c) for c in s]

def is_ready(m):
    scr = bytes(m.mem_get(0x0400, 0x07E7, memspace=0)); m.resume()
    conv = bytes((c & 0x7f) + 64 if 1 <= (c & 0x7f) <= 26 else 32 for c in scr)
    return b'READY' in conv

def load_one(disk, text, read_addr, read_len, port):
    """Arranca un C64 limpio, teclea `text`+RETURN y devuelve read_len bytes
    desde read_addr tras la carga. Sesion independiente por robustez."""
    extra = ['-dos1541', PROD_BIN, '-drive8type', '1541', '-drive8truedrive',
             '-virtualdev8', '-8', disk]
    p = launch_x64sc(WORK, port=port, extra=extra, logpath=WORK + '/vice.log')
    try:
        time.sleep(9)
        m = ViceMonitor(port); m.connect(); m.resume()
        for _ in range(40):
            time.sleep(1)
            if is_ready(m):
                break
        cmd = petscii(text) + [0x0D]
        m.mem_set(0x0277, cmd, memspace=0)        # cola de teclado del C64
        m.mem_set(0x00C6, [len(cmd)], memspace=0)  # numero de teclas en cola
        m.resume()
        time.sleep(14)                             # carga por el bus IEC
        data = bytes(m.mem_get(read_addr, read_addr + read_len - 1, memspace=0))
        m.resume(); m.quit()
        return data
    finally:
        p.terminate()
        try: p.wait(timeout=5)
        except Exception: p.kill()

def main():
    os.makedirs(WORK, exist_ok=True)
    # ROM de PRODUCCION (sin flags): debe arrancar limpio y servir el bus
    sh('ca65 -g -o %s/dos.o %s/dos.s' % (WORK, SRC))
    sh('ld65 -C %s/dos1541.cfg -o %s %s/dos.o' % (SRC, PROD_BIN, WORK))
    sh('c1541 -format "prueba,01" d64 %s' % DISK)
    sh('c1541 %s -write %s/dos.o objeto' % (DISK, WORK))
    # fichero PRG de contenido conocido cargado en zona alta ($5000): 20 bytes A..T
    prg = os.path.join(WORK, 'datos.prg')
    with open(prg, 'wb') as f:
        f.write(bytes([0x00, 0x50]) + bytes(range(0x41, 0x41 + 20)))
    sh('c1541 %s -write %s datos' % (DISK, prg))

    # 1. LOAD"$",8 -> directorio en $0801 (BASIC)
    d = load_one(DISK, 'LOAD"$",8', 0x0801, 0xFF, 6522)
    ok_dir = all(n in d for n in (b'PRUEBA', b'OBJETO', b'PRG', b'BLOCKS FREE'))
    print('LOAD"$",8       -> directorio en $0801:', 'OK' if ok_dir else 'FALLO')

    # 2. LOAD"DATOS",8,1 -> fichero por nombre en su direccion ($5000)
    f5 = load_one(DISK, 'LOAD"DATOS",8,1', 0x5000, 20, 6523)
    expected = bytes(range(0x41, 0x41 + 20))
    ok_file = (f5 == expected)
    print('LOAD"DATOS",8,1 -> fichero en $5000:', 'OK' if ok_file else 'FALLO')
    if not ok_file:
        print('  leido   :', ' '.join('%02X' % b for b in f5))
        print('  esperado:', ' '.join('%02X' % b for b in expected))

    ok = ok_dir and ok_file
    print('RESULTADO:', 'OK' if ok else 'FALLO', ' LOAD de directorio y de fichero por bus IEC en VICE')
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
