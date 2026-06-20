#!/usr/bin/env python3
# ============================================================================
#  test_disk.py  ::  controlador de disco, capa logica (sin timing)
# ----------------------------------------------------------------------------
#  Verifica la localizacion de SYNC y la lectura/validacion del bloque de
#  cabecera del sector. La pista se modela como bytes (SYNC = bytes $FF); el
#  alineamiento de bits del SYNC real pertenece a la capa de IRQ y se valida en
#  VICE. La codificacion GCR usa la referencia ya verificada en test_gcr.py.
# ============================================================================
import sys
from test_gcr import (gcr_encode_ref, load_labels, make_machine,
                      call_sub, set_ptr)

# TRACK_BUF es el flujo GCR de entrada de prueba (ficcion del harness): en
# hardware la pista no se almacena, se decodifica al vuelo desde la VIA2. Se
# situa fuera de la RAM real de la 1541 para no chocar con sus buffers.
TRACK_BUF = 0x1000
DATA_DEC_BUF = 0x0400   # sector decodificado, en RAM real de la 1541


def build_header_gcr(track, sector, id1, id2, mark=0x08, csum=None):
    if csum is None:
        csum = sector ^ track ^ id2 ^ id1
    data = [mark, csum, sector, track, id2, id1, 0x0F, 0x0F]
    return gcr_encode_ref(data[0:4]) + gcr_encode_ref(data[4:8])  # 10 bytes


def build_data_gcr(data256, mark=0x07, csum=None):
    if csum is None:
        c = 0
        for b in data256:
            c ^= b
        csum = c
    block = [mark] + list(data256) + [csum, 0x00, 0x00]   # 260 bytes
    gcr = []
    for i in range(0, 260, 4):
        gcr += gcr_encode_ref(block[i:i + 4])
    return gcr   # 325 bytes


def run_data(name, data256, mark=0x07, bad_csum=False):
    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")
    csum = None
    if bad_csum:
        c = 0
        for b in data256:
            c ^= b
        csum = c ^ 0xFF
    gcr = build_data_gcr(data256, mark=mark, csum=csum)
    track = [0xFF] * 6 + gcr + [0x55] * 8
    for i, b in enumerate(track):
        mem[TRACK_BUF + i] = b
    set_ptr(mem, labels["gcr_src"], TRACK_BUF)
    call_sub(mpu, mem, labels["disk_find_sync"])
    call_sub(mpu, mem, labels["disk_read_data"])
    derr = mem[labels["data_error"]]
    got = [mem[DATA_DEC_BUF + 1 + i] for i in range(256)]

    valid = (mark == 0x07 and not bad_csum)
    ok = ((derr == 0x00) == valid)
    if valid:
        ok &= (got == list(data256))
    print(f"[{name}] data_err=${derr:02X} datos_ok={got==list(data256)} -> "
          f"{'OK' if ok else 'FALLO'}")
    return ok


def run(name, track_bytes, expect):
    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")
    for i, b in enumerate(track_bytes):
        mem[TRACK_BUF + i] = b
    set_ptr(mem, labels["gcr_src"], TRACK_BUF)

    call_sub(mpu, mem, labels["disk_find_sync"])
    sync_err = mem[labels["sync_error"]]
    src_after = mem[labels["gcr_src"]] | (mem[labels["gcr_src"] + 1] << 8)

    if sync_err == 0 and not expect.get("sync_fail"):
        call_sub(mpu, mem, labels["disk_read_header"])
    hdr_err = mem[labels["hdr_error"]]
    trk = mem[labels["hdr_track"]]
    sec = mem[labels["hdr_sector"]]

    ok = True
    if "sync_fail" in expect:
        ok &= (sync_err == 0xFF) == expect["sync_fail"]
    if "sync_off" in expect:
        ok &= (src_after - TRACK_BUF) == expect["sync_off"]
    if "hdr_ok" in expect:
        ok &= (hdr_err == 0x00) == expect["hdr_ok"]
    if "track" in expect:
        ok &= trk == expect["track"]
    if "sector" in expect:
        ok &= sec == expect["sector"]

    print(f"[{name}] sync_err=${sync_err:02X} sync_off={src_after-TRACK_BUF} "
          f"hdr_err=${hdr_err:02X} track={trk} sector={sec} -> "
          f"{'OK' if ok else 'FALLO'}")
    return ok


