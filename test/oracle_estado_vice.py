#!/usr/bin/env python3
# Contraste de comportamiento observable (Nivel B) del canal 15: la misma secuencia
# de ordenes se envia por el bus a dos unidades en VICE, nuestra dos.bin y una ROM
# de referencia de la 1541 (la original, usada SOLO como caja negra: se observa la
# cadena de estado que llega al C64, nunca su codigo). Se comparan las cadenas
# crudas leidas con GET# (conservan los espacios, que INPUT# descarta).
#
# Uso: DOS1541_REF=<rom de referencia> [C64_ROMS=<carpeta>] python3 test/oracle_estado_vice.py
# La ROM de referencia no forma parte del repo.
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from vice_c64 import C64, c1541

WORK = os.environ.get('C64_WORK', '/tmp/dos1541_oraculo')
PORT = int(os.environ.get('C64_PORT_BASE', '6660'))

# (descripcion, texto tecleado antes de leer el estado o None)
PASOS = [
    ('arranque', None),
    ('tras leerlo', None),
    ('S:A', 'PRINT#15,"S:A"'),
    ('S:NOEXISTE', 'PRINT#15,"S:NOEXISTE"'),
    ('S:B*', 'PRINT#15,"S:B*"'),
    ('R:Z=C', 'PRINT#15,"R:Z=C"'),
    ('R:D=Z', 'PRINT#15,"R:D=Z"'),
    ('R:Q=NOEXISTE', 'PRINT#15,"R:Q=NOEXISTE"'),
    ('R:SINIGUAL', 'PRINT#15,"R:SINIGUAL"'),
    ('S', 'PRINT#15,"S"'),
    ('S:', 'PRINT#15,"S:"'),
    ('X', 'PRINT#15,"X"'),
    ('I', 'PRINT#15,"I"'),
    ('V', 'PRINT#15,"V"'),
    ('N:NUEVO', 'PRINT#15,"N:NUEVO"'),
    ('LOAD"NADA"', 'CLOSE15:LOAD"NADA",8'),
    ('SAVE repetido', 'CLOSE15:SAVE"D",8'),
]


# Segundo escenario: disco lleno (SAVE -> DISK FULL) y unidad sin disco.
PASOS_LLENO = [
    ('arranque', None),
    ('SAVE en disco lleno', 'CLOSE15:SAVE"NUEVO",8'),
]
PASOS_SIN_DISCO = [
    ('arranque', None),
    ('I sin disco', 'PRINT#15,"I"'),
    ('S:A sin disco', 'PRINT#15,"S:A"'),
    ('LOAD"$" sin disco', 'CLOSE15:LOAD"$",8'),
]


def leer(c):
    c.type('PRINTCHR$(147):GOTO3\n')
    for _ in range(40):
        rows = [r for r in c.screen() if r.startswith('#')]
        if rows:
            return rows[-1][1:]
        c.run(1)
    return '(sin respuesta)'


def preparar(tag, modo):
    d = os.path.join(WORK, tag + '.d64')
    c1541(d, '-format', 'oraculo,01', 'd64', d)
    if modo == 'normal':
        ficheros = (('a', 300), ('b1', 100), ('b2', 100), ('c', 50), ('d', 20))
    elif modo == 'lleno':
        ficheros = (('grande', 664 * 254 - 2),)
    else:
        return None
    for name, n in ficheros:
        p = os.path.join(WORK, name)
        open(p, 'wb').write(bytes([1, 8]) + bytes(i & 0xFF for i in range(n)))
        c1541(d, '-write', p, name)
    return d


def sesion(rom, port, tag, modo='normal', pasos=PASOS):
    d = preparar(tag, modo)
    c = C64(WORK, d, port=port, rom=rom)
    out = []
    try:
        c.type('3 E$=""\n4 GET#15,A$:IFA$<>CHR$(13)THENE$=E$+A$:GOTO4\n'
               '5 PRINT"#"E$:END\n')
        c.type('OPEN15,8,15\n')
        c.run(2)
        for n, (desc, cmd) in enumerate(pasos):
          try:
            if cmd:
                c.type(cmd + '\n')
                c.run(12 if ('LOAD' in cmd or 'SAVE' in cmd) else 6)
                if cmd.startswith('CLOSE15'):
                    c.type('3 E$=""\n4 GET#15,A$:IFA$<>CHR$(13)THENE$=E$+A$:GOTO4\n'
                           '5 PRINT"#"E$:END\n')
                    c.type('OPEN15,8,15\n')
                    c.run(2)
            out.append((desc, leer(c)))
          except RuntimeError:
            # la unidad no termina (p. ej. la de referencia sin disco sigue
            # reintentando): se anota y se abandonan los pasos restantes
            out += [(d, '(sin respuesta en 60 s)') for d, _ in pasos[n:]]
            break
    finally:
        c.close()
    if d:
        out.append(('directorio final', ' | '.join(
            l.strip() for l in c1541(d, '-dir').splitlines() if l.strip())))
    return out


def main():
    ref = os.environ.get('DOS1541_REF')
    if not ref or not os.path.exists(ref):
        print('SALTADO: falta DOS1541_REF (ROM de referencia de la 1541)')
        return
    os.makedirs(WORK, exist_ok=True)
    for f in os.listdir(WORK):
        os.remove(os.path.join(WORK, f))
    nuestra, referencia = [], []
    for i, (modo, pasos) in enumerate((('normal', PASOS), ('lleno', PASOS_LLENO),
                                       ('sin', PASOS_SIN_DISCO))):
        if os.environ.get('ESCENARIOS') and modo not in os.environ['ESCENARIOS']:
            continue
        nuestra += sesion(None, PORT + 2 * i, 'nuestra_' + modo, modo, pasos)
        referencia += sesion(ref, PORT + 2 * i + 1, 'referencia_' + modo, modo, pasos)
    iguales = 0
    for (d, a), (_, b) in zip(nuestra, referencia):
        same = a == b
        iguales += same
        print('%-3s %-16s nuestra=%r' % ('==' if same else '<>', d, a))
        if not same:
            print('    %-16s ref.   =%r' % ('', b))
    print('\n%d de %d iguales' % (iguales, len(nuestra)))


if __name__ == '__main__':
    main()
