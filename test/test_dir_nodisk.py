#!/usr/bin/env python3
# Reproduccion del fallo: LOAD"$",8 sin disco genera un listado a partir de
# basura porque disk_build_dir no comprueba el error de la lectura de la BAM.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_gcr import load_labels, make_machine, call_sub

LIST_BUF = 0x0300
BAM_BUF_OFF_NAME = 144


def stub_read_fail(mem, labels):
    # Sustituye disk_read_sector_hw y disk_find_sector_hw por un stub que
    # simula "sin disco": fsec_error = $FF y RTS. (LDA #$FF; STA fsec_error; RTS)
    fsec = labels['fsec_error']
    stub = [0xA9, 0xFF, 0x8D, fsec & 0xFF, (fsec >> 8) & 0xFF, 0x60]
    for name in ('disk_read_sector_hw', 'disk_find_sector_hw'):
        addr = labels[name]
        for i, b in enumerate(stub):
            mem[addr + i] = b


def fill_garbage(mem, labels):
    # Simula un buffer no leido: rellena BAM_BUF y DATA_DEC_BUF con basura que
    # incluye un $00 en mitad del nombre del disco (caso realista de RAM sucia).
    bam = 0x0600
    dd = 0x0400
    pattern = [0x12, 0x22, 0x55, 0x00, 0x80, 0x01, 0x22, 0xA0,
               0xA0, 0xA0, 0xA0, 0xA0, 0xA0, 0xA0, 0xA0, 0xA0]
    for i in range(256):
        b = pattern[i % len(pattern)]
        mem[bam + i] = b
        mem[dd + 1 + i] = b


def main():
    mpu, mem = make_machine()
    labels = load_labels('dos.lbl')

    stub_read_fail(mem, labels)
    fill_garbage(mem, labels)

    mem[labels['list_ptr']] = LIST_BUF & 0xFF
    mem[labels['list_ptr'] + 1] = (LIST_BUF >> 8) & 0xFF

    call_sub(mpu, mem, labels['disk_build_dir'])

    end = mem[labels['list_ptr']] | (mem[labels['list_ptr'] + 1] << 8)
    length = end - LIST_BUF
    data = bytes(mem[LIST_BUF + i] for i in range(max(length, 0)))
    print('fsec_error tras disk_build_dir: $%02X' % mem[labels['fsec_error']])
    print('bytes emitidos en el listado: %d' % length)
    print('volcado: %s' % data.hex(' '))

    # Un programa valido vacio = solo $00 $00 (3-4 bytes
    # tras el load address). Si la longitud es grande, estamos enviando basura.
    if len(data) > 6:
        print('VEREDICTO: FALLO. Se transmite un listado de %d bytes construido '
              'sobre un buffer sin leer.' % len(data))
        sys.exit(1)
    else:
        print('VEREDICTO: OK. Sin disco se transmite un programa vacio limpio.')
        sys.exit(0)


if __name__ == '__main__':
    main()
