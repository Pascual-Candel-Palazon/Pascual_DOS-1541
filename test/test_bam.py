#!/usr/bin/env python3
# ============================================================================
#  test_bam.py  ::  mapa de bloques disponibles (BAM), logica pura
# ----------------------------------------------------------------------------
#  Verifica las operaciones sobre el BAM (sector pista 18/0, 256 bytes ya
#  decodificados): libres por pista, consulta de un bloque, asignar, liberar y
#  total de bloques libres. Formato publico del .d64.
# ============================================================================
import sys
from test_gcr import load_labels, make_machine, call_sub

BAM_BUF = 0x0600


def sectors_per_track(t):
    if t <= 17:
        return 21
    if t <= 24:
        return 19
    if t <= 30:
        return 18
    return 17


def build_bam(occupied):
    """occupied: dict track -> lista de sectores ocupados."""
    bam = [0] * 256
    bam[0], bam[1] = 18, 1          # link al primer sector de directorio
    bam[2], bam[3] = 0x41, 0x00     # 'A', formato
    for t in range(1, 36):
        n = sectors_per_track(t)
        e = 4 + (t - 1) * 4
        occ = set(occupied.get(t, []))
        bits = [0, 0, 0]
        free = 0
        for s in range(n):
            if s not in occ:
                bits[s // 8] |= (1 << (s % 8))
                free += 1
        bam[e] = free
        bam[e + 1], bam[e + 2], bam[e + 3] = bits
    # nombre/id (no afecta a estas pruebas)
    return bam


def load_bam(mem, bam):
    for i, b in enumerate(bam):
        mem[BAM_BUF + i] = b


def main():
    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")
    r = []

    # ocupados: pista 1 sectores {0,1,5}; pista 17 sector {20}; pista 35 sectores {0..16} todos
    occupied = {1: [0, 1, 5], 17: [20], 35: list(range(17))}
    bam = build_bam(occupied)
    load_bam(mem, bam)

    def free_on(track):
        mem[labels["bam_track"]] = track
        call_sub(mpu, mem, labels["bam_free_on_track"])
        return mpu.a

    def is_free(track, sector):
        mem[labels["bam_track"]] = track
        mem[labels["bam_sector"]] = sector
        call_sub(mpu, mem, labels["bam_is_free"])
        return mem[labels["bam_result"]] == 0xFF

    def total_free():
        call_sub(mpu, mem, labels["bam_total_free"])
        return mem[labels["bam_total_lo"]] | (mem[labels["bam_total_hi"]] << 8)

    # libres por pista
    ok = (free_on(1) == 21 - 3 and free_on(2) == 21 and
          free_on(17) == 20 and free_on(35) == 0)
    print(f"[libres por pista] t1={free_on(1)} t2={free_on(2)} "
          f"t17={free_on(17)} t35={free_on(35)} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # consulta de bloques concretos
    ok = (not is_free(1, 0) and not is_free(1, 5) and is_free(1, 2) and
          is_free(2, 0) and not is_free(17, 20) and is_free(17, 19))
    print(f"[consulta bloques] (1,0)libre={is_free(1,0)} (1,2)libre={is_free(1,2)} "
          f"(17,20)libre={is_free(17,20)} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # total: suma de libres en 1..35 excepto pista 18
    expected_total = 0
    for t in range(1, 36):
        if t == 18:
            continue
        n = sectors_per_track(t)
        expected_total += n - len(set(occupied.get(t, [])))
    tot = total_free()
    ok = (tot == expected_total)
    print(f"[total libres] {tot} (esperado {expected_total}) -> "
          f"{'OK' if ok else 'FALLO'}")
    r.append(ok)

    # asignar un bloque libre: (2,3) pasa a ocupado y baja el contador
    before = free_on(2)
    mem[labels["bam_track"]] = 2
    mem[labels["bam_sector"]] = 3
    call_sub(mpu, mem, labels["bam_alloc"])
    after = free_on(2)
    ok = (is_free(2, 3) is False and after == before - 1)
    print(f"[alloc (2,3)] libre_antes? si  ocupado_despues={not is_free(2,3)} "
          f"contador {before}->{after} -> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    # alloc idempotente: reasignar (2,3) no vuelve a decrementar
    again = free_on(2)
    mem[labels["bam_track"]] = 2
    mem[labels["bam_sector"]] = 3
    call_sub(mpu, mem, labels["bam_alloc"])
    ok = (free_on(2) == again)
    print(f"[alloc idempotente] contador {again}->{free_on(2)} -> "
          f"{'OK' if ok else 'FALLO'}")
    r.append(ok)

    # liberar (1,0): pasa a libre y sube el contador
    before = free_on(1)
    mem[labels["bam_track"]] = 1
    mem[labels["bam_sector"]] = 0
    call_sub(mpu, mem, labels["bam_free_block"])
    after = free_on(1)
    ok = (is_free(1, 0) and after == before + 1)
    print(f"[free (1,0)] libre_despues={is_free(1,0)} contador {before}->{after} "
          f"-> {'OK' if ok else 'FALLO'}")
    r.append(ok)

    print()
    if all(r):
        print("RESULTADO: OK  operaciones del BAM")
        sys.exit(0)
    print("RESULTADO: FALLO")
    sys.exit(1)


if __name__ == "__main__":
    main()
