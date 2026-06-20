#!/usr/bin/env python3
# Cliente minimo del monitor binario de VICE. Se usa como andamiaje para verificar
# la 1541 en x64sc: lee/escribe RAM y controla la ejecucion SIN tocar ni desensamblar
# ninguna ROM (solo observa RAM, comportamiento de caja negra, Nivel B).
import socket
import struct
import subprocess
import time

STX = 0x02
API = 0x02
CMD_MEM_GET = 0x01
CMD_MEM_SET = 0x02
CMD_REGISTERS_GET = 0x31
CMD_RESET = 0xcc
CMD_EXIT = 0xaa
CMD_QUIT = 0xbb
CMD_PING = 0x81


class ViceMonitor:
    def __init__(self, port=6502):
        self.port = port
        self.sock = None
        self.req = 1

    def connect(self, timeout=20):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                s = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                self.sock = s
                return True
            except OSError as e:
                last = e
                time.sleep(0.3)
        raise RuntimeError(f"no se pudo conectar al monitor binario: {last}")

    def _send(self, cmd_type, body=b""):
        rid = self.req
        self.req += 1
        header = struct.pack("<BBIIB", STX, API, len(body), rid, cmd_type)
        self.sock.sendall(header + body)
        return rid

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise RuntimeError("conexion cerrada por VICE")
            buf += chunk
        return buf

    def _recv_response(self, want_rid):
        # Lee respuestas hasta encontrar la del request id pedido (descarta eventos).
        while True:
            hdr = self._recv_exact(12)
            stx, api, blen, rtype, err, rid = struct.unpack("<BBIBBI", hdr)
            body = self._recv_exact(blen) if blen else b""
            if rid == want_rid:
                return rtype, err, body
            # si no coincide, es un evento asincrono: seguir leyendo

    def mem_get(self, start, end, memspace=0, bank=0, side_effects=0):
        body = struct.pack("<BHHBH", side_effects, start, end, memspace, bank)
        rid = self._send(CMD_MEM_GET, body)
        rtype, err, rbody = self._recv_response(rid)
        if err != 0:
            raise RuntimeError(f"mem_get error {err}")
        n = struct.unpack("<H", rbody[:2])[0]
        return rbody[2:2 + n]

    def mem_set(self, start, data, memspace=0, bank=0, side_effects=0):
        end = start + len(data) - 1
        body = struct.pack("<BHHBH", side_effects, start, end, memspace, bank) + bytes(data)
        rid = self._send(CMD_MEM_SET, body)
        rtype, err, rbody = self._recv_response(rid)
        if err != 0:
            raise RuntimeError(f"mem_set error {err}")

    def reset(self, mode=1):
        rid = self._send(CMD_RESET, bytes([mode]))
        self._recv_response(rid)

    def resume(self):
        # reanuda la emulacion (por si una conexion la dejo detenida)
        try:
            self._send(CMD_EXIT)
        except Exception:
            pass

    def registers_get(self, memspace=0):
        # devuelve {reg_id: value}; en el 6502 de VICE el id 3 suele ser PC
        rid = self._send(CMD_REGISTERS_GET, bytes([memspace]))
        rtype, err, body = self._recv_response(rid)
        n = struct.unpack("<H", body[:2])[0]
        off = 2
        out = {}
        for _ in range(n):
            size = body[off]
            reg_id = body[off + 1]
            val = struct.unpack("<H", body[off + 2:off + 4])[0]
            out[reg_id] = val
            off += size + 1
        return out

    def pc(self, memspace=0):
        # heuristica: el PC es el registro de 16 bits con valor en rango de codigo
        rg = self.registers_get(memspace)
        for v in rg.values():
            if 0x8000 <= v <= 0xFFFF:
                return v
        return rg.get(3)

    def quit(self):
        try:
            rid = self._send(CMD_QUIT)
            self._recv_response(rid)
        except Exception:
            pass
        finally:
            if self.sock:
                self.sock.close()


def screencode_to_char(c):
    c &= 0x7f
    if c <= 31:
        return chr(c + 64)        # @ A-Z [ \ ] ^ _
    if c <= 63:
        return chr(c)             # espacio, signos, 0-9, ?
    return "."


def decode_screen(ram1000):
    rows = []
    for r in range(25):
        row = "".join(screencode_to_char(b) for b in ram1000[r * 40:r * 40 + 40])
        rows.append(row.rstrip())
    return rows


def launch_x64sc(rom_dir, port=6502, extra=None, logpath="/tmp/vice_test/mon.log"):
    args = ["xvfb-run", "-a", "x64sc", "-warp", "-sound",
            "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{port}"]
    if extra:
        args += extra
    log = open(logpath, "w")
    return subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, cwd=rom_dir)
