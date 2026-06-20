# Free DOS ROM for the Commodore 1541

[English](#english) | [Español](#espanol)

<a name="english"></a>

A drop-in replacement DOS ROM for the Commodore 1541 disk drive, written from
scratch under a permissive license with an auditable provenance chain. The
spirit is that of AltirraOS in the Atari 8-bit world: a free alternative that
behaves like the real drive on the bus. Sister project of
[Pascuals-BASIC](https://github.com/Pascual-Candel-Palazon/Pascuals-BASIC), the
free BASIC and KERNAL ROMs for the Commodore 64.

The ROM is a flat 16384-byte image (`dos.bin`) built from a single source file.

## Status

Implemented and verified functionally in VICE, against an original 1541 and the
C64 ROMs used only as opaque peripherals at the other end of the bus (never
disassembled):

- Serial IEC bus in both directions (listener and talker), with ATN handling and
  EOI: OPEN, CLOSE, send and receive.
- GCR 4-to-5 codec, checked by round-trip against an independent reference.
- Sector read from the physical layer (VIA2, byte-ready wired to the 6502 SO
  input, SYNC detection on PB7).
- Sector write to the physical layer (in-place: SYNC plus GCR block, with the
  per-zone bit rate), verified by write then read-back and by disk image
  persistence.
- BAM held in RAM (read once on open, flushed once on close).
- Directory: entry creation, listing (`LOAD "$",8`), and chaining beyond a single
  sector (more than eight files).
- File LOAD and SAVE end to end over the bus, single and multi-sector.
- Command and error channel (15): SCRATCH, RENAME, NEW (format) and VALIDATE.

Cross-checked against `c1541` as a reference and exercised from a C64 running both
the original KERNAL and the free Pascuals-BASIC KERNAL.

## Scope

This is a clean-room DOS. Because reading the original ROM is not allowed (see
provenance below), it does not aim to be compatible with software that depends on
the drive internals, such as fast loaders or internals-based copy protection.
That is a design boundary, not a missing feature. See `SPEC.md`.

## Usage

In VICE, with true drive emulation so the ROM actually runs on the emulated 1541:

```
x64sc -dos1541 dos.bin -drive8type 1541 -drive8truedrive
```

The C64 KERNAL, BASIC and character ROMs are proprietary and are not included
here. Supply your own (for example dumped from your own hardware), or use the
free Pascuals-BASIC ROMs.

## Building

Requirements: `cc65` (ca65 and ld65) for the ROM, `py65` for the logic tests, and
VICE (`x64sc`, `c1541`) plus `Xvfb` for the physical-layer tests.

```
ca65 -g -o src/dos.o src/dos.s
ld65 -C src/dos1541.cfg -o dos.bin src/dos.o
```

This produces the flat 16384-byte ROM image. `make test` runs the py65 logic
batteries.

## Verification

Two layers. The logic (BAM, directory, GCR codec, command parsing, file handling)
is verified with py65 unit batteries that run without an emulator. The physical
layer (VIA2 timing, IEC handshake, head read and write) is verified in VICE with
true drive emulation, using `c1541` and a real drive behavior as a black-box
reference: inputs and outputs on the bus and on the disk image are observed,
never the internal code of any original ROM.

## Provenance

Clean-room. The rules are in `PROCEDENCIA.md`. In short: Level A (public hardware,
disk format and bus protocol specifications) and Level B (observable black-box
behavior) are allowed; Level C (disassembly of the original ROM) is prohibited and
is neither read nor consulted. Any convergence with the original firmware on the
physical layer is dictated by the wiring of the 6522, not by copying.

This project never downloads or disassembles the original ROMs, and never
includes them. Any non-similarity verification against the original ROM should be
performed by a third party.

## License

MIT (`LICENSE`). The proprietary Commodore ROMs are not part of this project.

---

<a name="espanol"></a>

# ROM de DOS libre para la Commodore 1541

[English](#english) | [Español](#espanol)

Una ROM de DOS de reemplazo directo para la unidad de disco Commodore 1541,
escrita desde cero bajo una licencia permisiva y con una cadena de procedencia
auditable. El espiritu es el de AltirraOS en el mundo Atari de 8 bits: una
alternativa libre que se comporta como la unidad real en el bus. Proyecto hermano
de [Pascuals-BASIC](https://github.com/Pascual-Candel-Palazon/Pascuals-BASIC),
las ROMs libres de BASIC y KERNAL para el Commodore 64.

La ROM es una imagen plana de 16384 bytes (`dos.bin`) construida a partir de un
unico fichero fuente.

## Estado

Implementado y verificado funcionalmente en VICE, contra una 1541 original y las
ROMs del C64 usadas solo como perifericos opacos al otro extremo del bus (nunca
desensambladas):

- Bus serie IEC en ambos sentidos (listener y talker), con gestion de ATN y EOI:
  OPEN, CLOSE, envio y recepcion.
- Codec GCR de 4 a 5 bits, comprobado por round-trip contra una referencia
  independiente.
- Lectura de sector desde la capa fisica (VIA2, byte-ready cableado a la entrada
  SO del 6502, deteccion de SYNC en PB7).
- Escritura de sector en la capa fisica (in-place: SYNC mas bloque GCR, con la
  velocidad de bit de cada zona), verificada por escritura y relectura y por la
  persistencia en la imagen de disco.
- BAM mantenida en RAM (se lee una vez al abrir, se vuelca una vez al cerrar).
- Directorio: creacion de entradas, listado (`LOAD "$",8`) y encadenamiento mas
  alla de un solo sector (mas de ocho ficheros).
- LOAD y SAVE de ficheros de extremo a extremo por el bus, de uno y de varios
  sectores.
- Canal de comandos y errores (15): SCRATCH, RENAME, NEW (formatear) y VALIDATE.

Contrastado contra `c1541` como referencia y ejercitado desde un C64 con el KERNAL
original y con el KERNAL libre de Pascuals-BASIC.

## Alcance

Es un DOS clean-room. Como leer la ROM original no esta permitido (ver procedencia
mas abajo), no pretende ser compatible con software que dependa de los internals
de la unidad, como los fast loaders o las protecciones basadas en internals. Eso
es una frontera de diseno, no una carencia. Ver `SPEC.md`.

## Uso

En VICE, con emulacion de unidad real para que la ROM se ejecute de verdad en la
1541 emulada:

```
x64sc -dos1541 dos.bin -drive8type 1541 -drive8truedrive
```

Las ROMs de KERNAL, BASIC y caracteres del C64 son propietarias y no se incluyen
aqui. Usa las tuyas (por ejemplo volcadas de tu propio hardware) o las ROMs libres
de Pascuals-BASIC.

## Construccion

Requisitos: `cc65` (ca65 y ld65) para la ROM, `py65` para los tests de logica, y
VICE (`x64sc`, `c1541`) mas `Xvfb` para los tests de capa fisica.

```
ca65 -g -o src/dos.o src/dos.s
ld65 -C src/dos1541.cfg -o dos.bin src/dos.o
```

Esto produce la imagen plana de ROM de 16384 bytes. `make test` ejecuta las
baterias de logica en py65.

## Verificacion

Dos capas. La logica (BAM, directorio, codec GCR, parseo de comandos, manejo de
ficheros) se verifica con baterias unitarias en py65 que corren sin emulador. La
capa fisica (temporizacion de la VIA2, handshake IEC, lectura y escritura del
cabezal) se verifica en VICE con emulacion de unidad real, usando `c1541` y el
comportamiento de una unidad real como referencia de caja negra: se observan las
entradas y salidas en el bus y en la imagen de disco, nunca el codigo interno de
ninguna ROM original.

## Procedencia

Clean-room. Las reglas estan en `PROCEDENCIA.md`. En resumen: el Nivel A
(especificaciones publicas de hardware, formato de disco y protocolo del bus) y el
Nivel B (comportamiento observable de caja negra) estan permitidos; el Nivel C
(desensamblado de la ROM original) esta prohibido y no se lee ni se consulta.
Cualquier convergencia con el firmware original en la capa fisica la impone el
cableado del 6522, no una copia.

Este proyecto nunca descarga ni desensambla las ROMs originales, y nunca las
incluye. Cualquier verificacion de no-similitud contra la ROM original deberia
hacerla un tercero.

## Licencia

MIT (`LICENSE`). Las ROMs propietarias de Commodore no forman parte de este
proyecto.
