#!/usr/bin/env python3
# Contraste de comportamiento observable (Nivel B) de los canales de fichero: el
# mismo programa BASIC se ejecuta contra nuestra dos.bin y contra una ROM de
# referencia de la 1541 (la original, SOLO como caja negra: se compara lo que el
# C64 recibe por el bus y el disco resultante, nunca el codigo). Las cadenas de
# estado se leen crudas con GET#.
#
# Uso: DOS1541_REF=<rom de referencia> [C64_ROMS=<carpeta>] python3 test/oracle_canales_vice.py
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from vice_c64 import C64, c1541

WORK = os.environ.get('C64_WORK', '/tmp/dos1541_oraculo_canales')
PORT = int(os.environ.get('C64_PORT_BASE', '6790'))

PROGRAMA = [
    '1 PRINTCHR$(147):OPEN15,8,15:GOSUB90',
    '2 OPEN2,8,2,"SINTIPO,W":PRINT#2,"X":CLOSE2:GOSUB90',
    '3 OPEN2,8,2,"DATOS,S,W":PRINT#2,"AB":CLOSE2:GOSUB90',
    '4 OPEN3,8,3,"DATOS,P,R":GOSUB90:CLOSE3',
    '5 OPEN2,8,2,"DATOS,S,R":OPEN3,8,3,"OTRO,S,W":GOSUB90:CLOSE3:CLOSE2',
    '6 OPEN2,8,2,"DATOS,S,R":GET#2,A$,B$,C$',
    '7 PRINT"#R";ASC(A$+"@");ASC(B$+"@");ASC(C$+"@");ST',
    '8 GET#2,D$:PRINT"#S";LEN(D$);ST:CLOSE2:GOSUB90',
    '9 OPEN2,8,2,"DATOS":GET#2,A$:PRINT"#T";A$;ST:CLOSE2:GOSUB90',
    '10 OPEN2,8,2,"DATOS,S,W":GOSUB90:CLOSE2:GOSUB90',
    '11 OPEN2,8,2,"NOEX":GOSUB90:CLOSE2',
    '12 OPEN2,8,2,"DATOS,S,A":PRINT#2,"C":CLOSE2:GOSUB90',
    '13 PRINT"#.FIN":CLOSE15:END',
    '90 E$=""',
    '91 GET#15,X$:IFX$<>CHR$(13)THENE$=E$+X$:GOTO91',
    '92 PRINT"#";E$:RETURN',
]


def sesion(rom, port, tag):
    d = os.path.join(WORK, tag + '.d64')
    c1541(d, '-format', 'oraculo,01', 'd64', d)
    c = C64(WORK, d, port=port, rom=rom)
    filas = []
    try:
        for linea in PROGRAMA:
            c.type(linea + '\n')
        c.type('RUN\n')
        for _ in range(300):
            c.run(1)
            filas = [r for r in c.screen() if r.startswith('#')]
            if any(r.startswith('#.FIN') for r in filas):
                break
    finally:
        c.close()
    filas = [r for r in filas if not r.startswith('#.FIN')]
    dirtxt = [l.strip() for l in c1541(d, '-dir').splitlines() if l.strip()]
    return filas, dirtxt


def main():
    ref = os.environ.get('DOS1541_REF')
    if not ref or not os.path.exists(ref):
        print('SALTADO: falta DOS1541_REF (ROM de referencia de la 1541)')
        return
    os.makedirs(WORK, exist_ok=True)
    for f in os.listdir(WORK):
        os.remove(os.path.join(WORK, f))
    n_f, n_d = sesion(None, PORT, 'nuestra')
    r_f, r_d = sesion(ref, PORT + 1, 'referencia')
    iguales = 0
    total = max(len(n_f), len(r_f))
    for i in range(total):
        a = n_f[i] if i < len(n_f) else '(nada)'
        b = r_f[i] if i < len(r_f) else '(nada)'
        same = a == b
        iguales += same
        print('%-3s nuestra=%r' % ('==' if same else '<>', a))
        if not same:
            print('    ref.   =%r' % b)
    print('\n%d de %d lineas iguales' % (iguales, total))
    print('\ndirectorio nuestra:    ' + ' | '.join(n_d))
    print('directorio referencia: ' + ' | '.join(r_d))


if __name__ == '__main__':
    main()
