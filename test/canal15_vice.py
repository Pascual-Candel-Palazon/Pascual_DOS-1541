#!/usr/bin/env python3
# Prueba de extremo a extremo del canal de comandos (15) en VICE: un C64 con las
# ROMs libres de Pascuals-BASIC envia ordenes por el bus a la unidad 8 (dos.bin,
# true drive) y lee el canal de estado con INPUT#15. Despues se comprueba el disco
# con c1541 (referencia externa, Nivel B): directorio y BAM.
#
# Requiere: VICE (x64sc, c1541), Xvfb y las ROMs de Pascuals-BASIC (ver vice_c64).
import os, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from vice_c64 import C64, c1541, read_sector

PORT = int(os.environ.get('C64_PORT_BASE', '6590'))
WORK = os.environ.get('C64_WORK', '/tmp/dos1541_canal15')
ok_all = []


def check(label, cond, extra=''):
    ok_all.append(bool(cond))
    print('[%s] %s %s' % ('OK' if cond else 'FALLO', label, extra))


def prg(path, n, seed):
    with open(path, 'wb') as f:
        f.write(bytes([0x01, 0x08]) + bytes((seed + i) & 0xFF for i in range(n)))


def wait_hash(c, timeout=30):
    """Espera a que aparezca en pantalla la linea de resultado (empieza por '#')."""
    for _ in range(timeout):
        rows = [r for r in c.screen() if r.startswith('#')]
        if rows:
            return rows[-1]
        c.run(1)
    return '(sin respuesta)'


def status_line(c, cmd=None):
    """Envia `cmd` por el canal 15 (si se da) y devuelve la linea de estado."""
    if cmd:
        c.type('PRINT#15,"%s"\n' % cmd)
        c.run(4)
    c.type('PRINTCHR$(147):GOTO1\n')       # pantalla limpia: solo el resultado
    return wait_hash(c)


def setup(c):
    """Lineas de programa para leer el estado. INPUT# y GET# se ejecutan en modo
    programa (GET# no se admite en modo directo); GOTO no cierra los ficheros."""
    c.type('1 INPUT#15,E,E$,T,S:PRINT"#";E;E$;T;S:END\n')
    c.type('2 E$="":FORI=1TO12:GET#15,A$:E$=E$+A$:NEXT:PRINT"#"E$:END\n')
    c.run(1)


def bam_free_map(disk):
    """BAM (pistas 1-35, contador + bitmap) del sector 18/0."""
    return read_sector(disk, 18, 0)[4:144]


def validated_copy(disk):
    """Copia del disco validada por c1541: BAM de referencia para comparar."""
    ref = disk + '.ref.d64'
    shutil.copy(disk, ref)
    c1541(ref, '-validate')
    return ref


