#!/usr/bin/env python3
# ============================================================================
#  test_iec.py  ::  co-simulacion del bus serie IEC (comandos, datos, EOI)
# ----------------------------------------------------------------------------
#  Ejecuta la ROM dos1541 (py65) como dispositivo y un controlador C64 simulado
#  como host, compartiendo un modelo de las lineas del bus (wired-AND).
#
#  Verifica la LOGICA del protocolo del lado listener: parseo de comandos,
#  transferencia de byte y deteccion de EOI. El handshake se modela por
#  niveles; el EOI se modela por el ORDEN relativo de los eventos (el talker en
#  modo EOI no toca CLK y espera el pulso de reconocimiento del listener), no
#  por tiempo absoluto. Polaridad y timing fisicos se validan en VICE.
# ============================================================================
import sys
from py65.devices.mpu6502 import MPU
from py65.memory import ObservableMemory

DATA_IN, DATA_OUT = 0x01, 0x02
CLK_IN,  CLK_OUT  = 0x04, 0x08
ATNA, ATN_IN      = 0x10, 0x80
OUT_BITS = DATA_OUT | CLK_OUT | ATNA

LISTEN, TALK, UNLISTEN, UNTALK = 0x20, 0x40, 0x3F, 0x5F
SECONDARY = 0x60
DATA_BUF = 0x0300
EOI_TIMEOUT_TICKS = 60   # timeout del listener simulado para detectar EOI


class Bus:
    def __init__(self):
        self.dev_data = self.dev_clk = self.via1_out = 0
        self.ctrl_atn = self.ctrl_clk = self.ctrl_data = 0

    def read_pb(self):
        b = self.via1_out & OUT_BITS
        if self.dev_data or self.ctrl_data: b |= DATA_IN
        if self.dev_clk or self.ctrl_clk:   b |= CLK_IN
        if self.ctrl_atn:                   b |= ATN_IN
        return b

    def write_pb(self, value):
        self.via1_out = value
        self.dev_data = 1 if (value & DATA_OUT) else 0
        self.dev_clk  = 1 if (value & CLK_OUT)  else 0


def load_labels(path):
    out = {}
    for line in open(path):
        p = line.split()
        if len(p) == 3 and p[0] == "al":
            out[p[2].lstrip(".")] = int(p[1], 16)
    return out


