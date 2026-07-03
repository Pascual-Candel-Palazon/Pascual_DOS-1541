#!/usr/bin/env python3
# Regresion: disk_find_current_track hacia cur_track = hdr_track SIEMPRE,
# incluso con hdr_error != 0 (sin disco, ninguna cabecera valida). Como
# hdr_track nunca se llega a escribir en ese caso, cur_track se "olvidaba" y
# volvia a 0 en cada intento, forzando un reseek fisico completo (pista 0 a
# 18) en cada operacion sin disco, aunque el cabezal ya estuviera alli.
# Verifica que, tras una primera lectura con exito que deja cur_track=18,
# una segunda lectura sin exito (sin disco) NO da ningun paso fisico y
# conserva cur_track.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_gcr import load_labels, make_machine

VIA2_PB = 0x1C00
STEP_BUDGET = 8_000_000


def call_budget(mpu, mem, addr, budget, labels):
    mem[0x0200] = 0x20
    mem[0x0201] = addr & 0xFF
    mem[0x0202] = addr >> 8
    mem[0x0203] = 0x4C
    mem[0x0204] = 0x03
    mem[0x0205] = 0x02
    mpu.pc = 0x0200
    mpu.sp = 0xFF
    steps = 0
    for _ in range(budget):
        prev_pc = mpu.pc
        mpu.step()
        if prev_pc in (labels['disk_step_in'], labels['disk_step_out']):
            steps += 1
        if mpu.pc == 0x0203:
            return steps
    return None


def main():
    mpu, mem = make_machine()
    labels = load_labels('dos.lbl')

    mem[labels['want_track']] = 18

    # Primera llamada: sin disco (fuerza el mismo escenario que en el fix
    # anterior), termina con cur_track=18 tras el reseek inicial legitimo.
    mem[VIA2_PB] = 0x80
    steps1 = call_budget(mpu, mem, labels['disk_read_sector_hw'],
                          STEP_BUDGET, labels)
    if steps1 is None:
        print('RESULTADO: FALLO  primera llamada no ha retornado')
        sys.exit(1)
    cur1 = mem[labels['cur_track']]
    print('llamada 1: pasos fisicos=%d cur_track=%d' % (steps1, cur1))

    # Segunda llamada: sigue sin disco. No deberia dar NINGUN paso fisico,
    # porque cur_track ya estaba en 18 y debe conservarse.
    steps2 = call_budget(mpu, mem, labels['disk_read_sector_hw'],
                          STEP_BUDGET, labels)
    if steps2 is None:
        print('RESULTADO: FALLO  segunda llamada no ha retornado')
        sys.exit(1)
    cur2 = mem[labels['cur_track']]
    print('llamada 2: pasos fisicos=%d cur_track=%d' % (steps2, cur2))

    if steps2 == 0 and cur2 == cur1:
        print('RESULTADO: OK  la posicion se conserva, sin reseek fisico '
              'innecesario')
        sys.exit(0)
    print('RESULTADO: FALLO  la segunda llamada ha movido el cabezal de '
          'mas')
    sys.exit(1)


if __name__ == '__main__':
    main()
