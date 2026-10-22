#!/usr/bin/env python3
# ============================================================================
#  test_cmd.py  ::  canal de estado / error (canal 15)
# ----------------------------------------------------------------------------
#  Verifica la construccion de la cadena de estado "NN,MENSAJE,TT,SS" + CR que
#  el C64 lee del canal 15 para conocer el resultado de una operacion. Codigos
#  de error del formato publico del DOS.
# ============================================================================
import sys
from test_gcr import load_labels, make_machine, call_sub
from test_bam import build_bam, BAM_BUF
from test_dir import load_dir, set_name, build_dir_sector
from test_file import read_file, CHAIN_BUF
from test_save import save_file, total_free, set_ptr

STATUS_BUF = 0x0290
CMD_BUF = 0x0240
NAME_BUF = 0x0280
NAME_BUF2 = 0x0268
DIR_BUF = 0x0700


def read_name2(mem):
    return bytes(mem[NAME_BUF2 + i] for i in range(16))


def build_status(mpu, mem, labels, code, track, sector):
    mem[labels["err_code"]] = code
    mem[labels["err_track"]] = track
    mem[labels["err_sector"]] = sector
    call_sub(mpu, mem, labels["err_build_status"])
    out = []
    i = 0
    while True:
        b = mem[STATUS_BUF + i]
        out.append(b)
        if b == 0x0D or i > 60:
            break
        i += 1
    return bytes(out).decode("ascii")


def put_cmd(mem, text):
    b = text.encode("ascii")
    for i, c in enumerate(b):
        mem[CMD_BUF + i] = c
    mem[CMD_BUF + len(b)] = 0


def read_name(mem):
    return bytes(mem[NAME_BUF + i] for i in range(16))


def pad(name):
    b = name.encode("ascii")
    return b + bytes([0xA0] * (16 - len(b)))


def free_chain(mpu, mem, labels, blocks, start):
    set_ptr(mem, labels["out_ptr"], 0x3000)   # destino temporal (datos ignorados)
    t, s = start
    freed = 0
    while True:
        sec = blocks[(t, s)]
        for i, b in enumerate(sec):
            mem[CHAIN_BUF + i] = b
        call_sub(mpu, mem, labels["file_block_process"])
        mem[labels["bam_track"]] = t
        mem[labels["bam_sector"]] = s
        call_sub(mpu, mem, labels["bam_free_block"])
        freed += 1
        nt = mem[labels["file_next_track"]]
        ns = mem[labels["file_next_sector"]]
        if nt == 0:
            break
        t, s = nt, ns
    return freed