class Controller:
    """Host C64 simulado. Ejecuta un script de operaciones de alto nivel."""
    DWELL = 25

    def __init__(self, bus, script, skip_presence=False):
        self.bus = bus
        self.script = script
        self.skip_presence = skip_presence
        self.gen = self._run()
        self.rx = []          # bytes recibidos cuando el host actua de listener
        self.rx_eoi = False   # el ultimo byte recibido llevaba EOI
        self.trace = []       # (ticks_esperando_clk, valor, eoi) por byte

    def tick(self): next(self.gen)

    def _dwell(self, n=None):
        for _ in range(n or self.DWELL):
            yield

    def _wait(self, cond, timeout=30000):
        t = 0
        while not cond():
            yield
            t += 1
            if t > timeout:
                raise TimeoutError("deadlock en una linea del bus")

    def _recv_byte(self):
        """Host actuando de listener: recibe un byte del talker (la 1541)."""
        b = self.bus
        yield from self._wait(lambda: not b.dev_clk)   # talker listo
        b.ctrl_data = 0                                # listener listo
        # esperar CLK asserted con timeout (deteccion de EOI)
        eoi, t = False, 0
        while not b.dev_clk:
            yield
            t += 1
            if t > EOI_TIMEOUT_TICKS:
                eoi = True
                break
        if eoi:
            b.ctrl_data = 1                            # pulso de reconocimiento
            yield from self._dwell(20)
            b.ctrl_data = 0
            yield from self._wait(lambda: b.dev_clk)   # primer bit del ultimo byte
        value = 0
        for i in range(8):
            yield from self._wait(lambda: not b.dev_clk)   # CLK liberado: dato valido
            value |= (0 if b.dev_data else 1) << i         # asserted=0, liberada=1
            yield from self._wait(lambda: b.dev_clk)        # CLK asertado: siguiente
        b.ctrl_data = 1                                # frame ACK
        yield from self._wait(lambda: b.dev_clk)       # talker reconoce (reposo)
        self.rx.append(value)
        self.rx_eoi = eoi
        self.trace.append((t, value, eoi))

    def _send_byte(self, value, eoi=False):
        b = self.bus
        b.ctrl_clk = 0                                  # talker listo (CLK liberado)
        yield from self._wait(lambda: not b.dev_data)   # listener listo (libera DATA)
        if eoi:
            # no asertir CLK: el listener agota su timeout y pulsa DATA
            yield from self._wait(lambda: b.dev_data)   # pulso EOI ack
            yield from self._wait(lambda: not b.dev_data)
        b.ctrl_clk = 1                                  # non-EOI start: asertar CLK
        yield from self._dwell()
        for i in range(8):
            bit = (value >> i) & 1
            b.ctrl_data = 0 if bit else 1               # poner el bit en DATA
            yield from self._dwell(5)
            b.ctrl_clk = 0                              # liberar CLK: dato valido (lee aqui)
            yield from self._dwell()
            b.ctrl_clk = 1                              # asertar CLK: prepara el siguiente
            yield from self._dwell()
        b.ctrl_data = 0
        yield from self._wait(lambda: b.dev_data)       # frame ACK
        b.ctrl_clk = 1                                  # reposo
        yield from self._dwell()

    def _run(self):
        b = self.bus
        b.ctrl_atn = 1; b.ctrl_clk = 1; b.ctrl_data = 0
        if not self.skip_presence:
            yield from self._wait(lambda: b.dev_data)       # presencia
        for op in self.script:
            kind = op[0]
            if kind == "cmd":
                yield from self._send_byte(op[1])
            elif kind == "data":
                yield from self._send_byte(op[1], op[2])
            elif kind == "unatn":
                b.ctrl_atn = 0
                yield from self._dwell()
            elif kind == "reatn":
                b.ctrl_atn = 1
                yield from self._dwell()
            elif kind == "turnaround":
                # el host pasa de talker a listener tras liberar ATN
                b.ctrl_atn = 0
                yield from self._wait(lambda: b.dev_clk)  # la 1541 toma CLK
                b.ctrl_clk = 0
                b.ctrl_data = 1                           # host: listener listo
                yield from self._dwell()
            elif kind == "as_listener":
                # el host se coloca como listener sin turnaround previo (para
                # probar iec_send_buffer de forma aislada: el talker ya esta activo)
                b.ctrl_atn = 0
                b.ctrl_clk = 0
                b.ctrl_data = 1
                yield from self._dwell()
            elif kind == "recv_eoi":
                while True:
                    yield from self._recv_byte()
                    if self.rx_eoi:
                        break
        b.ctrl_atn = 0
        yield from self._dwell()


def run_case(name, script, expect, entry=None, preload=None):
    rom = open("dos.bin", "rb").read()
    labels = load_labels("dos.lbl")
    bus = Bus()
    mem = ObservableMemory()
    for i, byte in enumerate(rom):
        mem[0xC000 + i] = byte
    mem.subscribe_to_read([0x1800], lambda a: bus.read_pb())
    mem.subscribe_to_write([0x1800], lambda a, v: bus.write_pb(v))

    if preload:
        for addr, vals in preload.items():
            a = labels[addr] if isinstance(addr, str) else addr
            for i, v in enumerate(vals):
                mem[a + i] = v

    mpu = MPU(memory=mem)
    if entry is not None:
        mpu.pc = labels[entry] if isinstance(entry, str) else entry
        mpu.sp = 0xFF
    else:
        mpu.pc = mem[0xFFFC] | (mem[0xFFFD] << 8)
    ctrl = Controller(bus, script, skip_presence=(entry is not None))

    steps, MAX, done = 0, 600_000, False
    while steps < MAX:
        mpu.step()
        steps += 1
        try:
            ctrl.tick()
        except StopIteration:
            done = True
            break
        except TimeoutError as e:
            pc = mpu.pc
            near = max((a, n) for n, a in labels.items()
                       if isinstance(a, int) and a <= pc and a >= 0xC000)
            print(f"[{name}] FALLO: {e}")
            print(f"   1541 PC=${pc:04X} (~{near[1]}+${pc-near[0]:X})  "
                  f"dev_data={bus.dev_data} dev_clk={bus.dev_clk}  "
                  f"ctrl_atn={bus.ctrl_atn} ctrl_clk={bus.ctrl_clk} "
                  f"ctrl_data={bus.ctrl_data}")
            return False

    state = mem[labels["iec_state"]]
    listening = bool(state & 0x01)
    talking   = bool(state & 0x02)
    sa        = mem[labels["iec_sa"]]
    eoi       = mem[labels["iec_data_eoi"]]
    didx      = mem[labels["data_idx"]]
    buf       = [mem[DATA_BUF + i] for i in range(didx)]

    ok = True
    if "listening" in expect: ok &= listening == expect["listening"]
    if "talking" in expect:   ok &= talking == expect["talking"]
    if "sa" in expect:        ok &= sa == expect["sa"]
    if "eoi" in expect:       ok &= (eoi == (0xFF if expect["eoi"] else 0x00))
    if "data_buf" in expect:  ok &= buf == expect["data_buf"]
    if "rx" in expect:        ok &= ctrl.rx == expect["rx"]
    if "rx_eoi" in expect:    ok &= ctrl.rx_eoi == expect["rx_eoi"]

    extra = ""
    if "data_buf" in expect:
        extra = f" buf={['$%02X'%x for x in buf]}"
    if "rx" in expect:
        extra = f" rx={['$%02X'%x for x in ctrl.rx]} rx_eoi={ctrl.rx_eoi}"
        extra += f"  trace={[(t,'$%02X'%v,e) for t,v,e in ctrl.trace]}"
    print(f"[{name}] pasos={steps:>6} done={done} listen={listening} "
          f"talk={talking} sa={sa} eoi=${eoi:02X}{extra} -> "
          f"{'OK' if ok else 'FALLO'}")
    return bool(ok)


