#!/usr/bin/env python3
# Smoke test del andamiaje de verificacion en VICE: arranca un C64 headless,
# lee la RAM de pantalla por el monitor binario y comprueba el banner de arranque.
# Valida la cadena completa (lanzar, conectar, leer RAM, decodificar) que despues
# servira para probar la capa fisica de la 1541 en hardware emulado.
#
# Requiere x64sc (VICE) y las ROMs del C64 instaladas en el system path de VICE.
# Las ROMs son propietarias y NO forman parte del repo: cada uno usa las suyas
# (volcadas de su propio hardware). Si faltan, el test se salta (no es un fallo).
# Solo se lee RAM, nunca se inspecciona ni desensambla ninguna ROM (Nivel B).
import os
import shutil
import sys
import tempfile
import time

from vice_monitor import ViceMonitor, launch_x64sc, decode_screen

ROM_DIR = "/usr/share/vice/C64"
ROMS = ["kernal-901227-03.bin", "basic-901226-01.bin", "chargen-901225-01.bin"]


def main():
    if shutil.which("x64sc") is None or shutil.which("xvfb-run") is None:
        print("SALTADO: x64sc/xvfb-run (VICE) no disponibles")
        sys.exit(0)
    missing = [r for r in ROMS if not os.path.exists(os.path.join(ROM_DIR, r))]
    if missing:
        print(f"SALTADO: faltan ROMs del C64 en {ROM_DIR}: {missing}")
        print("  (son propietarias; instalar las propias para habilitar este test)")
        sys.exit(0)

    work = tempfile.mkdtemp(prefix="vice_boot_")
    log = os.path.join(work, "x64sc.log")
    port = 6502
    proc = launch_x64sc(work, port=port, logpath=log)
    rows = []
    try:
        time.sleep(6)                       # arranque en warp, de sobra
        m = ViceMonitor(port)
        m.connect()
        scr = m.mem_get(0x0400, 0x07e7)     # RAM de pantalla (40x25)
        rows = decode_screen(scr)
        m.quit()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(work, ignore_errors=True)

    text = " ".join(rows).upper()
    ok = ("COMMODORE" in text and "BASIC" in text and "READY" in text)
    for ln in rows:
        if ln.strip():
            print("  " + repr(ln))
    print()
    if ok:
        print("RESULTADO: OK  andamiaje VICE operativo (C64 arranca y se lee su RAM)")
        sys.exit(0)
    print("RESULTADO: FALLO  el banner de arranque no aparecio como se esperaba")
    sys.exit(1)


if __name__ == "__main__":
    main()
