#!/usr/bin/env python3
# Prueba del SISTEMA 100% LIBRE: el C64 con ROMs libres (Pascuals-BASIC: BASIC
# derivado del fuente MIT de Microsoft, KERNAL clean-room, chargen LGPL de MEGA65
# Open ROMs) hablando con la 1541 libre (este dos1541) por el bus IEC, SIN ninguna
# ROM propietaria de Commodore y SIN dispositivo virtual.
#
# Es la primera vez que los dos lados libres se enfrentan: el dos1541 se valido
# contra el KERNAL original y el C64 libre contra una 1541 real, nunca entre si.
# El primer intento revelo un deadlock: el C64 libre confia en la deteccion de ATN
# por hardware de la 1541 (no marca EOI en el nombre), y el dos1541 solo sondeaba
# ATN al inicio de cada byte. Resuelto vigilando ATN tambien en la espera entre
# bits de iec_recv_byte (sin tocar el muestreo, para no romper el KERNAL original).
#
# Comprueba, con ROMs libres en ambos extremos:
#   LOAD"$",8        -> el directorio del disco real se carga en $0801
#   LOAD"DATOS",8,1  -> un fichero por nombre se carga en su direccion ($5000)
#
# El C64 libre se clona y construye desde su repo si no esta presente.
# Requiere: cc65, VICE (x64sc, c1541), Xvfb, git, python3.

import os, sys, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
WORK = '/tmp/dos1541_libre'
C64 = os.path.join(WORK, 'c64libre')   # repo Pascuals-BASIC
DISK = os.path.join(WORK, 'disco.d64')
PROD_BIN = os.path.join(WORK, 'dos1541.bin')
REPO = 'https://github.com/Pascual-Candel-Palazon/Pascuals-BASIC.git'

sys.path.insert(0, HERE)
from vice_monitor import ViceMonitor, launch_x64sc

def sh(cmd, cwd=None):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise SystemExit('fallo: %s\n%s\n%s' % (cmd, r.stdout, r.stderr))

def petscii(s):
    return [ord(c) for c in s]

def is_ready(m):
    scr = bytes(m.mem_get(0x0400, 0x07E7, memspace=0)); m.resume()
    conv = bytes((c & 0x7f) + 64 if 1 <= (c & 0x7f) <= 26 else 32 for c in scr)
    return b'READY' in conv

def load_one(kbin, bbin, cbin, text, read_addr, read_len, port):
    extra = ['-kernal', kbin, '-basic', bbin, '-chargen', cbin,
             '-dos1541', PROD_BIN, '-drive8type', '1541', '-drive8truedrive', '-8', DISK]
    p = launch_x64sc(WORK, port=port, extra=extra, logpath=WORK + '/vice.log')
    try:
        time.sleep(9)
        m = ViceMonitor(port); m.connect(); m.resume()
        for _ in range(40):
            time.sleep(1)
            if is_ready(m):
                break
        cmd = petscii(text) + [0x0D]
        m.mem_set(0x0277, cmd, memspace=0)
        m.mem_set(0x00C6, [len(cmd)], memspace=0)
        m.resume()
        time.sleep(15)
        data = bytes(m.mem_get(read_addr, read_addr + read_len - 1, memspace=0))
        m.resume(); m.quit()
        return data
    finally:
        p.terminate()
        try: p.wait(timeout=5)
        except Exception: p.kill()

def main():
    os.makedirs(WORK, exist_ok=True)
    # 1541 libre (este proyecto), ROM de produccion sin flags
    sh('ca65 -g -o %s/dos.o %s/dos.s' % (WORK, SRC))
    sh('ld65 -C %s/dos1541.cfg -o %s %s/dos.o' % (SRC, PROD_BIN, WORK))
    # C64 libre: clonar y construir si no esta
    if not os.path.exists(os.path.join(C64, 'bin', 'kernal_c64.bin')):
        sh('rm -rf %s && git clone --depth 1 %s %s' % (C64, REPO, C64))
        sh('sh build.sh', cwd=C64)
    kbin = os.path.join(C64, 'bin', 'kernal_c64.bin')
    bbin = os.path.join(C64, 'bin', 'basic_c64.bin')
    cbin = os.path.join(C64, 'bin', 'chargen.bin')
    # disco con un fichero de directorio y un PRG de contenido conocido en $5000
    sh('c1541 -format "prueba,01" d64 %s' % DISK)
    sh('c1541 %s -write %s/dos.o objeto' % (DISK, WORK))
    prg = os.path.join(WORK, 'datos.prg')
    with open(prg, 'wb') as f:
        f.write(bytes([0x00, 0x50]) + bytes(range(0x41, 0x41 + 20)))
    sh('c1541 %s -write %s datos' % (DISK, prg))

    d = load_one(kbin, bbin, cbin, 'LOAD"$",8', 0x0801, 0xFF, 6544)
    ok_dir = all(n in d for n in (b'PRUEBA', b'OBJETO', b'PRG', b'BLOCKS FREE'))
    print('C64 libre  LOAD"$",8       -> directorio en $0801:', 'OK' if ok_dir else 'FALLO')

    f5 = load_one(kbin, bbin, cbin, 'LOAD"DATOS",8,1', 0x5000, 20, 6545)
    expected = bytes(range(0x41, 0x41 + 20))
    ok_file = (f5 == expected)
    print('C64 libre  LOAD"DATOS",8,1 -> fichero en $5000:', 'OK' if ok_file else 'FALLO')
    if not ok_file:
        print('  leido   :', ' '.join('%02X' % b for b in f5))
        print('  esperado:', ' '.join('%02X' % b for b in expected))

    ok = ok_dir and ok_file
    print('RESULTADO:', 'OK' if ok else 'FALLO',
          ' sistema 100% libre (C64 libre + 1541 libre) por bus IEC en VICE')
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