def main():
    r = []
    # --- comandos (hito 1a) ---
    r.append(run_case("LISTEN dev8 + canal 2",
        [("cmd", LISTEN | 8), ("cmd", SECONDARY | 2), ("unatn",)],
        {"listening": True, "talking": False, "sa": 2}))
    r.append(run_case("LISTEN dev9 (ajeno)",
        [("cmd", LISTEN | 9), ("cmd", SECONDARY | 2), ("unatn",)],
        {"listening": False, "talking": False}))
    r.append(run_case("LISTEN dev8 + UNLISTEN",
        [("cmd", LISTEN | 8), ("cmd", UNLISTEN), ("unatn",)],
        {"listening": False}))
    r.append(run_case("TALK dev8",
        [("cmd", TALK | 8), ("unatn",)],
        {"listening": False, "talking": True}))

    # --- datos con EOI (hito 1b) ---
    r.append(run_case("datos 3 bytes, EOI en el ultimo",
        [("cmd", LISTEN | 8), ("cmd", SECONDARY | 2), ("unatn",),
         ("data", 0x41, False), ("data", 0x42, False), ("data", 0x43, True),
         ("reatn",), ("cmd", UNLISTEN), ("unatn",)],
        {"data_buf": [0x41, 0x42, 0x43], "eoi": True, "listening": False}))

    # --- datos sin EOI: no debe dispararse EOI falso, corte por ATN ---
    r.append(run_case("datos 3 bytes, sin EOI (corte por ATN)",
        [("cmd", LISTEN | 8), ("cmd", SECONDARY | 2), ("unatn",),
         ("data", 0x53, False), ("data", 0x41, False), ("data", 0x4C, False),
         ("reatn",), ("cmd", UNLISTEN), ("unatn",)],
        {"data_buf": [0x53, 0x41, 0x4C], "eoi": False, "listening": False}))

    # --- talker: envio de un buffer de longitud variable con EOI ---
    # Verifica iec_send_buffer (el mecanismo de transmision generalizado que usa
    # iec_talk): transmite tx_len bytes desde (tx_ptr) con EOI en el ultimo. Se
    # prueba de forma aislada precargando un buffer, con el host ya como listener.
    # El turnaround y el cierre del canal (UNTALK) estan verificados en VICE: un
    # LOAD"$",8 completo recibe $28 $F0 $24 $3F $48 $60 $5F $28 $E0 $3F y el C64
    # retorna a READY.
    TXTEST = 0x0700
    r.append(run_case("iec_talk_send: turnaround + 3 bytes con EOI",
        [("turnaround",), ("recv_eoi",)],
        {"rx": [0x11, 0x22, 0x33], "rx_eoi": True},
        entry="iec_talk_send",
        preload={TXTEST: [0x11, 0x22, 0x33],
                 "tx_ptr": [TXTEST & 0xFF, (TXTEST >> 8) & 0xFF],
                 "tx_len": [3, 0],
                 "tx_last": [0xFF]}))

    print()
    if all(r):
        print("RESULTADO: OK  listener IEC con comandos, datos y EOI")
        sys.exit(0)
    print("RESULTADO: FALLO")
    sys.exit(1)


if __name__ == "__main__":
    main()
