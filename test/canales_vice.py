#!/usr/bin/env python3
# Prueba de extremo a extremo de los canales de fichero en VICE: un programa BASIC
# en el C64 escribe y lee ficheros SEQ y USR por la unidad 8 (dos.bin, true drive)
# con OPEN/PRINT#/INPUT#/GET#/CLOSE y lee el canal de estado. Despues c1541
# (referencia externa, Nivel B) comprueba tipos, contenido y BAM.
#
# ROMs del C64: las libres de Pascuals-BASIC, o las de C64_ROMS (ver vice_c64).
import os, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from vice_c64 import C64, c1541, read_sector

PORT = int(os.environ.get('C64_PORT_BASE', '6740'))
WORK = os.environ.get('C64_WORK', '/tmp/dos1541_canales')

# Cada linea cabe en las 80 columnas del editor de pantalla (comprobado abajo).
PROGRAMA = [
    '1 PRINTCHR$(147):OPEN15,8,15:R$=CHR$(13)',
    '2 OPEN2,8,2,"DATOS,S,W":FORI=1TO50:PRINT#2,"LINEA,"STR$(I)R$;:NEXT:CLOSE2',
    '3 INPUT#15,E,E$,T,S:PRINT"#A";E',
    '4 OPEN2,8,2,"DATOS,S,R":C=0',
    '5 INPUT#2,A$,N:IFA$="LINEA"ANDN=C+1THENC=C+1',
    '6 IFST=0THEN5',
    '7 PRINT"#B";C;ST:CLOSE2',
    '8 OPEN3,8,3,"BIN,U,W":FORI=0TO199:PRINT#3,CHR$(I);:NEXT:CLOSE3',
    '9 OPEN3,8,3,"BIN,U,R":K=0:FORI=0TO199:GET#3,A$:IFASC(A$+CHR$(0))=ITHENK=K+1',
    '10 NEXT:PRINT"#C";K;ST:CLOSE3',
    '11 OPEN3,8,3,"DATOS,P,R":INPUT#15,E,E$,T,S:PRINT"#D";E:CLOSE3',
    '12 OPEN2,8,2,"DATOS,S,R":OPEN3,8,3,"OTRO,S,W":INPUT#15,E,E$,T,S:PRINT"#E";E',
    '13 CLOSE3:CLOSE2',
    '14 OPEN2,8,2,"@0:DATOS,S,W":PRINT#2,"NUEVA,"STR$(99)R$;:CLOSE2',
    '15 OPEN2,8,2,"DATOS,S,R":INPUT#2,A$,N:PRINT"#F";A$;N;ST:CLOSE2',
    '16 OPEN4,8,4,"NOEXISTE,S,R":INPUT#15,E,E$,T,S:PRINT"#G";E:CLOSE4',
    '17 OPEN2,8,2,"DATOS,S,A":PRINT#2,"MAS,"STR$(7)R$;:CLOSE2',
    '18 INPUT#15,E,E$,T,S:OPEN2,8,2,"DATOS,S,R":INPUT#2,A$,N:INPUT#2,B$,M',
    '19 PRINT"#H";E;A$;N;B$;M;ST:CLOSE2:OPEN5,8,5,"SINTIPO,W":PRINT#5,"X":CLOSE5',
    '20 OPEN3,8,3,"BIN,U,A":FORI=200TO299:PRINT#3,CHR$(IAND255);:NEXT:CLOSE3',
    '21 INPUT#15,E,E$,T,S:PRINT"#I";E',
    '22 PRINT"#.FIN":CLOSE15:END',
]

assert all(len(l) <= 76 for l in PROGRAMA), 'linea BASIC demasiado larga'

ESPERADO = {
    'A': '0', 'B': '50  64', 'C': '200  64', 'D': '64', 'E': '70',
    'F': 'NUEVA 99  64', 'G': '62', 'H': '0 NUEVA 99 MAS 7  64', 'I': '0',
}
oks = []


def check(label, cond, extra=''):
    oks.append(bool(cond))
    print('[%s] %s %s' % ('OK' if cond else 'FALLO', label, extra))


def bam(disk):
    return read_sector(disk, 18, 0)[4:144]


def main():
    os.makedirs(WORK, exist_ok=True)
    for f in os.listdir(WORK):
        os.remove(os.path.join(WORK, f))
    d = os.path.join(WORK, 'd.d64')
    c1541(d, '-format', 'canales,01', 'd64', d)
    c = C64(WORK, d, port=PORT)
    try:
        for linea in PROGRAMA:
            c.type(linea + '\n')
        c.type('RUN\n')
        filas = []
        for _ in range(240):
            c.run(1)
            filas = [r for r in c.screen() if r.startswith('#')]
            if any(r.startswith('#.FIN') for r in filas):
                break
        print('\n'.join(r for r in c.screen() if r.strip()))
    finally:
        c.close()
    res = {}
    for r in filas:
        if len(r) > 1 and r[1] in ESPERADO:
            res[r[1]] = r[2:].strip()
    nombres = {
        'A': 'escritura SEQ con PRINT# -> estado 00',
        'B': 'lectura SEQ con INPUT#: 50 registros, ST=64 al final',
        'C': 'USR: 200 bytes (0..199) escritos y leidos con GET#, ST=64',
        'D': 'tipo distinto al abrir (P sobre SEQ) -> 64',
        'E': 'segundo fichero abierto a la vez -> 70',
        'F': '"@0:" reemplaza el fichero',
        'G': 'leer un fichero inexistente -> 62',
        'H': 'modo A anade al final del SEQ',
        'I': 'modo A sobre el USR cruzando bloque -> 00',
    }
    # Los registros se escriben con CHR$(13) explicito y ';' para que el fichero
    # sea el mismo con cualquier anfitrion: el PRINT# de Pascuals-BASIC anade un
    # LF tras el CR de fin de linea (el C64 original solo en ficheros >= 128).
    for k in sorted(ESPERADO):
        check(nombres[k], res.get(k) == ESPERADO[k],
              'obtenido=%r esperado=%r' % (res.get(k), ESPERADO[k]))
    dirtxt = c1541(d, '-dir')
    print(dirtxt)
    ent = {}
    for l in dirtxt.splitlines():
        if l.count('"') == 2 and not l.startswith('0 '):
            ent[l.split('"')[1]] = l.split('"')[2].split()[0]
    check('directorio: datos seq, bin usr, sintipo seq (por defecto)',
          ent == {'datos': 'seq', 'bin': 'usr', 'sintipo': 'seq'}, str(ent))
    os.chdir(WORK)
    for f in ('datos', 'bin'):
        if os.path.exists(f):
            os.remove(f)
    c1541(d, '-read', 'datos,s', 'datos')
    c1541(d, '-read', 'bin,u', 'bin')
    got = open('datos', 'rb').read() if os.path.exists('datos') else b''
    check('contenido de datos (c1541)', got == b'NUEVA, 99\rMAS, 7\r', repr(got))
    got = open('bin', 'rb').read() if os.path.exists('bin') else b''
    check('contenido de bin (c1541): 300 bytes en 2 bloques',
          got == bytes(i & 255 for i in range(300)), '%d bytes' % len(got))
    ref = d + '.ref.d64'
    shutil.copy(d, ref)
    c1541(ref, '-validate')
    check('BAM coherente (igual a la validada por c1541)', bam(d) == bam(ref))
    print()
    if all(oks):
        print('RESULTADO: OK  canales de fichero por el bus (%d comprobaciones)' % len(oks))
        sys.exit(0)
    print('RESULTADO: FALLO')
    sys.exit(1)


if __name__ == '__main__':
    main()
