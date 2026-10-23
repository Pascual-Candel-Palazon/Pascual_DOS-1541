#!/usr/bin/env python3
# ============================================================================
#  test_chan.py  ::  nombre de OPEN de un canal de fichero
# ----------------------------------------------------------------------------
#  Verifica chan_parse: "[@][0:]nombre[,tipo[,modo]]" -> NAME_BUF (16 bytes,
#  relleno $A0), open_type, open_mode y open_repl. Formato del manual de usuario
#  de la unidad (OPEN 2,8,2,"DATOS,S,W").
# ============================================================================
import sys
from test_gcr import load_labels, make_machine, call_sub

DATA_BUF = 0x0300
NAME_BUF = 0x0280


def pad(name):
    b = name.encode('ascii')[:16]
    return b + bytes([0xA0] * (16 - len(b)))


def parse(mpu, mem, labels, text):
    b = text.encode('ascii')
    for i, c in enumerate(b):
        mem[DATA_BUF + i] = c
    mem[labels['data_idx']] = len(b)
    call_sub(mpu, mem, labels['chan_parse'])
    name = bytes(mem[NAME_BUF + i] for i in range(16))
    t = mem[labels['open_type']]
    m = mem[labels['open_mode']]
    r = mem[labels['open_repl']]
    return mpu.a, name, (chr(t) if t else ''), (chr(m) if m else ''), r == 0xFF


def main():
    mpu, mem = make_machine()
    labels = load_labels('dos.lbl')
    cases = [
        ('DATOS', 'DATOS', '', '', False),
        ('DATOS,S,W', 'DATOS', 'S', 'W', False),
        ('DATOS,SEQ,WRITE', 'DATOS', 'S', 'W', False),
        ('@0:DATOS,S,W', 'DATOS', 'S', 'W', True),
        ('0:PROG,P', 'PROG', 'P', '', False),
        ('X,U,R', 'X', 'U', 'R', False),
        ('NOMBREMUYLARGODEMASDE16,S,R', 'NOMBREMUYLARGODE', 'S', 'R', False),
        ('@:N', 'N', '', '', True),
        ('SINTIPO,W', 'SINTIPO', '', 'W', False),
        ('DATOS,A', 'DATOS', '', 'A', False),
        ('DATOS,R,S', 'DATOS', 'S', 'R', False),
        ('REL,L', 'REL', 'L', '', False),
    ]
    ok = True
    for text, name, t, m, r in cases:
        a, gname, gt, gm, gr = parse(mpu, mem, labels, text)
        good = (gname == pad(name) and gt == t and gm == m and gr == r and a != 0)
        ok &= good
        print('[%-28s] nombre=%r tipo=%r modo=%r repl=%s -> %s'
              % (text, gname.rstrip(b'\xa0').decode(), gt, gm, gr, 'OK' if good else 'FALLO'))
    a, *_ = parse(mpu, mem, labels, '')
    good = (a == 0)
    ok &= good
    print('[%-28s] vacio -> %s' % ('', 'OK' if good else 'FALLO'))
    print()
    if ok:
        print('RESULTADO: OK  nombre, tipo y modo del OPEN de un canal de fichero')
        sys.exit(0)
    print('RESULTADO: FALLO')
    sys.exit(1)


if __name__ == '__main__':
    main()
