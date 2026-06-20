#!/usr/bin/env python3
# Herramienta de diagnostico (no es un test pass/fail) del bus IEC en hardware
# emulado. Arranca el C64 con nuestra ROM como unidad, inyecta LOAD"$",8 por el
# buffer de teclado y reporta el estado: pantalla del C64, palabra de estado de
# I/O, estado del bus en la unidad y el PC de la unidad (para ver donde se queda).
# Se usa para depurar el handshake del bus IEC contra el timing real.
#
# Requiere x64sc (VICE) y las ROMs del C64 instaladas (propietarias, no en el repo).
import os
import shutil
import sys
import tempfile
import time

from vice_monitor import ViceMonitor, launch_x64sc, decode_screen

ROM_DIR = "/usr/share/vice/C64"
ROMS = ["kernal-901227-03.bin", "basic-901226-01.bin", "chargen-901225-01.bin"]
DOS_BIN = os.path.abspath("dos.bin")
LOAD_DOLLAR = bytes([0x4C, 0x4F, 0x41, 0x44, 0x22, 0x24, 0x22, 0x2C, 0x38, 0x0D])


def main():
    if shutil.which("x64sc") is None or shutil.which("xvfb-run") is None:
        print("SALTADO: VICE no disponible")
        return
    if any(not os.path.exists(os.path.join(ROM_DIR, r)) for r in ROMS):
        print(f"SALTADO: faltan las ROMs del C64 en {ROM_DIR}")
        return
    if not os.path.exists(DOS_BIN):
        print("SALTADO: dos.bin no encontrado (make primero)")
        return

    work = tempfile.mkdtemp(prefix="diag_bus_")
    # disco de prueba: si hay c1541, formatear uno; si no, fichero vacio de imagen
    d64 = os.path.join(work, "disco.d64")
    if shutil.which("c1541"):
        import subprocess
        subprocess.run(["c1541", "-format", "diag,01", "d64", d64],
                       cwd=work, capture_output=True)
    else:
        with open(d64, "wb") as f:
            f.write(b"\x00" * 174848)

    extra = ["-dos1541", DOS_BIN, "-drive8type", "1541",
             "-drive8truedrive", "-virtualdev8", "-8", d64]
    proc = launch_x64sc(work, port=6510, extra=extra,
                        logpath=os.path.join(work, "diag.log"))
    try:
        time.sleep(7)
        m = ViceMonitor(6510)
        m.connect()
        m.mem_set(0x0277, LOAD_DOLLAR)
        m.mem_set(0x00C6, bytes([len(LOAD_DOLLAR)]))
        m.resume()
        time.sleep(3)
        rows = [l for l in decode_screen(m.mem_get(0x0400, 0x07e7)) if l.strip()]
        st = m.mem_get(0x0090, 0x0090)[0]
        zp = m.mem_get(0x0000, 0x000f, memspace=1)
        via1 = m.mem_get(0x1800, 0x1800, memspace=1)[0]
        pc = m.pc(memspace=1)
        print("pantalla C64:")
        for ln in rows:
            print("   " + repr(ln))
        print(f"C64 ST($90) = ${st:02X}")
        print(f"unidad: iec_dev={zp[0]} iec_state={zp[1]} iec_sa={zp[2]} data_idx={zp[9]}")
        print(f"unidad VIA1_PB($1800) = ${via1:02X} ({format(via1, '08b')})  "
              f"ATN_IN={1 if via1 & 0x80 else 0} CLK_IN={1 if via1 & 4 else 0} "
              f"DATA_IN={via1 & 1}")
        print(f"unidad PC = ${pc:04X}" if pc else "unidad PC = ?")
        m.quit()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
