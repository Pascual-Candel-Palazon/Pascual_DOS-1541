# dos1541 clean room  ::  especificacion

Reemplazo limpio del DOS de la Commodore 1541, escrito desde cero a partir de
especificaciones publicas. Sin codigo de Commodore (ver PROCEDENCIA.md).

## Alcance

Nivel 1: reemplazo funcional. Da soporte al uso normal de la unidad y nada
mas. Queda explicitamente fuera la compatibilidad con fast loaders y con
protecciones anticopia que dependan de direcciones internas, del job queue
o del timing fino del controlador. Esa compatibilidad exigiria reproducir la
estructura interna de Commodore, lo que entra en conflicto con la regla
clean room (Nivel C de PROCEDENCIA.md) y por tanto se descarta.

Target de verificacion: VICE en modo True Drive Emulation (TDE), con un host
C64 provisto por ROMs clean room propias (Pascual's BASIC), de modo que el
banco de pruebas completo quede libre de procedencia contaminada.

### Funcionalidad objetivo (Nivel 1)

- Bus serie IEC, lado dispositivo: ATN, listen/talk, transferencia byte a byte
  con handshake, deteccion de fin de fichero (EOI), numero de dispositivo.
- Canal de comandos (direccion secundaria 15): N (format), I (init), V
  (validate), S (scratch), R (rename), C (copy), B (block), M (memory), U.
- Apertura y cierre de canales de datos, ficheros PRG, SEQ, USR y REL.
- BAM (mapa de bloques libres), directorio, asignacion de bloques.
- Controlador de disco: stepper, deteccion de SYNC, lectura y escritura de
  sectores, codec GCR (4 a 5 bits), formateo.
- Mensajes de error de canal en el formato esperado por el host.

## Hardware (Nivel A, interfaz publica)

- CPU MOS 6502 a 1 MHz.
- RAM 2 KB en $0000-$07FF.
- ROM 16 KB en $C000-$FFFF.
- VIA 1 en $1800: bus serie IEC (ATN, CLK, DATA, ATNA).
- VIA 2 en $1C00: control del mecanismo.
- Vectores en $FFFA (NMI), $FFFC (RESET), $FFFE (IRQ/BRK).

### VIA 2, puerto B ($1C00), distribucion de bits

Segun especificaciones publicas, pendiente de validar contra el comportamiento
observable del hardware:

| bit | funcion                         | dir |
|-----|---------------------------------|-----|
| 0-1 | fase del motor de paso          | out |
| 2   | motor de giro (1 = ON)          | out |
| 3   | LED de actividad (1 = encendido)| out |
| 4   | sensor de proteccion de escritura | in |
| 5-6 | seleccion de densidad           | out |
| 7   | deteccion de SYNC (activo bajo) | in  |

## Mapa de RAM (provisional)

El reparto de la RAM de 2 KB se concretara al implementar el sistema de
ficheros. Como el proyecto es Nivel 1, no se reproduce el layout de Commodore:
la pagina cero del DOS, los buffers de sector y las variables del job queue se
ubican donde convenga al diseno propio. Esto es deliberado y es lo que mantiene
el proyecto limpio.

## Plan de hitos

0. (hecho) Arranque: reset, init de VIAs, bucle con latido del LED. Verificado
   en harness py65. El latido se retiro al implementar el hito 1; el arranque
   queda en la historia del repo (src/dos_hito0.s.bak).
1a. (hecho) Bus serie IEC, lado LISTENER: deteccion de ATN, recepcion de byte
   con handshake de 8 bits (LSB primero, sin EOI) y parseo de comandos
   (LISTEN, TALK, UNLISTEN, UNTALK, direccion secundaria). Verificado con
   co-simulacion: un controlador C64 simulado dialoga con la 1541 a traves de
   un modelo de las lineas del bus (test/test_iec.py).
   Validado despues en VICE (polaridad y timing reales, ver NOTAS_BUS_VICE.md).
1b. (hecho) Recepcion de datos con deteccion de EOI (ultimo byte) y bucle de
   recepcion: tras un LISTEN con ATN ya liberado, recibe bytes hasta EOI o
   hasta que el controlador retome ATN, dejandolos en un buffer provisional.
   Verificado con co-simulacion temporizada: el talker en modo EOI no toca CLK
   y espera el pulso de reconocimiento del listener. Se comprueba que el EOI se
   detecta en el ultimo byte y que NO se dispara en transferencia normal.
   Limitacion conocida: el manejo de ATN a mitad de byte requiere la IRQ de CA1
   (no implementada aun); la version actual solo aborta entre bytes.
   Validado despues en VICE (ver NOTAS_BUS_VICE.md).
1c. (hecho) Rol de TALKER: turnaround talk-attention (tras recibir TALK +
   canal y liberarse ATN, la 1541 toma CLK y el host pasa a listener) y envio
   de byte con EOI opcional en el ultimo. Verificado en co-simulacion con el
   host actuando de listener: recibe el buffer completo y detecta el EOI solo
   en el ultimo byte. El cierre con UNTALK devuelve la 1541 a rol listener.
   Limitacion conocida: igual que en recepcion, el manejo de ATN a mitad de
   transferencia requiere la IRQ de CA1, no implementada aun.
   Validado despues en VICE. Como talker, la espera de listener listo vigila
   ATN: si el host cierra el canal entre bytes (GET# hace un TALK por byte) la
   transmision se corta sin perder la posicion.
2a. (hecho) Codec GCR (formato publico, codificacion 4-a-5 bits): rutinas
   gcr_encode (4 bytes -> 5) y gcr_decode (5 -> 4) con sus tablas directa e
   inversa. Verificado como logica pura (sin timing) en test/test_gcr.py: el
   encode coincide con una referencia que usa la misma tabla publica en 772
   vectores y el round-trip decode(encode(x)) es exacto.
2b. (parcial, hecho la lectura logica de sector) Controlador de disco sobre
   una pista en GCR: disk_find_sync localiza el SYNC; disk_read_header decodifica
   y valida la cabecera (marca $08, checksum, track/sector); disk_read_data
   decodifica el bloque de datos (260 bytes), valida marca $07 y checksum, y deja
   los 256 bytes utiles en DATA_DEC_BUF+1. Verificado como logica pura en
   test/test_disk.py (cabecera y datos validos, checksum corrupto y marca
   incorrecta rechazados, SYNC ausente detectado). La pista se modela como bytes;
   el alineamiento de bits del SYNC y la rotacion fisica son la capa de IRQ.
2c. (hecho) Localizar un sector concreto en una pista con varios sectores:
   disk_find_sector recorre los bloques, identifica la cabecera del sector
   pedido (want_track/want_sector) y lee su bloque de datos. disk_find_sync usa
   un puntero de 16 bits para cruzar bloques de datos largos.
   disk_sectors_per_track da la geometria por zonas (21/19/18/17). Verificado en
   test/test_disk.py: localiza el sector pedido (primero, intermedio, ultimo) con
   sus datos, rechaza sector ausente y track erroneo, y la geometria es correcta
   en las cuatro zonas. El offset dentro de una imagen .d64 es responsabilidad
   del host, no de la 1541, y queda fuera de la ROM.
2e. (hecho) Escritura de sector (codificacion, espejo de la lectura):
   disk_build_data anade marca $07, checksum y relleno a los 256 bytes y los
   codifica a 325 bytes GCR; disk_build_header construye la cabecera (marca $08,
   checksum) y la codifica a 10 bytes GCR. Verificado en test/test_disk.py: el
   GCR producido coincide byte a byte con la referencia y el round-trip
   (construir, codificar, releer) recupera datos y metadatos.
2d. Capa fisica dirigida por IRQ: ensamblado de bytes desde el shift register de
   la VIA2, deteccion de SYNC a nivel de bit, control de la cabeza y grabado.
   Solo validable en VICE / hardware.
3a. (hecho) BAM (mapa de bloques disponibles) sobre el sector 18/0 ya
   decodificado: bam_free_on_track, bam_is_free, bam_alloc, bam_free_block y
   bam_total_free (excluye la pista 18). Verificado en test/test_bam.py: libres
   por pista en las cuatro zonas, consulta de bloques, total correcto, y
   asignar/liberar ajustando bit y contador (con alloc idempotente).
3b. Directorio: recorrer los sectores de directorio (enlazados), leer las
   entradas de 32 bytes (tipo, nombre, track/sector inicial, tamano) y buscar un
   fichero por nombre. Logica pura, verificable.
3b. (hecho) Directorio: dir_find_in_buf busca un fichero por nombre en las 8
   entradas de un sector (DIR_BUF), extrae tipo, track/sector inicial y tamano;
   dir_get_link da el enlace al siguiente sector. Verificado en test/test_dir.py:
   busqueda de PRG y SEQ, tamano de 16 bits, entradas borradas ignoradas, nombre
   ausente, y recorrido entre dos sectores enlazados. La carga del siguiente
   sector de directorio es I/O de disco (capa de integracion).
3c. Asignacion de bloques de orden superior (siguiente bloque libre con la
   politica de intercalado) cuando se implemente la escritura de ficheros.
3d. (hecho) Lectura de fichero por cadena de bloques: file_block_process sigue
   el enlace track/sector de cada bloque, detecta el ultimo (track 0) y sus
   bytes utiles, y vuelca el contenido por out_ptr. Verificado en
   test/test_file.py incluyendo un caso end-to-end (resolver un nombre en el
   directorio y leer el fichero completo, el equivalente logico de un LOAD):
   ficheros de 1 a 3 bloques y los casos limite (bloque final lleno, bloque con
   un solo byte util) se recuperan byte a byte.
3e. (hecho) Escritura de fichero por cadena de bloques (espejo de 3d):
   file_build_block construye cada bloque con su enlace (o track 0 y el offset
   final en el ultimo) y los datos. Verificado en test/test_file.py: los bloques
   producidos coinciden con la referencia y el round-trip escritura->lectura
   (SAVE->LOAD) recupera el contenido en ficheros de 1 a 4 bloques.
   El SAVE completo se cierra en 3c.
3c. (hecho) Asignacion de bloques con bam_alloc_next (politica simple, sin
   intercalado todavia) y creacion de entrada de directorio con dir_make_entry.
   SAVE completo verificado en test/test_save.py: asignar los bloques, construir
   la cadena, crear la entrada, y un LOAD posterior recupera el contenido byte a
   byte. Dos ficheros coexisten sin solaparse y ambos quedan en el directorio.
4a. (hecho) Canal de estado (canal 15): err_build_status construye la cadena
   "NN,MENSAJE,TT,SS" + CR a partir del codigo de error, con tabla de mensajes
   del DOS. Verificado en test/test_cmd.py (codigos conocidos, generico para
   desconocidos, conversion a dos digitos).
4b. (parcial) Parseo y ejecucion de comandos del canal 15. Hecho y verificado en
   test/test_cmd.py:
   - cmd_parse_name: extrae el nombre tras ':', relleno $A0, trunca a 16, detecta
     falta de ':'.
   - SCRATCH: dir_scratch_entry marca la entrada como borrada y la cadena de
     bloques se libera con bam_free_block. Round-trip: guardar, borrar y comprobar
     que la entrada desaparece y los bloques vuelven a estar libres.
   - RENAME: cmd_parse_rename separa "nuevo=viejo" en NAME_BUF2/NAME_BUF;
     dir_rename_entry reescribe el nombre. Round-trip: el fichero se localiza por
     el nombre nuevo en el mismo bloque y el viejo deja de encontrarse.
   - NEW: disk_format_bam reconstruye el BAM (todas las pistas libres salvo 18/0 y
     18/1) con cabecera de formato. cmd_parse_format parsea "N:nombre,id" y
     disk_write_header escribe la identidad del disco. El sector 18/0 completo (256
     bytes) es identico a la referencia VICE. Deja 664 bloques libres.
   - Listado de directorio (LOAD "$",8): dir_make_listing_line genera la linea
     BASIC de una entrada (enlace, numero de linea = bloques, relleno de
     alineacion, nombre entrecomillado, tipo de 3 letras); dir_make_title_line el
     titulo (video inverso, nombre e ID); dir_make_free_line la linea
     "BLOCKS FREE."; dir_make_end el cierre. list_put vuelca por puntero. Todo
     verificado byte a byte. El recorrido de la cadena de sectores de directorio
     es orquestacion sobre estas rutinas.
   - VALIDATE: reconstruye el BAM (disk_format_bam) y vuelve a marcar los sectores
     de directorio y las cadenas de cada fichero con bam_alloc. disk_link_valid
     descarta enlaces fuera de rango para no seguir cadenas corruptas. Verificado
     con un round-trip de recuperacion desde un BAM con basura.
   La capa logica del DOS esta completa. El BAM y la entrada de directorio se
   validan ademas byte a byte contra la referencia VICE (test/test_vice_ref.py).
4c. Capa fisica y bus en VICE (hecho): lectura y escritura de sector, seek, zona
   de velocidad, LOAD y SAVE de extremo a extremo. Ver NOTAS_DISCO_VICE.md y
   NOTAS_BUS_VICE.md. La cola de trabajos dirigida por IRQ de la unidad original
   no se reproduce: el DOS es sincrono (Nivel 1).
4d. (hecho) Canal 15 cableado al bus. OPEN 15 con nombre o PRINT#15 dejan el
   texto en DATA_BUF; al UNLISTEN queda cmd_pending y el bucle principal lo
   ejecuta (cmd_execute) antes de atender de nuevo el bus. TALK sobre el canal
   15 sirve STATUS_BUF desde stat_rd, con EOI en el CR; leido entero, el estado
   vuelve a 00. Ordenes: S (varios nombres, comodines * y ?), R, N (sin
   formateo fisico), V, I, UJ/U: (reinicio). Desconocidas: 31. LOAD, SAVE y el
   directorio fijan tambien el estado (21, 62, 63, 72...). LOAD de un fichero
   inexistente suelta CLK y DATA tras el turnaround (antes los retenia y el host
   esperaba sin fin): el host termina por tiempo. Verificado en VICE
   con test/canal15_vice.py (C64 con las ROMs de Pascuals-BASIC, disco
   comprobado con c1541, BAM igual a la que produce c1541 -validate).
   Pendiente: formateo fisico en NEW, ordenes C, B, M y resto de U, proteccion
   contra escritura, IRQ de ATN (CA1).
   Contraste de caja negra con una 1541 de referencia en VICE
   (test/oracle_estado_vice.py, solo se compara la cadena de estado que llega al
   C64): coinciden los formatos de 00, 01, 21, 30, 31, 34, 62 y 63, espacios
   incluidos. Diferencias conocidas: el texto de 73 (identificacion propia, a
   proposito); SAVE con el disco lleno da 72,DISK FULL (la referencia da
   67,ILLEGAL TRACK OR SECTOR,36,01, un efecto de su organizacion interna que no
   se reproduce); sin disco, una orden tras un I fallido da 21 (la referencia
   recuerda el estado y da 74,DRIVE NOT READY), y LOAD"$" informa 21 en 18/00
   (la referencia en 18/01).
5. (hecho salvo REL) Canales de datos 1 a 14. El OPEN deja el nombre en
   DATA_BUF y al UNLISTEN queda open_pending; chan_open lo ejecuta desde el
   bucle principal. chan_parse separa "[@][0:]nombre[,campo[,campo]]": cada campo
   se clasifica por su letra (S, P, U, L tipos; R, W, A, M modos), de modo que
   "NOMBRE,W" es un modo. Sin modo: escritura en el canal 1 (SAVE), lectura en
   los demas; sin tipo al escribir: PRG en el canal 1, SEQ en los demas.
   - Lectura (R): iec_talk_read entrega el fichero bloque a bloque desde
     DATA_DEC_BUF, con EOI en el ultimo byte. La posicion se conserva entre TALKs
     (GET# pide un byte por TALK). dsk_gen cambia cada vez que otra operacion
     pisa DATA_DEC_BUF; si cambio, rd_ensure relee el bloque en curso.
   - Escritura (W) y anadir (A): el camino del SAVE (SAVE_BUF, BAM en RAM) con
     el tipo de la entrada en save_ftype. "@" reemplaza: al cerrar se borra la
     version anterior (dir_walk) antes de crear la entrada. A recorre la cadena
     hasta el ultimo bloque, sigue llenandolo y al cerrar actualiza el tamano de
     la entrada existente.
   - Un unico fichero de datos abierto a la vez (RAM de 2 KB con buffers
     compartidos): otro OPEN con el primero abierto da 70 NO CHANNEL. La unidad de
     referencia admite varios.
   - Tolerancia a un host que atiende interrupciones en mitad del protocolo (con
     el KERNAL libre se perdian bytes y aparecia ST=$80 de forma intermitente):
     tras ATN se espera a ver CLK asertado antes del primer byte (con limite de
     unos 12 ms); en el turnaround se espera a que el host suelte CLK antes de
     tomarlo, y se mantiene asertado unos 5 ms antes del primer byte para que el
     host no pierda el pulso. Como talker, un ATN a mitad de byte aborta el envio
     y el byte no cuenta como entregado.
   Verificado en VICE con test/canales_vice.py (ROMs del C64 originales y
   libres; contenido y tipos comprobados con c1541) y contrastado con una 1541
   de referencia como caja negra (test/oracle_canales_vice.py).
   Pendiente: REL (tipo L), modo M, varios ficheros abiertos a la vez.

## Toolchain

- Ensamblador: cc65/ca65.
- Enlazado: ld65 con src/dos1541.cfg, produce dos.bin de 16384 bytes exactos.
- Pruebas rapidas: harness py65 en test/.
- Validacion final: VICE TDE (verificar el nombre exacto del recurso de ROM de
  drive en la version de VICE usada antes de scriptar el headless).

## Build

    ca65 -g -o src/dos.o src/dos.s
    ld65 -C src/dos1541.cfg -Ln dos.lbl -o dos.bin src/dos.o
    python3 test/harness.py
