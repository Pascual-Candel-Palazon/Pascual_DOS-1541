#!/usr/bin/env python3
# Validacion del formato .d64 contra la implementacion de referencia de VICE
# (la herramienta c1541). No portamos su codigo: la usamos como caja negra para
# generar discos auteenticos y comparar los bytes que produce contra los que
# generan nuestras rutinas. Nivel B de procedencia (comportamiento observable).
#
# Si c1541 no esta instalado, el test se salta (no es un fallo): la verificacion
# contra VICE es opcional y complementa al harness logico.
import os
import shutil
import subprocess
import sys
import tempfile

from test_gcr import load_labels, make_machine, call_sub
from test_dir import set_name, load_dir, build_dir_sector
from test_save import set_ptr, save_file

BAM_BUF = 0x0600
DIR_BUF = 0x0700
CHAIN_BUF = 0x0700
FILE_OUT = 0x2000


def c1541(args, cwd):
    return subprocess.run(["c1541"] + args, cwd=cwd, capture_output=True, text=True)


def read_sector_ref(d64, track, sector, cwd):
    """Devuelve los 256 bytes del sector (track,sector) de la imagen d64."""
    out = os.path.join(cwd, "sec.bin")
    if os.path.exists(out):
        os.remove(out)
    c1541(d64 + ["-bread", "sec.bin", str(track), str(sector)], cwd)
    with open(out, "rb") as f:
        return f.read()