def main():
    os.makedirs(WORK, exist_ok=True)
    for f in os.listdir(WORK):
        os.remove(os.path.join(WORK, f))

    # ---- sesion 1: estado de arranque, SCRATCH, RENAME, errores ------------
    d1 = WORK + '/d1.d64'
    c1541(d1, '-format', 'prueba,01', 'd64', d1)
    for name, n, seed in (('a', 300, 1), ('b', 600, 2), ('c', 100, 3)):
        prg(WORK + '/' + name, n, seed)
        c1541(d1, '-write', WORK + '/' + name, name)

    c = C64(WORK, d1, port=PORT + 0)
    try:
        setup(c)
        c.type('OPEN15,8,15\n')
        c.run(2)
        s = status_line(c)
        check('estado de arranque 73', '73' in s and 'PASCUAL DOS 1541' in s, s)
        s = status_line(c)
        check('tras leerlo, vuelve a 00 OK', s.split()[:2] == ['#', '0'] and 'OK' in s, s)
        s = status_line(c, 'S:A')
        check('S:A -> 01 FILES SCRATCHED 1', 'FILES SCRATCHED' in s and ' 1 ' in s + ' ', s)
        s = status_line(c, 'S:NOEXISTE')
        check('S:NOEXISTE -> 01 FILES SCRATCHED 0', 'FILES SCRATCHED' in s and s.rstrip().endswith('0  0'), s)
        s = status_line(c, 'R:Z=B')
        check('R:Z=B -> 00 OK', 'OK' in s, s)
        s = status_line(c, 'R:C=Z')
        check('R:C=Z -> 63 FILE EXISTS', '63' in s and 'FILE EXISTS' in s, s)
        s = status_line(c, 'R:Q=NOEXISTE')
        check('R:Q=NOEXISTE -> 62 FILE NOT FOUND', '62' in s and 'FILE NOT FOUND' in s, s)
        s = status_line(c, 'S')
        check('S sin nombre -> 34 SYNTAX ERROR', '34' in s and 'SYNTAX ERROR' in s, s)
        s = status_line(c, 'X')
        check('orden desconocida -> 31 SYNTAX ERROR', '31' in s and 'SYNTAX ERROR' in s, s)
        c.type('CLOSE15\n')
        c.run(2)
        # GET# lee el estado byte a byte (un TALK por byte): no debe colgarse
        c.type('OPEN15,8,15,"I"\n')
        c.run(6)
        c.type('PRINTCHR$(147):GOTO2\n')
        s = wait_hash(c)
        check('GET# byte a byte: "00, OK,00,00"', s.startswith('#00, OK,00,00'), s)
        c.type('CLOSE15\n')
        c.run(2)
        # LOAD de un fichero inexistente: el estado queda en 62
        c.type('LOAD"NADA",8\n')
        c.run(10)
        setup(c)                            # el LOAD deja el programa vacio
        c.type('OPEN15,8,15\n')
        c.run(2)
        s = status_line(c)
        check('LOAD"NADA" deja 62 FILE NOT FOUND', '62' in s and 'FILE NOT FOUND' in s, s)
        c.type('CLOSE15\n')
        c.run(2)
    finally:
        c.close()

    d = c1541(d1, '-dir')
    print(d)
    names = [l.split('"')[1] for l in d.splitlines() if l.count('"') == 2 and not l.startswith('0 ')]
    check('directorio final = c, z', sorted(names) == ['c', 'z'], str(names))
    ref = validated_copy(d1)
    check('BAM coherente (igual a la validada por c1541)',
          bam_free_map(d1) == bam_free_map(ref))

    # ---- sesion 2: comodines, varios nombres, VALIDATE, NEW, SAVE/LOAD ------
    d2 = WORK + '/d2.d64'
    c1541(d2, '-format', 'otro,02', 'd64', d2)
    for name, n, seed in (('largo1', 700, 4), ('largo2', 50, 5), ('corto', 260, 6),
                          ('x', 20, 7)):
        prg(WORK + '/' + name, n, seed)
        c1541(d2, '-write', WORK + '/' + name, name)
    # BAM estropeada a proposito: todo marcado como ocupado
    raw = bytearray(open(d2, 'rb').read())
    off = (21 * 17 + 0) * 256          # 18/0
    for t in range(35):
        raw[off + 4 + t * 4: off + 8 + t * 4] = b'\x00\x00\x00\x00'
    open(d2, 'wb').write(raw)

    c = C64(WORK, d2, port=PORT + 1)
    try:
        setup(c)
        c.type('OPEN15,8,15\n')
        c.run(2)
        status_line(c)                          # consumir el 73
        s = status_line(c, 'V')
        check('V -> 00 OK', 'OK' in s, s)
        c.type('CLOSE15\n')
        c.run(2)
    finally:
        c.close()
    ref = validated_copy(d2)
    check('VALIDATE reconstruye la BAM como c1541', bam_free_map(d2) == bam_free_map(ref))

    c = C64(WORK, d2, port=PORT + 2)
    try:
        setup(c)
        c.type('OPEN15,8,15\n')
        c.run(2)
        status_line(c)
        s = status_line(c, 'S:LARGO*')
        check('S:LARGO* -> 2 borrados', 'FILES SCRATCHED' in s and ' 2 ' in s + ' ', s)
        s = status_line(c, 'S:X,COR?O')
        check('S:X,COR?O -> 2 borrados', 'FILES SCRATCHED' in s and ' 2 ' in s + ' ', s)
        c.type('CLOSE15\n')
        c.run(2)
    finally:
        c.close()
    d = c1541(d2, '-dir')
    print(d)
    check('disco vacio tras los SCRATCH', '664 blocks free' in d and d.count('prg') == 0, '')

    c = C64(WORK, d2, port=PORT + 3)
    try:
        setup(c)
        c.type('OPEN15,8,15\n')
        c.run(2)
        status_line(c)
        s = status_line(c, 'N:NUEVO,77')
        check('N:NUEVO,77 -> 00 OK', 'OK' in s, s)
        c.type('CLOSE15\n')
        c.run(2)
        c.type('10 PRINT"HOLA"\n')
        c.type('SAVE"PROG",8\n')
        c.run(12)
        c.type('SAVE"PROG",8\n')            # repetido: debe rechazarse con 63
        c.run(12)
        c.type('OPEN15,8,15\n')
        c.run(2)
        s = status_line(c)
        check('SAVE repetido -> 63 FILE EXISTS', '63' in s and 'FILE EXISTS' in s, s)
        c.type('CLOSE15\n')
        c.run(2)
        c.type('NEW\n')
        c.type('LOAD"P*",8\n')
        c.run(12)
        c.type('LIST\n')
        c.run(2)
        scr = '\n'.join(c.screen())
        check('LOAD"P*" con comodin carga el programa', '10 PRINT"HOLA"' in scr)
    finally:
        c.close()
    d = c1541(d2, '-dir')
    print(d)
    hdr = d.splitlines()[0] if d else ''
    check('cabecera nueva "nuevo" id 77', '"nuevo' in hdr and '77' in hdr, hdr)
    names = [l.split('"')[1] for l in d.splitlines() if l.count('"') == 2 and not l.startswith('0 ')]
    check('un solo PROG en el directorio', names == ['prog'], str(names))
    ref = validated_copy(d2)
    check('BAM coherente tras NEW + SAVE', bam_free_map(d2) == bam_free_map(ref))

    print()
    if all(ok_all):
        print('RESULTADO: OK  canal 15 por el bus (%d comprobaciones)' % len(ok_all))
        sys.exit(0)
    print('RESULTADO: FALLO')
    sys.exit(1)


if __name__ == '__main__':
    main()