def main():
    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")
    r = []

    cases = [
        (0, 0, 0, "00, OK,00,00\r"),
        (1, 0, 0, "01, FILES SCRATCHED,00,00\r"),
        (21, 18, 0, "21,READ ERROR,18,00\r"),
        (30, 0, 0, "30,SYNTAX ERROR,00,00\r"),
        (34, 0, 0, "34,SYNTAX ERROR,00,00\r"),
        (62, 18, 1, "62, FILE NOT FOUND,18,01\r"),
        (63, 0, 0, "63, FILE EXISTS,00,00\r"),
        (72, 0, 0, "72,DISK FULL,00,00\r"),
        (73, 0, 0, "73,PASCUAL DOS 1541,00,00\r"),
        (99, 5, 9, "99,ERROR,05,09\r"),      # codigo desconocido -> generico
        (20, 18, 5, "20,ERROR,18,05\r"),     # 20 no esta en la tabla -> generico
    ]
    for code, t, s, expected in cases:
        got = build_status(mpu, mem, labels, code, t, s)
        ok = (got == expected)
        shown = got.replace("\r", "\\r")
        print(f"[code {code:02d} t{t} s{s}] '{shown}' -> {'OK' if ok else 'FALLO'}")
        if not ok:
            print(f"    esperado: '{expected.replace(chr(13), chr(92)+'r')}'")
        r.append(ok)

    # --- parseo del nombre de un comando ---
    for cmd, expected, err in [
        ("S:HELLO", pad("HELLO"), 0),
        ("S0:GAME,P", pad("GAME"), 0),
        ("S:0123456789ABCDEFGH", pad("0123456789ABCDEF"), 0),  # truncado a 16
        ("NOCOLON", None, 0xFF),
    ]:
        put_cmd(mem, cmd)
        call_sub(mpu, mem, labels["cmd_parse_name"])
        ce = mem[labels["cmd_error"]]
        if err == 0xFF:
            ok = (ce == 0xFF)
        else:
            ok = (ce == 0 and read_name(mem) == expected)
        print(f"[parse '{cmd}'] err=${ce:02X} name={read_name(mem)!r} -> "
              f"{'OK' if ok else 'FALLO'}")
        r.append(ok)

    # --- SCRATCH end-to-end: guardar, borrar, verificar ---
    bam = build_bam({})
    for i, b in enumerate(bam):
        mem[BAM_BUF + i] = b
    load_dir(mem, build_dir_sector([], link=(0, 0xFF)))
    free0 = total_free(mpu, mem, labels)

    data = bytes((i * 7 + 1) & 0xFF for i in range(600))   # 3 bloques
    coords, blocks, dir_sector, nblk = save_file(mpu, mem, labels, "HELLO", data)
    free_after_save = total_free(mpu, mem, labels)

    # SCRATCH "S:HELLO"
    load_dir(mem, dir_sector)
    put_cmd(mem, "S:HELLO")
    call_sub(mpu, mem, labels["cmd_parse_name"])
    call_sub(mpu, mem, labels["dir_find_in_buf"])
    found = mem[labels["dir_found"]] == 0xFF
    start = (mem[labels["dir_track"]], mem[labels["dir_sector"]])
    # marcar la entrada como borrada (antes de reutilizar el buffer)
    call_sub(mpu, mem, labels["dir_scratch_entry"])
    dir_after = [mem[DIR_BUF + k] for k in range(256)]
    # liberar la cadena de bloques en el BAM
    freed = free_chain(mpu, mem, labels, blocks, start)
    free_after_scratch = total_free(mpu, mem, labels)

    # verificar: el fichero ya no esta y los bloques volvieron a estar libres
    load_dir(mem, dir_after)
    set_name(mem, "HELLO")
    call_sub(mpu, mem, labels["dir_find_in_buf"])
    gone = mem[labels["dir_found"]] != 0xFF
    ok = (found and freed == nblk and gone and
          free_after_save == free0 - nblk and free_after_scratch == free0)
    print(f"[SCRATCH HELLO] guardado_libres={free_after_save} "
          f"borrado_libres={free_after_scratch} (orig {free0}) freed={freed} "
          f"entrada_eliminada={gone} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # --- parseo de RENAME ---
    for cmd, new_exp, old_exp, err in [
        ("R:NEWNAME=OLDNAME", pad("NEWNAME"), pad("OLDNAME"), 0),
        ("R0:A=B,X", pad("A"), pad("B"), 0),
        ("R:NOEQUALS", None, None, 0xFF),     # falta '='
        ("R:NEW", None, None, 0xFF),          # falta '='
    ]:
        put_cmd(mem, cmd)
        call_sub(mpu, mem, labels["cmd_parse_rename"])
        ce = mem[labels["cmd_error"]]
        if err == 0xFF:
            ok = (ce == 0xFF)
        else:
            ok = (ce == 0 and read_name2(mem) == new_exp and read_name(mem) == old_exp)
        print(f"[rename-parse '{cmd}'] err=${ce:02X} new={read_name2(mem)!r} "
              f"old={read_name(mem)!r} -> {'OK' if ok else 'FALLO'}")
        r.append(ok)

    # --- RENAME end-to-end: guardar, renombrar, verificar ---
    bam = build_bam({})
    for i, b in enumerate(bam):
        mem[BAM_BUF + i] = b
    load_dir(mem, build_dir_sector([], link=(0, 0xFF)))
    data = bytes((i * 3 + 5) & 0xFF for i in range(400))   # 2 bloques
    coords, blocks, dir_sector, nblk = save_file(mpu, mem, labels, "OLDNAME", data)

    load_dir(mem, dir_sector)
    put_cmd(mem, "R:NEWNAME=OLDNAME")
    call_sub(mpu, mem, labels["cmd_parse_rename"])
    call_sub(mpu, mem, labels["dir_find_in_buf"])     # busca NAME_BUF = OLDNAME
    found_old = mem[labels["dir_found"]] == 0xFF
    t_old = (mem[labels["dir_track"]], mem[labels["dir_sector"]])
    call_sub(mpu, mem, labels["dir_rename_entry"])    # escribe NAME_BUF2 = NEWNAME
    dir_after = [mem[DIR_BUF + k] for k in range(256)]

    # NEWNAME debe existir con el mismo primer bloque; OLDNAME ya no
    load_dir(mem, dir_after)
    set_name(mem, "NEWNAME")
    call_sub(mpu, mem, labels["dir_find_in_buf"])
    found_new = mem[labels["dir_found"]] == 0xFF
    t_new = (mem[labels["dir_track"]], mem[labels["dir_sector"]])

    load_dir(mem, dir_after)
    set_name(mem, "OLDNAME")
    call_sub(mpu, mem, labels["dir_find_in_buf"])
    old_gone = mem[labels["dir_found"]] != 0xFF

    ok = (found_old and found_new and old_gone and t_old == t_new)
    print(f"[RENAME OLDNAME->NEWNAME] viejo@{t_old} nuevo@{t_new} "
          f"viejo_eliminado={old_gone} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # --- NEW: formatear el BAM ---
    for i in range(256):
        mem[BAM_BUF + i] = 0xAA          # basura previa
    call_sub(mpu, mem, labels["disk_format_bam"])
    free_fmt = total_free(mpu, mem, labels)

    def is_free(t, s):
        mem[labels["bam_track"]] = t
        mem[labels["bam_sector"]] = s
        call_sub(mpu, mem, labels["bam_is_free"])
        return mem[labels["bam_result"]] == 0xFF

    hdr_ok = (mem[BAM_BUF] == 18 and mem[BAM_BUF + 1] == 1 and mem[BAM_BUF + 2] == 0x41)
    sys_occ = (not is_free(18, 0)) and (not is_free(18, 1))
    rest_free = is_free(18, 2) and is_free(1, 0) and is_free(35, 16)
    ok = (free_fmt == 664 and hdr_ok and sys_occ and rest_free)
    print(f"[NEW formatear] libres={free_fmt} cabecera={hdr_ok} "
          f"sistema_ocupado={sys_occ} resto_libre={rest_free} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # --- disk_link_valid: validez de un enlace de bloque ---
    def link_valid(t, s):
        mem[labels["file_next_track"]] = t
        mem[labels["file_next_sector"]] = s
        call_sub(mpu, mem, labels["disk_link_valid"])
        return mpu.a == 0xFF

    lv_cases = [
        (1, 0, True), (1, 20, True), (1, 21, False),
        (35, 16, True), (35, 17, False),
        (18, 18, True), (18, 19, False),
        (0, 0, False), (36, 0, False),
    ]
    lv_ok = all(link_valid(t, s) == exp for t, s, exp in lv_cases)
    print(f"[disk_link_valid] {len(lv_cases)} casos -> {'OK' if lv_ok else 'FALLO'}")
    r.append(lv_ok)

    # --- VALIDATE: reconstruir el BAM desde el directorio y las cadenas ---
    # disco con dos ficheros de cadenas conocidas (un solo sector de directorio)
    file_links = {
        (1, 0): (1, 1), (1, 1): (1, 2), (1, 2): (0, 5),   # FILEA: 3 bloques
        (1, 5): (1, 6), (1, 6): (0, 8),                    # FILEB: 2 bloques
    }
    dir_sec = build_dir_sector([
        {"type": 0x82, "track": 1, "sector": 0, "name": "FILEA", "blocks": 3},
        {"type": 0x82, "track": 1, "sector": 5, "name": "FILEB", "blocks": 2},
    ], link=(0, 0xFF))
    dir_sectors = {(18, 1): dir_sec}

    # corromper el BAM con basura antes de validar
    for i in range(256):
        mem[BAM_BUF + i] = 0xAA

    def alloc(t, s):
        mem[labels["bam_track"]] = t
        mem[labels["bam_sector"]] = s
        call_sub(mpu, mem, labels["bam_alloc"])

    # VALIDATE orquestado sobre las rutinas ROM
    call_sub(mpu, mem, labels["disk_format_bam"])      # BAM limpio (marca 18/0,18/1)
    dt, ds = 18, 1
    while dt != 0:
        alloc(dt, ds)                                   # marcar el sector de dir
        sec = dir_sectors[(dt, ds)]
        for i in range(256):
            mem[DIR_BUF + i] = sec[i]
        for slot in range(8):
            base = slot * 32
            if (mem[DIR_BUF + base + 2] & 0x0F) == 0:
                continue
            t, s = mem[DIR_BUF + base + 3], mem[DIR_BUF + base + 4]
            guard = 0
            while t != 0 and guard < 1000:
                guard += 1
                mem[labels["file_next_track"]] = t
                mem[labels["file_next_sector"]] = s
                call_sub(mpu, mem, labels["disk_link_valid"])
                if mpu.a != 0xFF:
                    break
                alloc(t, s)
                t, s = file_links[(t, s)]
        dt, ds = sec[0], sec[1]

    # verificacion independiente: exactamente estos bloques ocupados
    occ = {(1, 0), (1, 1), (1, 2), (1, 5), (1, 6), (18, 0), (18, 1)}
    free_chk = [(1, 3), (1, 4), (1, 7), (2, 0), (35, 0)]
    occ_ok = all(not is_free(t, s) for t, s in occ)
    free_ok = all(is_free(t, s) for t, s in free_chk)
    total_after = total_free(mpu, mem, labels)
    # 5 bloques de fichero en la pista 1 (la pista 18 no cuenta en el total)
    ok = occ_ok and free_ok and total_after == 664 - 5
    print(f"[VALIDATE] ocupados_ok={occ_ok} libres_ok={free_ok} "
          f"total_libres={total_after} (esperado {664 - 5}) -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    print()
    if all(r):
        print("RESULTADO: OK  canal de estado, SCRATCH, RENAME, NEW y VALIDATE")
        sys.exit(0)
    print("RESULTADO: FALLO")
    sys.exit(1)


if __name__ == "__main__":
    main()