def main():
    if shutil.which("c1541") is None:
        print("SALTADO: c1541 (VICE) no esta instalado; "
              "la validacion contra la referencia es opcional")
        sys.exit(0)

    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")
    r = []
    work = tempfile.mkdtemp(prefix="dos1541ref_")

    # --- referencia: disco recien formateado ---
    d64 = ["ref.d64"]
    c1541(["-format", "test disk,1a", "d64", "ref.d64"], work)
    ref_bam = read_sector_ref(d64, 18, 0, work)

    # nuestro BAM tras disk_format_bam
    call_sub(mpu, mem, labels["disk_format_bam"])
    our_bam = bytes(mem[BAM_BUF + i] for i in range(256))

    # comparar cabecera (0..3) y bitmap de las 35 pistas (4..143); el nombre y el
    # ID del disco (144..) aun no los escribe nuestro formateo, asi que se omiten
    head_ok = our_bam[0:4] == ref_bam[0:4]
    bitmap_ok = our_bam[4:144] == ref_bam[4:144]
    print(f"[BAM cabecera] nuestro={our_bam[0:4].hex()} "
          f"ref={ref_bam[0:4].hex()} -> {'OK' if head_ok else 'FALLO'}")
    print(f"[BAM bitmap 1..35] {'identico a VICE' if bitmap_ok else 'DIFIERE'} -> "
          f"{'OK' if bitmap_ok else 'FALLO'}")
    if not bitmap_ok:
        for t in range(1, 36):
            o = our_bam[4 + (t - 1) * 4:8 + (t - 1) * 4]
            e = ref_bam[4 + (t - 1) * 4:8 + (t - 1) * 4]
            if o != e:
                print(f"   pista {t}: nuestro={o.hex()} ref={e.hex()}")
    r.append(head_ok)
    r.append(bitmap_ok)

    # total de bloques libres que reporta nuestro BAM == 664 (canonico de VICE)
    call_sub(mpu, mem, labels["bam_total_free"])
    total = mem[labels["bam_total_lo"]] | (mem[labels["bam_total_hi"]] << 8)
    free_ok = (total == 664)
    print(f"[bloques libres] {total} (VICE: 664) -> {'OK' if free_ok else 'FALLO'}")
    r.append(free_ok)

    # --- NEW completo: bitmap + identidad del disco, sector 18/0 entero ---
    def put_cmd(text):
        b = text.encode("ascii")
        for i, c in enumerate(b):
            mem[0x0240 + i] = c
        mem[0x0240 + len(b)] = 0

    put_cmd("N:TEST DISK,1A")
    call_sub(mpu, mem, labels["cmd_parse_format"])
    call_sub(mpu, mem, labels["disk_format_bam"])
    call_sub(mpu, mem, labels["disk_write_header"])
    our_full = bytes(mem[BAM_BUF + i] for i in range(256))
    full_ok = (our_full == ref_bam)
    print(f"[NEW sector 18/0 completo] {'identico a VICE (256 bytes)' if full_ok else 'DIFIERE'} "
          f"-> {'OK' if full_ok else 'FALLO'}")
    if not full_ok:
        for i in range(256):
            if our_full[i] != ref_bam[i]:
                print(f"   offset {i} (${i:02X}): nuestro=${our_full[i]:02X} "
                      f"ref=${ref_bam[i]:02X}")
    r.append(full_ok)

    # --- entrada de directorio: escribir un PRG con c1541 y comparar layout ---
    prg = os.path.join(work, "hello.prg")
    with open(prg, "wb") as f:
        f.write(bytes([0x01, 0x08, 0x0b, 0x08, 0x0a, 0x00, 0x9e,
                       0x32, 0x30, 0x36, 0x31, 0x00, 0x00, 0x00]))
    c1541(d64 + ["-write", prg, "hello"], work)
    ref_dir = read_sector_ref(d64, 18, 1, work)
    ref_blocks = ref_dir[28] | (ref_dir[29] << 8)

    # nuestra entrada para el mismo nombre, tipo PRG cerrado y mismo numero de bloques
    load_dir(mem, build_dir_sector([], link=(0, 0xFF)))
    set_name(mem, "HELLO")
    mem[labels["dir_ftype"]] = 0x82
    mem[labels["dir_track"]] = ref_dir[3]
    mem[labels["dir_sector"]] = ref_dir[4]
    mem[labels["dir_blocks_lo"]] = ref_blocks & 0xFF
    mem[labels["dir_blocks_hi"]] = (ref_blocks >> 8) & 0xFF
    call_sub(mpu, mem, labels["dir_make_entry"])
    our_dir = bytes(mem[DIR_BUF + i] for i in range(32))

    # comparar los campos de la entrada (tipo, track/sector, nombre, bloques)
    type_ok = our_dir[2] == ref_dir[2] == 0x82
    name_ok = our_dir[5:21] == ref_dir[5:21] == (b"HELLO" + bytes([0xA0]) * 11)
    ts_ok = our_dir[3:5] == ref_dir[3:5]
    blk_ok = our_dir[28:30] == ref_dir[28:30]
    print(f"[dir entrada tipo] nuestro=${our_dir[2]:02X} ref=${ref_dir[2]:02X} -> "
          f"{'OK' if type_ok else 'FALLO'}")
    print(f"[dir entrada nombre] {'identico a VICE' if name_ok else 'DIFIERE'} -> "
          f"{'OK' if name_ok else 'FALLO'}")
    print(f"[dir entrada track/sector y bloques] ts={ts_ok} bloques={blk_ok} -> "
          f"{'OK' if (ts_ok and blk_ok) else 'FALLO'}")
    r.extend([type_ok, name_ok, ts_ok, blk_ok])

    # --- lectura de cadena multi-bloque: c1541 escribe, nuestras rutinas leen ---
    orig = bytes([0x01, 0x08]) + bytes((i * 37 + 11) & 0xFF for i in range(600))
    prg2 = os.path.join(work, "orig.prg")
    with open(prg2, "wb") as f:
        f.write(orig)
    c1541(["-format", "big,2b", "d64", "big.d64"], work)
    c1541(["big.d64", "-write", prg2, "bigfile"], work)
    backp = os.path.join(work, "back.prg")
    c1541(["big.d64", "-read", "bigfile", backp], work)
    with open(backp, "rb") as f:
        ref_data = f.read()

    big = ["big.d64"]
    dsec = read_sector_ref(big, 18, 1, work)
    t, s = dsec[3], dsec[4]                      # track/sector inicial del fichero
    set_ptr(mem, labels["out_ptr"], FILE_OUT)
    nblocks = 0
    guard = 0
    while t != 0 and guard < 100:
        guard += 1
        nblocks += 1
        sec = read_sector_ref(big, t, s, work)
        for i in range(256):
            mem[CHAIN_BUF + i] = sec[i]
        call_sub(mpu, mem, labels["file_block_process"])
        t = mem[labels["file_next_track"]]
        s = mem[labels["file_next_sector"]]
    end_ptr = mem[labels["out_ptr"]] | (mem[labels["out_ptr"] + 1] << 8)
    recon = bytes(mem[FILE_OUT + i] for i in range(end_ptr - FILE_OUT))
    ok = (recon == ref_data == orig)
    print(f"[lectura cadena {nblocks} bloques] reconstruido={len(recon)}B "
          f"ref={len(ref_data)}B identico={recon == ref_data} -> "
          f"{'OK' if ok else 'FALLO'}")
    r.append(ok)

    # --- inversa: un disco generado por NUESTRO DOS leido por c1541 (VICE) ---
    def spt(t):
        if t <= 17:
            return 21
        if t <= 24:
            return 19
        if t <= 30:
            return 18
        return 17

    def d64_offset(t, s):
        return (sum(spt(k) for k in range(1, t)) + s) * 256

    # nuestras rutinas generan BAM con identidad, directorio y bloques del fichero
    set_name(mem, "MYDISK")
    mem[0x0268] = ord("X")           # NAME_BUF2 = ID del disco
    mem[0x0268 + 1] = ord("Y")
    call_sub(mpu, mem, labels["disk_format_bam"])
    call_sub(mpu, mem, labels["disk_write_header"])
    our_bam_full = [mem[BAM_BUF + i] for i in range(256)]
    load_dir(mem, build_dir_sector([], link=(0, 0xFF)))
    fdata = bytes([0x01, 0x08]) + bytes((i * 53 + 7) & 0xFF for i in range(500))
    coords, blocks, dir_sector, nblk = save_file(mpu, mem, labels, "MYFILE", fdata)
    bam_final = [mem[BAM_BUF + i] for i in range(256)]   # con los bloques ocupados

    # ensamblar la imagen .d64 cruda (683 sectores) con nuestros sectores
    img = bytearray(174848)
    sectors = {(18, 0): bam_final, (18, 1): dir_sector}
    sectors.update(blocks)
    for (t, s), payload in sectors.items():
        off = d64_offset(t, s)
        img[off:off + 256] = bytes(payload)
    mine = os.path.join(work, "mine.d64")
    with open(mine, "wb") as f:
        f.write(img)

    # c1541 (VICE) lista y lee el fichero de NUESTRO disco. El nombre se pasa en
    # minusculas porque c1541 convierte el argumento de ASCII a PETSCII (mayusculas)
    dir_txt = c1541(["mine.d64", "-dir"], work).stdout
    outp = os.path.join(work, "out.prg")
    c1541(["mine.d64", "-read", "myfile", outp], work)
    read_back = b""
    if os.path.exists(outp):
        with open(outp, "rb") as f:
            read_back = f.read()
    dir_ok = ("MYFILE" in dir_txt.upper() and "MYDISK" in dir_txt.upper())
    data_ok = (read_back == fdata)
    print(f"[disco nuestro leido por VICE] dir_ve_fichero={dir_ok} "
          f"datos_identicos={data_ok} ({len(read_back)}/{len(fdata)}B) -> "
          f"{'OK' if (dir_ok and data_ok) else 'FALLO'}")
    if not (dir_ok and data_ok):
        print("   --- dir de c1541 ---")
        for ln in dir_txt.splitlines()[:6]:
            print("   " + ln)
    r.extend([dir_ok, data_ok])

    shutil.rmtree(work, ignore_errors=True)
    print()
    if all(r):
        print("RESULTADO: OK  disco de nuestro DOS leido por VICE; lectura/escritura validadas")
        sys.exit(0)
    print("RESULTADO: FALLO")
    sys.exit(1)


if __name__ == "__main__":
    main()
