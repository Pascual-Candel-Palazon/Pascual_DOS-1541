#!/usr/bin/env python3
# ============================================================================
#  test_file.py  ::  lectura de fichero por cadena de bloques (logica pura)
# ----------------------------------------------------------------------------
#  Verifica el seguimiento de la cadena de bloques de un fichero: enlace
#  track/sector, deteccion del ultimo bloque y bytes utiles, y el reensamblado
#  del contenido. Incluye un caso end-to-end: resolver un nombre en el
#  directorio y leer el fichero completo (equivalente logico de un LOAD). La
#  carga de cada bloque (I/O de disco) la orquesta el harness.
# ============================================================================
import sys
from test_gcr import load_labels, make_machine, call_sub
from test_dir import build_dir_sector, load_dir, set_name, CLOSED, TYPE_PRG

CHAIN_BUF = 0x0700
FILE_OUT = 0x2000
IN_BUF = 0x2100


def make_file_chain(data, coords):
    """Parte data en bloques de 254 y los encadena por las coordenadas dadas."""
    chunks = [data[i:i + 254] for i in range(0, len(data), 254)] or [b""]
    assert len(coords) >= len(chunks), "faltan coordenadas de bloque"
    blocks = {}
    for i, chunk in enumerate(chunks):
        sec = [0] * 256
        if i < len(chunks) - 1:
            sec[0], sec[1] = coords[i + 1]
        else:
            sec[0] = 0
            sec[1] = len(chunk) + 1          # offset del ultimo byte util
        for j, b in enumerate(chunk):
            sec[2 + j] = b
        blocks[coords[i]] = sec
    return blocks, coords[0]


def read_file(mpu, mem, labels, blocks, start):
    set_ptr(mem, labels["out_ptr"], FILE_OUT)
    t, s = start
    total = 0
    guard = 0
    while True:
        guard += 1
        assert guard < 2000, "cadena demasiado larga (posible ciclo)"
        sec = blocks[(t, s)]
        for i, b in enumerate(sec):
            mem[CHAIN_BUF + i] = b
        call_sub(mpu, mem, labels["file_block_process"])
        total += mem[labels["file_nbytes"]]
        nt = mem[labels["file_next_track"]]
        ns = mem[labels["file_next_sector"]]
        if nt == 0:
            break
        t, s = nt, ns
    return bytes(mem[FILE_OUT + i] for i in range(total))


def set_ptr(mem, zp, addr):
    mem[zp] = addr & 0xFF
    mem[zp + 1] = addr >> 8


def write_file(mpu, mem, labels, data, coords):
    """Construye los bloques del fichero con file_build_block (la rutina de
    escritura de la ROM) y los devuelve como dict {(t,s): sector}."""
    chunks = [data[i:i + 254] for i in range(0, len(data), 254)] or [b""]
    assert len(coords) >= len(chunks)
    blocks = {}
    for i, chunk in enumerate(chunks):
        for j, b in enumerate(chunk):
            mem[IN_BUF + j] = b
        set_ptr(mem, labels["in_ptr"], IN_BUF)
        mem[labels["file_nbytes"]] = len(chunk)
        if i < len(chunks) - 1:
            mem[labels["file_next_track"]] = coords[i + 1][0]
            mem[labels["file_next_sector"]] = coords[i + 1][1]
        else:
            mem[labels["file_next_track"]] = 0
        call_sub(mpu, mem, labels["file_build_block"])
        blocks[coords[i]] = [mem[CHAIN_BUF + k] for k in range(256)]
    return blocks, coords[0]