def build_sector(track, sector, data256, id1=ord('A'), id2=ord('B')):
    return ([0xFF] * 6 + build_header_gcr(track, sector, id1, id2) + [0x55] * 8 +
            [0xFF] * 6 + build_data_gcr(data256) + [0x55] * 8)


def build_track(sector_list):
    t = []
    for (tr, se, d) in sector_list:
        t += build_sector(tr, se, d)
    return t


def run_find_sector(name, sector_list, want_track, want_sector, expect_data):
    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")
    track = build_track(sector_list)
    for i, b in enumerate(track):
        mem[TRACK_BUF + i] = b
    set_ptr(mem, labels["gcr_src"], TRACK_BUF)
    mem[labels["want_track"]] = want_track
    mem[labels["want_sector"]] = want_sector
    call_sub(mpu, mem, labels["disk_find_sector"])
    ferr = mem[labels["fsec_error"]]
    got = [mem[DATA_DEC_BUF + 1 + i] for i in range(256)]

    if expect_data is None:
        ok = (ferr == 0xFF)
        datos_ok = "-"
    else:
        ok = (ferr == 0x00) and (got == list(expect_data))
        datos_ok = (got == list(expect_data))
    print(f"[{name}] fsec_err=${ferr:02X} datos_ok={datos_ok} -> "
          f"{'OK' if ok else 'FALLO'}")
    return ok


def run_geometry():
    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")
    expected = {1: 21, 17: 21, 18: 19, 24: 19, 25: 18, 30: 18, 31: 17, 35: 17}
    ok = True
    detail = []
    for track, sec in expected.items():
        mem[0x0200] = 0xA9; mem[0x0201] = track          # LDA #track
        mem[0x0202] = 0x20                               # JSR disk_sectors_per_track
        addr = labels["disk_sectors_per_track"]
        mem[0x0203] = addr & 0xFF; mem[0x0204] = addr >> 8
        mem[0x0205] = 0x8D; mem[0x0206] = 0x10; mem[0x0207] = 0x02  # STA $0210
        mem[0x0208] = 0x4C; mem[0x0209] = 0x08; mem[0x020A] = 0x02  # JMP *
        mpu.pc = 0x0200; mpu.sp = 0xFF
        for _ in range(2000):
            mpu.step()
            if mpu.pc == 0x0208:
                break
        got = mem[0x0210]
        ok &= (got == sec)
        detail.append(f"t{track}={got}")
    print(f"[geometria] {' '.join(detail)} -> {'OK' if ok else 'FALLO'}")
    return ok


GCR_OUT = 0x1400   # buffer GCR de salida de escritura (ficcion del harness)


def run_build_data(name, data256):
    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")
    # poner los 256 bytes en DATA_DEC_BUF+1
    for i, b in enumerate(data256):
        mem[DATA_DEC_BUF + 1 + i] = b
    set_ptr(mem, labels["gcr_dst"], GCR_OUT)
    call_sub(mpu, mem, labels["disk_build_data"])
    got = [mem[GCR_OUT + i] for i in range(325)]
    ref = build_data_gcr(data256)
    enc_ok = (got == ref)

    # round-trip: releer el GCR producido y recuperar los 256 bytes
    set_ptr(mem, labels["gcr_src"], GCR_OUT)
    call_sub(mpu, mem, labels["disk_read_data"])
    derr = mem[labels["data_error"]]
    back = [mem[DATA_DEC_BUF + 1 + i] for i in range(256)]
    rt_ok = (derr == 0x00 and back == list(data256))

    ok = enc_ok and rt_ok
    print(f"[{name}] encode==ref={enc_ok} roundtrip={rt_ok} -> "
          f"{'OK' if ok else 'FALLO'}")
    return ok


def run_build_header(name, track, sector, id1, id2):
    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")
    mem[labels["want_track"]] = track
    mem[labels["want_sector"]] = sector
    mem[labels["want_id1"]] = id1
    mem[labels["want_id2"]] = id2
    set_ptr(mem, labels["gcr_dst"], GCR_OUT)
    call_sub(mpu, mem, labels["disk_build_header"])
    got = [mem[GCR_OUT + i] for i in range(10)]
    ref = build_header_gcr(track, sector, id1, id2)
    enc_ok = (got == ref)

    # round-trip: releer la cabecera producida
    set_ptr(mem, labels["gcr_src"], GCR_OUT)
    call_sub(mpu, mem, labels["disk_read_header"])
    herr = mem[labels["hdr_error"]]
    trk = mem[labels["hdr_track"]]
    sec = mem[labels["hdr_sector"]]
    rt_ok = (herr == 0x00 and trk == track and sec == sector)

    ok = enc_ok and rt_ok
    print(f"[{name}] encode==ref={enc_ok} roundtrip(t{trk}s{sec})={rt_ok} -> "
          f"{'OK' if ok else 'FALLO'}")
    return ok


