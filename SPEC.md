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
   Pendiente de validar en VICE: polaridad fisica de los bits de VIA1 y timing.
1b. (hecho) Recepcion de datos con deteccion de EOI (ultimo byte) y bucle de
   recepcion: tras un LISTEN con ATN ya liberado, recibe bytes hasta EOI o
   hasta que el controlador retome ATN, dejandolos en un buffer provisional.
   Verificado con co-simulacion temporizada: el talker en modo EOI no toca CLK
   y espera el pulso de reconocimiento del listener. Se comprueba que el EOI se
   detecta en el ultimo byte y que NO se dispara en transferencia normal.
   Limitacion conocida: el manejo de ATN a mitad de byte requiere la IRQ de CA1
   (no implementada aun); la version actual solo aborta entre bytes.
   Pendiente de validar en VICE: polaridad fisica y valor del timeout en us.
1c. (hecho) Rol de TALKER: turnaround talk-attention (tras recibir TALK +
   canal y liberarse ATN, la 1541 toma CLK y el host pasa a listener) y envio
   de byte con EOI opcional en el ultimo. Verificado en co-simulacion con el
   host actuando de listener: recibe el buffer completo y detecta el EOI solo
   en el ultimo byte. El cierre con UNTALK devuelve la 1541 a rol listener.
   Limitacion conocida: igual que en recepcion, el manejo de ATN a mitad de
   transferencia requiere la IRQ de CA1, no implementada aun.
   Pendiente de validar en VICE: polaridad fisica, retardos y timeout en us.
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
   Pendiente para un SAVE completo: asignar los bloques con el BAM y crear la
   entrada de directorio (3c y escritura de entrada).
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
4c. Job queue de bajo nivel (capa fisica, dirigida por IRQ). Pendiente; requiere
   verificacion en VICE/hardware, no en el harness py65. El banco de pruebas ya
   esta montado: test/vice_monitor.py es un cliente del monitor binario de VICE que
   arranca x64sc headless (bajo Xvfb), lee/escribe RAM y controla la ejecucion sin
   tocar ninguna ROM (solo observa RAM, Nivel B). test/test_vice_boot.py es su
   smoke test (arranca un C64 y comprueba el banner). Sobre esta base se escribira
   y verificara la capa fisica: cargar dos.bin como ROM de unidad (-dos1541),
   adjuntar un .d64 y comprobar por RAM que la unidad responde en el bus. Estos
   tests requieren las ROMs propietarias del C64 (no incluidas en el repo) y por eso
   no forman parte de "make test".

   Primer contacto con hardware (verificado): test/test_vice_drive.py carga dos.bin
   como ROM de unidad (-dos1541) con emulacion a nivel hardware y comprueba, leyendo
   la pagina cero de la unidad por el monitor binario, que tras el reset aparece el
   patron que escribe nuestro codigo (iec_dev=8, resto a 0). Es decir: el 6502 de la
   1541 emulada ejecuta nuestro vector de reset, inicia las VIAs y entra en el bucle
   del bus. Nuestra ROM arranca en el hardware emulado. Falta por verificar que la
   unidad responda al bus IEC con el timing real y, sobre todo, la capa fisica del
   disco (controlador IRQ, GCR a nivel de bit, motor, cabeza), que aun no existe.
5. Tipos de fichero: SEQ, PRG, USR y por ultimo REL.

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
