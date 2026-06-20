#!/usr/bin/env python3
# ============================================================================
#  test_save.py  ::  SAVE completo (asignacion BAM + cadena + directorio)
# ----------------------------------------------------------------------------
#  Verifica un guardado de fichero de cabo a rabo usando las primitivas de la
#  ROM: bam_alloc_next asigna los bloques, file_build_block construye la cadena
#  y dir_make_entry crea la entrada de directorio. Luego un LOAD (dir_find_in_buf
#  + seguir la cadena) confirma que el contenido se recupera byte a byte. El
#  harness orquesta el flujo (la I/O fisica seria la capa de IRQ).
# ============================================================================
import sys
from test_gcr import load_labels, make_machine, call_sub
from test_bam import build_bam, BAM_BUF
from test_dir import build_dir_sector, load_dir, set_name, CLOSED, TYPE_PRG
from test_file import read_file, CHAIN_BUF, IN_BUF

DIR_BUF = 0x0700


def set_ptr(mem, zp, addr):
    mem[zp] = addr & 0xFF
    mem[zp + 1] = addr >> 8


def total_free(mpu, mem, labels):
    call_sub(mpu, mem, labels["bam_total_free"])
    return mem[labels["bam_total_lo"]] | (mem[labels["bam_total_hi"]] << 8)


def save_file(mpu, mem, labels, name, data, start_track=1):
    chunks = [data[i:i + 254] for i in range(0, len(data), 254)] or [b""]

    # 1) asignar un bloque libre por chunk (BAM en BAM_BUF)
    coords = []
    mem[labels["bam_track"]] = start_track
    for _ in chunks:
        call_sub(mpu, mem, labels["bam_alloc_next"])
        if mem[labels["alloc_ok"]] != 0xFF:
            return None
        coords.append((mem[labels["alloc_track"]], mem[labels["alloc_sector"]]))

    # 2) crear la entrada de directorio PRIMERO (usa DIR_BUF = $0700), antes de
    #    construir los bloques de datos, que reutilizan ese mismo buffer.
    set_name(mem, name)
    mem[labels["dir_ftype"]] = CLOSED | TYPE_PRG
    mem[labels["dir_track"]] = coords[0][0]
    mem[labels["dir_sector"]] = coords[0][1]
    mem[labels["dir_blocks_lo"]] = len(chunks) & 0xFF
    mem[labels["dir_blocks_hi"]] = (len(chunks) >> 8) & 0xFF
    call_sub(mpu, mem, labels["dir_make_entry"])
    if mem[labels["dir_found"]] != 0xFF:
        return None
    dir_sector = [mem[DIR_BUF + k] for k in range(256)]

    # 3) construir la cadena de bloques (cada uno enlaza al siguiente)
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

    return coords, blocks, dir_sector, len(chunks)


def main():
    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")
    r = []

    # disco vacio: BAM con todo libre, directorio vacio
    load_bam = build_bam({})
    for i, b in enumerate(load_bam):
        mem[BAM_BUF + i] = b
    dir_empty = build_dir_sector([], link=(0, 0xFF))
    load_dir(mem, dir_empty)

    free_before = total_free(mpu, mem, labels)

    # guardar un fichero de 600 bytes (3 bloques) llamado HELLO
    data = bytes((i * 9 + 2) & 0xFF for i in range(600))
    res = save_file(mpu, mem, labels, "HELLO", data, start_track=1)
    ok = res is not None
    coords, blocks, dir_sector, nblocks = res if ok else ([], {}, [], 0)

    # bloques asignados distintos y consecutivos por la politica simple
    ok &= (len(set(coords)) == 3 and nblocks == 3)
    # ninguno en la pista 18
    ok &= all(t != 18 for (t, s) in coords)
    print(f"[asignacion] coords={coords} distintos={len(set(coords))==3} "
          f"sin_t18={all(t!=18 for t,s in coords)} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # el BAM refleja 3 bloques menos libres
    free_after = total_free(mpu, mem, labels)
    ok = (free_after == free_before - 3)
    print(f"[BAM] libres {free_before}->{free_after} (-3) -> "
          f"{'OK' if ok else 'FALLO'}")
    r.append(ok)

    # LOAD de verificacion: buscar HELLO en el directorio y seguir la cadena
    load_dir(mem, dir_sector)
    set_name(mem, "HELLO")
    call_sub(mpu, mem, labels["dir_find_in_buf"])
    found = mem[labels["dir_found"]] == 0xFF
    st = mem[labels["dir_track"]]
    ss = mem[labels["dir_sector"]]
    got = read_file(mpu, mem, labels, blocks, (st, ss)) if found else b""
    ok = (found and (st, ss) == coords[0] and got == data)
    print(f"[SAVE->LOAD HELLO] found={found} start=({st},{ss}) "
          f"len={len(got)} ok={got==data} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # guardar un segundo fichero y comprobar que no pisa el primero.
    # el BAM persiste (HELLO ya marcado); recargamos el directorio con HELLO,
    # porque el LOAD anterior reuso ese buffer.
    load_dir(mem, dir_sector)
    data2 = bytes((255 - (i % 256)) for i in range(300))
    res2 = save_file(mpu, mem, labels, "WORLD", data2, start_track=1)
    ok = res2 is not None
    if ok:
        coords2, blocks2, dir_sector2, _ = res2
        ok &= set(coords2).isdisjoint(set(coords))
        # verificar que ambos ficheros se leen correctamente del directorio final
        load_dir(mem, dir_sector2)
        set_name(mem, "HELLO")
        call_sub(mpu, mem, labels["dir_find_in_buf"])
        h_found = mem[labels["dir_found"]] == 0xFF
        load_dir(mem, dir_sector2)
        set_name(mem, "WORLD")
        call_sub(mpu, mem, labels["dir_find_in_buf"])
        w_found = mem[labels["dir_found"]] == 0xFF
        wt = mem[labels["dir_track"]]
        ws = mem[labels["dir_sector"]]
        got2 = read_file(mpu, mem, labels, blocks2, (wt, ws)) if w_found else b""
        ok &= (h_found and w_found and got2 == data2)
    print(f"[segundo fichero WORLD] coords2={res2[0] if res2 else None} "
          f"disjunto={set(res2[0]).isdisjoint(set(coords)) if res2 else False} "
          f"ambos_en_dir={ok} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    print()
    if all(r):
        print("RESULTADO: OK  SAVE completo (BAM, cadena y directorio) + LOAD")
        sys.exit(0)
    print("RESULTADO: FALLO")
    sys.exit(1)


if __name__ == "__main__":
    main()