def main():
    r = []

    # cabecera valida: track 18, sector 0, ID 'AB', SYNC de 6 bytes
    hdr = build_header_gcr(18, 0, ord('A'), ord('B'))
    r.append(run("cabecera valida t18 s0",
        [0xFF]*6 + hdr + [0x55]*8,
        {"sync_fail": False, "sync_off": 6, "hdr_ok": True,
         "track": 18, "sector": 0}))

    # otra cabecera: track 1, sector 20
    hdr = build_header_gcr(1, 20, ord('Z'), ord('9'))
    r.append(run("cabecera valida t1 s20",
        [0xFF]*8 + hdr + [0x55]*8,
        {"hdr_ok": True, "track": 1, "sector": 20, "sync_off": 8}))

    # cabecera con checksum corrupto: GCR valido pero el checksum no cuadra
    good = 35 ^ 16 ^ ord('Y') ^ ord('X')
    hdr = build_header_gcr(35, 16, ord('X'), ord('Y'), csum=good ^ 0xFF)
    r.append(run("checksum corrupto",
        [0xFF]*6 + hdr + [0x55]*8,
        {"hdr_ok": False}))

    # cabecera con marca incorrecta ($07 en vez de $08)
    hdr = build_header_gcr(10, 5, ord('A'), ord('A'), mark=0x07)
    r.append(run("marca incorrecta",
        [0xFF]*6 + hdr + [0x55]*8,
        {"hdr_ok": False}))

    # sin SYNC suficiente: solo 3 bytes $FF
    hdr = build_header_gcr(18, 0, ord('A'), ord('B'))
    r.append(run("SYNC insuficiente",
        [0x55]*4 + [0xFF]*3 + [0x55]*4 + [0x55]*200,
        {"sync_fail": True}))

    # --- bloque de datos (2b-2) ---
    # patron incremental 0..255
    r.append(run_data("datos incrementales", [i & 0xFF for i in range(256)]))
    # patron fijo
    r.append(run_data("datos 0xA5", [0xA5] * 256))
    # checksum corrupto
    r.append(run_data("datos checksum corrupto", [i & 0xFF for i in range(256)],
                      bad_csum=True))
    # marca incorrecta
    r.append(run_data("datos marca incorrecta", [0x00] * 256, mark=0x08))

    # --- localizar un sector en una pista con varios sectores (2c) ---
    dataA = [0x11] * 256
    dataB = [(i ^ 0x5A) & 0xFF for i in range(256)]
    dataC = [0xCC] * 256
    sectors = [(18, 0, dataA), (18, 1, dataB), (18, 2, dataC)]
    r.append(run_find_sector("buscar sector 1 de 3", sectors, 18, 1, dataB))
    r.append(run_find_sector("buscar sector 0 (primero)", sectors, 18, 0, dataA))
    r.append(run_find_sector("buscar sector 2 (ultimo)", sectors, 18, 2, dataC))
    r.append(run_find_sector("sector ausente", sectors, 18, 5, None))
    r.append(run_find_sector("track erroneo", sectors, 19, 1, None))

    # --- geometria por zonas ---
    r.append(run_geometry())

    # --- escritura de sector: codificacion y round-trip (2e) ---
    r.append(run_build_data("escribir datos incrementales",
                            [i & 0xFF for i in range(256)]))
    r.append(run_build_data("escribir datos 0x3C", [0x3C] * 256))
    r.append(run_build_header("escribir cabecera t18 s0", 18, 0,
                              ord('A'), ord('B')))
    r.append(run_build_header("escribir cabecera t35 s16", 35, 16,
                              ord('Z'), ord('9')))

    print()
    if all(r):
        print("RESULTADO: OK  lectura, busqueda, geometria y escritura de sector")
        sys.exit(0)
    print("RESULTADO: FALLO")
    sys.exit(1)


if __name__ == "__main__":
    main()
