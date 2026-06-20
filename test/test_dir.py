#!/usr/bin/env python3
# ============================================================================
#  test_dir.py  ::  directorio del disco, logica pura
# ----------------------------------------------------------------------------
#  Verifica la lectura de entradas de un sector de directorio, la busqueda por
#  nombre, la extraccion de tipo/track/sector/tamano y el enlace al siguiente
#  sector. Formato publico del .d64. El recorrido entre sectores enlazados lo
#  orquesta el harness (la carga del siguiente sector es I/O de disco).
# ============================================================================
import sys
from test_gcr import load_labels, make_machine, call_sub

DIR_BUF = 0x0700
NAME_BUF = 0x0280

TYPE_DEL, TYPE_SEQ, TYPE_PRG, TYPE_USR, TYPE_REL = 0, 1, 2, 3, 4
CLOSED = 0x80


def build_dir_sector(entries, link=(0, 255)):
    sec = [0] * 256
    sec[0], sec[1] = link
    for i, e in enumerate(entries):
        base = i * 32
        sec[base + 2] = e["type"]
        sec[base + 3] = e["track"]
        sec[base + 4] = e["sector"]
        nm = e["name"].encode("ascii")
        for j in range(16):
            sec[base + 5 + j] = nm[j] if j < len(nm) else 0xA0
        sec[base + 30] = e["blocks"] & 0xFF
        sec[base + 31] = (e["blocks"] >> 8) & 0xFF
    return sec


def load_dir(mem, sec):
    for i, b in enumerate(sec):
        mem[DIR_BUF + i] = b


def set_name(mem, name):
    b = name.encode("ascii")
    for j in range(16):
        mem[NAME_BUF + j] = b[j] if j < len(b) else 0xA0


def find(mpu, mem, labels, name):
    set_name(mem, name)
    call_sub(mpu, mem, labels["dir_find_in_buf"])
    if mem[labels["dir_found"]] != 0xFF:
        return None
    return {
        "ftype": mem[labels["dir_ftype"]],
        "track": mem[labels["dir_track"]],
        "sector": mem[labels["dir_sector"]],
        "blocks": mem[labels["dir_blocks_lo"]] | (mem[labels["dir_blocks_hi"]] << 8),
    }


