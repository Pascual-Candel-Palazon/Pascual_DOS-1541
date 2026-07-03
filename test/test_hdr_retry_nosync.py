#!/usr/bin/env python3
# Regresion del cuelgue real: disk_read_hdr_retry no comprobaba el timeout de
# disk_wait_sync y llamaba a disk_read10 (espera SIN limite por la bandera V)
# incluso sin SYNC. Sin disco, eso colgaba la unidad para siempre (motor y
# LED encendidos, reproducido y confirmado: sin el fix, la CPU no retorna ni
# tras 20 millones de instrucciones simuladas). Aqui se fuerza VIA2_PB a
# "nunca hay SYNC" (bit 7 = 1 permanente) y se comprueba que la rutina
# retorna de todas formas, en el peor caso legitimo (24 reintentos x 65536
# ciclos de espera de SYNC cada uno, unas 6.3 millones de instrucciones).
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_gcr import load_labels, make_machine

VIA2_PB = 0x1C00
# Peor caso legitimo (24 reintentos, cada uno agotando el timeout de 65536
# ciclos de disk_wait_sync) es ~6.3 millones de instrucciones; se da margen.
STEP_BUDGET = 8_000_000


def call_sub_budget(mpu, mem, addr, budget):
    mem[0x0200] = 0x20
    mem[0x0201] = addr & 0xFF
    mem[0x0202] = addr >> 8
    mem[0x0203] = 0x4C
    mem[0x0204] = 0x03
    mem[0x0205] = 0x02
    mpu.pc = 0x0200
    mpu.sp = 0xFF
    for _ in range(budget):
        mpu.step()
        if mpu.pc == 0x0203:
            return True
    return False


def main():
    mpu, mem = make_machine()
    labels = load_labels('dos.lbl')

    mem[VIA2_PB] = 0x80  # SYNC nunca detectado

    returned = call_sub_budget(mpu, mem, labels['disk_read_hdr_retry'],
                                STEP_BUDGET)
    if not returned:
        print('RESULTADO: FALLO  disk_read_hdr_retry no ha retornado tras '
              '%d instrucciones (cuelgue)' % STEP_BUDGET)
        sys.exit(1)

    err = mem[labels['hdr_error']]
    print('hdr_error tras agotar los reintentos sin SYNC: $%02X' % err)
    if err == 0xFF:
        print('RESULTADO: OK  disk_read_hdr_retry retorna sin colgarse y '
              'reporta el fallo')
        sys.exit(0)
    print('RESULTADO: FALLO  hdr_error inesperado')
    sys.exit(1)


if __name__ == '__main__':
    main()
