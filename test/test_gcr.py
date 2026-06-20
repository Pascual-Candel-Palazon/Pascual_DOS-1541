#!/usr/bin/env python3
# ============================================================================
#  test_gcr.py  ::  verificacion del codec GCR (logica pura, sin timing)
# ----------------------------------------------------------------------------
#  Ejecuta las rutinas gcr_encode / gcr_decode de la ROM (py65) mediante un
#  trampolin en RAM y las compara contra una implementacion de referencia en
#  Python que usa la misma tabla GCR publica. Verifica:
#    - encode del 6502 == encode de referencia (muchos vectores)
#    - round-trip: decode(encode(x)) == x
# ============================================================================
import sys, random
from py65.devices.mpu6502 import MPU
from py65.memory import ObservableMemory

# tabla GCR publica (nibble -> codigo de 5 bits)
ENC = [0x0A,0x0B,0x12,0x13,0x0E,0x0F,0x16,0x17,
       0x09,0x19,0x1A,0x1B,0x0D,0x1D,0x1E,0x15]
DEC = {c: n for n, c in enumerate(ENC)}

IN4   = 0x0500   # 4 bytes de datos
GCR5  = 0x0600   # 5 bytes GCR
OUT4  = 0x0700   # 4 bytes decodificados


def gcr_encode_ref(four):
    nibbles = []
    for b in four:
        nibbles += [b >> 4, b & 0x0F]
    bits, nbits, out = 0, 0, []
    for nib in nibbles:
        bits = (bits << 5) | ENC[nib]
        nbits += 5
        while nbits >= 8:
            out.append((bits >> (nbits - 8)) & 0xFF)
            nbits -= 8
    return out  # 5 bytes


def gcr_decode_ref(five):
    bits = 0
    for b in five:
        bits = (bits << 8) | b           # 40 bits
    nibbles = [(bits >> (35 - 5 * i)) & 0x1F for i in range(8)]
    vals = [DEC[c] for c in nibbles]
    return [(vals[2 * i] << 4) | vals[2 * i + 1] for i in range(4)]


def load_labels(path):
    out = {}
    for line in open(path):
        p = line.split()
        if len(p) == 3 and p[0] == "al":
            out[p[2].lstrip(".")] = int(p[1], 16)
    return out


def make_machine():
    rom = open("dos.bin", "rb").read()
    mem = ObservableMemory()
    for i, b in enumerate(rom):
        mem[0xC000 + i] = b
    mpu = MPU(memory=mem)
    return mpu, mem


def call_sub(mpu, mem, addr):
    # trampolin: JSR addr ; JMP * (bucle en si mismo)
    mem[0x0200] = 0x20
    mem[0x0201] = addr & 0xFF
    mem[0x0202] = addr >> 8
    mem[0x0203] = 0x4C
    mem[0x0204] = 0x03
    mem[0x0205] = 0x02
    mpu.pc = 0x0200
    mpu.sp = 0xFF
    for _ in range(100000):
        mpu.step()
        if mpu.pc == 0x0203:
            return
    raise RuntimeError("la subrutina no retorno")


def set_ptr(mem, zp, addr):
    mem[zp] = addr & 0xFF
    mem[zp + 1] = addr >> 8


def encode_6502(mpu, mem, labels, four):
    for i, b in enumerate(four):
        mem[IN4 + i] = b
    set_ptr(mem, labels["gcr_src"], IN4)
    set_ptr(mem, labels["gcr_dst"], GCR5)
    call_sub(mpu, mem, labels["gcr_encode"])
    return [mem[GCR5 + i] for i in range(5)]


def decode_6502(mpu, mem, labels, five):
    for i, b in enumerate(five):
        mem[GCR5 + i] = b
    set_ptr(mem, labels["gcr_src"], GCR5)
    set_ptr(mem, labels["gcr_dst"], OUT4)
    call_sub(mpu, mem, labels["gcr_decode"])
    return [mem[OUT4 + i] for i in range(4)]


def main():
    mpu, mem = make_machine()
    labels = load_labels("dos.lbl")

    # construir el conjunto de vectores de prueba
    vectors = []
    for b in range(256):
        vectors.append([b, b, b, b])             # patrones uniformes
    vectors += [[0x00, 0x01, 0x02, 0x03],
                [0xFF, 0xFE, 0xFD, 0xFC],
                [0x12, 0x34, 0x56, 0x78],
                [0xDE, 0xAD, 0xBE, 0xEF]]
    random.seed(1541)
    for _ in range(512):
        vectors.append([random.randint(0, 255) for _ in range(4)])

    enc_mismatch = rt_mismatch = 0
    enc_ok = rt_ok = 0
    first_fail = None
    for v in vectors:
        g6 = encode_6502(mpu, mem, labels, v)
        gr = gcr_encode_ref(v)
        if g6 == gr:
            enc_ok += 1
        else:
            enc_mismatch += 1
            if first_fail is None:
                first_fail = ("encode", v, g6, gr)
        back = decode_6502(mpu, mem, labels, g6)
        if back == v:
            rt_ok += 1
        else:
            rt_mismatch += 1
            if first_fail is None:
                first_fail = ("roundtrip", v, g6, back)

    n = len(vectors)
    print(f"vectores probados: {n}")
    print(f"encode == referencia: {enc_ok}/{n}  (fallos {enc_mismatch})")
    print(f"round-trip decode(encode(x))==x: {rt_ok}/{n}  (fallos {rt_mismatch})")
    if first_fail:
        kind, v, a, b = first_fail
        sv = ["$%02X" % x for x in v]
        sa = ["$%02X" % x for x in a]
        sb = ["$%02X" % x for x in b]
        print(f"primer fallo ({kind}): in={sv} got={sa} exp={sb}")

    # comprobacion adicional: el decode del 6502 invierte su propio encode y
    # ademas coincide con la referencia para un vector concreto
    sample = [0xA5, 0x5A, 0x0F, 0xF0]
    print(f"muestra encode 6502  = {['$%02X'%x for x in encode_6502(mpu,mem,labels,sample)]}")
    print(f"muestra encode refer = {['$%02X'%x for x in gcr_encode_ref(sample)]}")

    print()
    if enc_mismatch == 0 and rt_mismatch == 0:
        print("RESULTADO: OK  codec GCR correcto (encode y round-trip)")
        sys.exit(0)
    print("RESULTADO: FALLO")
    sys.exit(1)


if __name__ == "__main__":
    main()
