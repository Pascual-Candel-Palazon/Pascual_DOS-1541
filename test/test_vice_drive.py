#!/usr/bin/env python3
# Verifica que NUESTRA ROM arranca en el hardware de la 1541 emulada por VICE.
# Carga dos.bin como ROM de unidad (-dos1541) con emulacion a nivel hardware y lee
# la pagina cero de la unidad por el monitor binario: tras el reset debe contener
# el patron que escribe nuestro codigo (iec_dev=8 y el resto de variables a 0).
# Esto prueba que nuestro 6502 de la unidad ejecuta nuestro vector de reset, inicia
# las VIAs y entra en el bucle del bus. Solo se lee RAM, nunca se inspecciona ROM.
#
# Requiere x64sc (VICE) y las ROMs del C64 instaladas (propietarias, no en el repo).
# Si faltan, el test se salta. La capa fisica (controlador de disco IRQ) aun no
# existe: este test NO prueba lectura/escritura de disco, solo el arranque.
import os
import shutil
import sys
import tempfile
import time

from vice_monitor import ViceMonitor, launch_x64sc
from test_gcr import load_labels

ROM_DIR = "/usr/share/vice/C64"
ROMS = ["kernal-901227-03.bin", "basic-901226-01.bin", "chargen-901225-01.bin"]
DOS_BIN = os.path.abspath("dos.bin")


def main():
    if shutil.which("x64sc") is None or shutil.which("xvfb-run") is None:
        print("SALTADO: x64sc/xvfb-run (VICE) no disponibles")
        sys.exit(0)
    if any(not os.path.exists(os.path.join(ROM_DIR, r)) for r in ROMS):
        print(f"SALTADO: faltan las ROMs del C64 en {ROM_DIR} (propietarias)")
        sys.exit(0)
    if not os.path.exists(DOS_BIN):
        print("SALTADO: dos.bin no encontrado (ejecutar 'make' primero)")
        sys.exit(0)

    labels = load_labels("dos.lbl")
    a_dev = labels["iec_dev"]
    a_state = labels["iec_state"]
    a_sa = labels["iec_sa"]

    work = tempfile.mkdtemp(prefix="vice_drive_")
    port = 6503
    extra = ["-dos1541", DOS_BIN, "-drive8type", "1541",
             "-drive8truedrive", "-virtualdev8"]
    proc = launch_x64sc(work, port=port, extra=extra,
                        logpath=os.path.join(work, "drv.log"))
    zp = b""
    try:
        time.sleep(7)
        m = ViceMonitor(port)
        m.connect()
        zp = m.mem_get(0x0000, 0x001f, memspace=1)   # memspace 1 = unidad 8
        m.quit()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(work, ignore_errors=True)

    if len(zp) < 3:
        print("RESULTADO: FALLO  no se pudo leer la RAM de la unidad")
        sys.exit(1)
    dev_ok = (zp[a_dev] == 8)
    zero_ok = (zp[a_state] == 0 and zp[a_sa] == 0)
    print(f"ZP unidad $00-$1F: {' '.join('%02x' % b for b in zp)}")
    print(f"iec_dev=${a_dev:02X}->{zp[a_dev]}  iec_state=${a_state:02X}->{zp[a_state]}  "
          f"iec_sa=${a_sa:02X}->{zp[a_sa]}")
    print()
    if dev_ok and zero_ok:
        print("RESULTADO: OK  nuestra ROM arranca en la 1541 emulada (reset ejecutado)")
        sys.exit(0)
    print("RESULTADO: FALLO  el patron del reset no aparecio en la RAM de la unidad")
    sys.exit(1)


if __name__ == "__main__":
    main()