def main():
    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")
    r = []

    # fichero corto (un bloque, < 254 bytes)
    data = bytes((i * 7 + 3) & 0xFF for i in range(100))
    blocks, start = make_file_chain(data, [(17, 0)])
    got = read_file(mpu, mem, labels, blocks, start)
    ok = (got == data)
    print(f"[fichero 100 bytes, 1 bloque] len={len(got)} ok={ok} -> "
          f"{'OK' if ok else 'FALLO'}")
    r.append(ok)

    # fichero de exactamente 254 bytes (un bloque lleno y final)
    data = bytes((255 - i) & 0xFF for i in range(254))
    blocks, start = make_file_chain(data, [(17, 1)])
    got = read_file(mpu, mem, labels, blocks, start)
    ok = (got == data)
    print(f"[fichero 254 bytes, bloque lleno] len={len(got)} ok={ok} -> "
          f"{'OK' if ok else 'FALLO'}")
    r.append(ok)

    # fichero multi-bloque (600 bytes -> 254 + 254 + 92)
    data = bytes((i * 13 + 1) & 0xFF for i in range(600))
    blocks, start = make_file_chain(data, [(17, 0), (17, 3), (18, 6)])
    got = read_file(mpu, mem, labels, blocks, start)
    ok = (got == data)
    print(f"[fichero 600 bytes, 3 bloques] len={len(got)} ok={ok} -> "
          f"{'OK' if ok else 'FALLO'}")
    r.append(ok)

    # 255 bytes -> 254 + 1 (segundo bloque con un solo byte util)
    data = bytes((i ^ 0x3C) & 0xFF for i in range(255))
    blocks, start = make_file_chain(data, [(20, 0), (20, 1)])
    got = read_file(mpu, mem, labels, blocks, start)
    ok = (got == data)
    print(f"[fichero 255 bytes, 254+1] len={len(got)} ok={ok} -> "
          f"{'OK' if ok else 'FALLO'}")
    r.append(ok)

    # --- end-to-end: directorio -> nombre -> cadena -> contenido (un LOAD) ---
    prog = bytes((i * 3 + 5) & 0xFF for i in range(700))
    coords = [(17, 0), (17, 2), (17, 4)]
    blocks, start = make_file_chain(prog, coords)
    dir_sec = build_dir_sector([
        {"type": CLOSED | TYPE_PRG, "track": start[0], "sector": start[1],
         "name": "MYPROG", "blocks": len(coords)},
    ], link=(0, 0xFF))
    load_dir(mem, dir_sec)
    set_name(mem, "MYPROG")
    call_sub(mpu, mem, labels["dir_find_in_buf"])
    found = mem[labels["dir_found"]] == 0xFF
    st = mem[labels["dir_track"]]
    ss = mem[labels["dir_sector"]]
    got = read_file(mpu, mem, labels, blocks, (st, ss)) if found else b""
    ok = (found and (st, ss) == start and got == prog)
    print(f"[end-to-end LOAD MYPROG] found={found} start=({st},{ss}) "
          f"len={len(got)} ok={got==prog} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # --- escritura de fichero: round-trip write -> read (SAVE -> LOAD) ---
    for desc, data, coords in [
        ("100 bytes 1 bloque", bytes((i * 5 + 1) & 0xFF for i in range(100)),
         [(19, 0)]),
        ("254 bytes 1 bloque", bytes((i ^ 0x7E) & 0xFF for i in range(254)),
         [(19, 1)]),
        ("800 bytes 4 bloques", bytes((i * 11 + 7) & 0xFF for i in range(800)),
         [(19, 0), (19, 3), (19, 6), (20, 0)]),
    ]:
        wblocks, start = write_file(mpu, mem, labels, data, coords)
        # comparar con la referencia de construccion
        rblocks, _ = make_file_chain(data, coords)
        same = all(wblocks[c] == rblocks[c] for c in wblocks)
        # round-trip: releer lo escrito
        got = read_file(mpu, mem, labels, wblocks, start)
        ok = same and (got == data)
        print(f"[write->read {desc}] bloques==ref={same} roundtrip={got==data} "
              f"-> {'OK' if ok else 'FALLO'}")
        r.append(ok)

    print()
    if all(r):
        print("RESULTADO: OK  lectura y escritura de fichero por cadena de bloques")
        sys.exit(0)
    print("RESULTADO: FALLO")
    sys.exit(1)


if __name__ == "__main__":
    main()
