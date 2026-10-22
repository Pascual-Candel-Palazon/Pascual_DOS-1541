#!/usr/bin/env python3
# Utilidades para las pruebas de extremo a extremo en VICE con un C64 completo:
# arranca x64sc con las ROMs libres de Pascuals-BASIC como host y dos.bin como ROM
# de la unidad 8 (true drive), teclea texto en el C64 por el buffer de teclado y lee
# la pantalla. Solo observa RAM del C64 (comportamiento de caja negra, Nivel B).
import os, subprocess, time

from vice_monitor import ViceMonitor, launch_x64sc, decode_screen

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def pascuals_basic_dir():
    """ROMs libres del C64. Por defecto junto a este repo; PASCUALS_BASIC lo cambia."""
    pb = os.environ.get('PASCUALS_BASIC') or os.path.abspath(
        os.path.join(ROOT, '..', 'Pascuals-BASIC'))
    if not os.path.exists(os.path.join(pb, 'bin', 'kernal_c64.bin')):
        if not os.path.isdir(pb):
            subprocess.run(['git', 'clone',
                            'https://github.com/Pascual-Candel-Palazon/Pascuals-BASIC', pb],
                           check=True)
        subprocess.run('sh build.sh', shell=True, cwd=pb, check=True)
    return os.path.join(pb, 'bin')


def host_roms():
    """ROMs del C64 anfitrion. Por defecto las libres de Pascuals-BASIC. Con
    C64_ROMS=<carpeta> se usan las originales de esa carpeta (kernal*, basic*,
    chargen*, por ejemplo las que trae VICE), solo como periferico opaco del
    otro extremo del bus. No forman parte del repo."""
    d = os.environ.get('C64_ROMS')
    if not d:
        b = pascuals_basic_dir()
        return ['-kernal', b + '/kernal_c64.bin', '-basic', b + '/basic_c64.bin',
                '-chargen', b + '/chargen.bin']
    out = []
    for opt, pref in (('-kernal', 'kernal'), ('-basic', 'basic'), ('-chargen', 'chargen')):
        names = sorted(n for n in os.listdir(d) if n.lower().startswith(pref))
        if not names:
            raise RuntimeError('falta la ROM %s en %s' % (pref, d))
        out += [opt, os.path.join(d, names[-1])]
    return out


class C64:
    """Un C64 con la unidad 8 corriendo dos.bin sobre la imagen `disk`."""

    def __init__(self, work, disk, port=6580, rom=None):
        self.work = work
        rom = rom or os.path.join(ROOT, 'dos.bin')
        extra = host_roms() + ['-dos1541', rom,
                 '-drive8type', '1541', '-drive8truedrive']
        if disk:                        # sin disco: unidad vacia
            extra += ['-8', disk]
        self.proc = launch_x64sc(work, port=port, extra=extra,
                                 logpath=os.path.join(work, 'vice.log'))
        time.sleep(6)
        self.m = ViceMonitor(port)
        self.m.connect()
        # esperar al READY. del arranque: lo tecleado antes se perderia
        for _ in range(40):
            if any(r.startswith('READY.') for r in self.screen()):
                break
            self.run(0.5)
        else:
            raise RuntimeError('el C64 no llego a READY.')

    def type(self, text, settle=0.4):
        """Teclea `text` (ASCII; '\\n' = RETURN) en trozos de 10 por el buffer."""
        data = bytes(0x0D if c == '\n' else ord(c.upper()) for c in text)
        for i in range(0, len(data), 10):
            chunk = data[i:i + 10]
            # no pisar teclas aun no consumidas (el C64 puede estar ocupado)
            for _ in range(200):
                if self.m.mem_get(0x00C6, 0x00C6)[0] == 0:
                    break
                self.run(0.3)
            else:
                raise RuntimeError('el C64 no consume el buffer de teclado')
            self.m.mem_set(0x0277, chunk)
            self.m.mem_set(0x00C6, bytes([len(chunk)]))
            self.m.resume()
            time.sleep(settle)
            self.m.connect()

    def run(self, seconds):
        self.m.resume()
        time.sleep(seconds)
        self.m.connect()

    def screen(self):
        return decode_screen(bytes(self.m.mem_get(0x0400, 0x07E7)))

    def close(self):
        try:
            self.m.resume()
            self.m.quit()
        except Exception:
            pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
        time.sleep(1)


def c1541(disk, *args):
    r = subprocess.run(['c1541', disk] + list(args), capture_output=True, text=True)
    return r.stdout + r.stderr


def read_sector(disk, track, sector):
    """Lee un sector de un .d64 de 35 pistas (sin errores)."""
    spt = [21] * 17 + [19] * 7 + [18] * 6 + [17] * 5
    off = sum(spt[:track - 1]) * 256 + sector * 256
    with open(disk, 'rb') as f:
        f.seek(off)
        return f.read(256)