def main():
    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")
    r = []

    entries = [
        {"type": CLOSED | TYPE_PRG, "track": 17, "sector": 0,
         "name": "GAME", "blocks": 25},
        {"type": CLOSED | TYPE_SEQ, "track": 18, "sector": 5,
         "name": "NOTES", "blocks": 3},
        {"type": TYPE_DEL, "track": 0, "sector": 0,
         "name": "DELETED", "blocks": 0},
        {"type": CLOSED | TYPE_PRG, "track": 20, "sector": 10,
         "name": "LOADER", "blocks": 258},
    ]
    sec = build_dir_sector(entries, link=(0, 0xFF))
    load_dir(mem, sec)

    # buscar un PRG presente
    f = find(mpu, mem, labels, "GAME")
    ok = (f is not None and f["ftype"] == (CLOSED | TYPE_PRG) and
          f["track"] == 17 and f["sector"] == 0 and f["blocks"] == 25)
    print(f"[buscar GAME] {f} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # buscar un SEQ presente
    f = find(mpu, mem, labels, "NOTES")
    ok = (f is not None and f["ftype"] == (CLOSED | TYPE_SEQ) and
          f["track"] == 18 and f["sector"] == 5 and f["blocks"] == 3)
    print(f"[buscar NOTES] {f} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # tamano de 16 bits (258 bloques)
    f = find(mpu, mem, labels, "LOADER")
    ok = (f is not None and f["blocks"] == 258)
    print(f"[buscar LOADER blocks=258] {f} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # una entrada borrada (tipo 0) no debe encontrarse
    f = find(mpu, mem, labels, "DELETED")
    ok = (f is None)
    print(f"[entrada borrada ignorada] encontrada={f is not None} -> "
          f"{'OK' if ok else 'FALLO'}")
    r.append(ok)

    # nombre ausente
    f = find(mpu, mem, labels, "MISSING")
    ok = (f is None)
    print(f"[nombre ausente] encontrada={f is not None} -> "
          f"{'OK' if ok else 'FALLO'}")
    r.append(ok)

    # enlace al siguiente sector
    call_sub(mpu, mem, labels["dir_get_link"])
    lt = mem[labels["dir_link_track"]]
    ls = mem[labels["dir_link_sector"]]
    ok = (lt == 0 and ls == 0xFF)
    print(f"[enlace] track={lt} sector={ls} (ultimo) -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # recorrido entre dos sectores enlazados: el fichero esta en el segundo
    sec1 = build_dir_sector(
        [{"type": CLOSED | TYPE_PRG, "track": 1, "sector": 0,
          "name": "FIRST", "blocks": 1}], link=(18, 4))
    sec2 = build_dir_sector(
        [{"type": CLOSED | TYPE_PRG, "track": 30, "sector": 8,
          "name": "TARGET", "blocks": 7}], link=(0, 0xFF))
    chain = {(18, 1): sec1, (18, 4): sec2}

    load_dir(mem, sec1)
    f = find(mpu, mem, labels, "TARGET")
    found_via_chain = None
    if f is None:
        call_sub(mpu, mem, labels["dir_get_link"])
        lt = mem[labels["dir_link_track"]]
        ls = mem[labels["dir_link_sector"]]
        if lt != 0 and (lt, ls) in chain:
            load_dir(mem, chain[(lt, ls)])
            found_via_chain = find(mpu, mem, labels, "TARGET")
    ok = (found_via_chain is not None and found_via_chain["track"] == 30 and
          found_via_chain["sector"] == 8 and found_via_chain["blocks"] == 7)
    print(f"[recorrido 2 sectores] {found_via_chain} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # --- linea de listado de directorio (LOAD "$",8) ---
    LIST_OUT = 0x2200
    sec = build_dir_sector([
        {"type": 0x82, "track": 17, "sector": 0, "name": "GAME", "blocks": 12},
    ], link=(0, 0xFF))
    load_dir(mem, sec)
    mem[labels["list_ptr"]] = LIST_OUT & 0xFF
    mem[labels["list_ptr"] + 1] = (LIST_OUT >> 8) & 0xFF
    mem[labels["dir_slot"]] = 0
    call_sub(mpu, mem, labels["dir_make_listing_line"])
    end = mem[labels["list_ptr"]] | (mem[labels["list_ptr"] + 1] << 8)
    got = bytes(mem[LIST_OUT + i] for i in range(end - LIST_OUT))
    expected = (bytes([0x01, 0x01, 12, 0]) + b"  " + b'"' + b"GAME" + b'"' +
                b" " * 13 + b"PRG" + bytes([0]))
    ok = (got == expected)
    print(f"[listado PRG GAME 12] {got!r} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # segunda entrada: nombre de 16 y 3 digitos de bloques (relleno minimo)
    sec = build_dir_sector([
        {"type": 0x81, "track": 1, "sector": 0, "name": "ABCDEFGHIJKLMNOP",
         "blocks": 254},
    ], link=(0, 0xFF))
    load_dir(mem, sec)
    mem[labels["list_ptr"]] = LIST_OUT & 0xFF
    mem[labels["list_ptr"] + 1] = (LIST_OUT >> 8) & 0xFF
    mem[labels["dir_slot"]] = 0
    call_sub(mpu, mem, labels["dir_make_listing_line"])
    end = mem[labels["list_ptr"]] | (mem[labels["list_ptr"] + 1] << 8)
    got2 = bytes(mem[LIST_OUT + i] for i in range(end - LIST_OUT))
    expected2 = (bytes([0x01, 0x01, 254, 0]) + b" " + b'"' + b"ABCDEFGHIJKLMNOP" +
                 b'"' + b" " * 1 + b"SEQ" + bytes([0]))
    ok = (got2 == expected2)
    print(f"[listado SEQ 16ch 254] {got2!r} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # titulo y linea de cierre del listado
    BAM_BUF = 0x0600
    NAME_BUF2 = 0x0268
    set_name(mem, "TEST DISK")
    mem[NAME_BUF2] = ord("1")
    mem[NAME_BUF2 + 1] = ord("A")
    call_sub(mpu, mem, labels["disk_format_bam"])
    call_sub(mpu, mem, labels["disk_write_header"])

    mem[labels["list_ptr"]] = LIST_OUT & 0xFF
    mem[labels["list_ptr"] + 1] = (LIST_OUT >> 8) & 0xFF
    call_sub(mpu, mem, labels["dir_make_title_line"])
    end = mem[labels["list_ptr"]] | (mem[labels["list_ptr"] + 1] << 8)
    title = bytes(mem[LIST_OUT + i] for i in range(end - LIST_OUT))
    exp_title = (bytes([0x01, 0x01, 0x00, 0x00, 0x12, 0x22]) + b"TEST DISK" +
                 bytes([0xA0]) * 7 + bytes([0x22, 0x20]) + b"1A" +
                 bytes([0x20]) + b"2A" + bytes([0x00]))
    ok = (title == exp_title)
    print(f"[listado titulo] {title!r} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    mem[labels["list_ptr"]] = LIST_OUT & 0xFF
    mem[labels["list_ptr"] + 1] = (LIST_OUT >> 8) & 0xFF
    call_sub(mpu, mem, labels["dir_make_free_line"])
    call_sub(mpu, mem, labels["dir_make_end"])
    end = mem[labels["list_ptr"]] | (mem[labels["list_ptr"] + 1] << 8)
    free = bytes(mem[LIST_OUT + i] for i in range(end - LIST_OUT))
    # disco recien formateado: 664 bloques libres = $0298
    exp_free = (bytes([0x01, 0x01, 0x98, 0x02]) + b"BLOCKS FREE." +
                bytes([0x00, 0x00, 0x00]))
    ok = (free == exp_free)
    print(f"[listado cierre 664] {free!r} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    print()
    if all(r):
        print("RESULTADO: OK  directorio: busqueda, extraccion, enlace y listado")
        sys.exit(0)
    print("RESULTADO: FALLO")
    sys.exit(1)


if __name__ == "__main__":
    main()
