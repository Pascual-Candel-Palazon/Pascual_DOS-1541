# Capa fisica de lectura del disco (verificada en VICE)

Este documento recoge la capa fisica de lectura del controlador de disco: leer el
flujo GCR real del cabezal a traves de la VIA2, distinta de la capa logica (que
opera sobre un buffer de bytes GCR en memoria y ya estaba verificada con py65).

## Interfaz del hardware (Nivel A, documentacion publica)

Fuentes: Butterfield y la documentacion dispersa del controlador de disco de la
1541 (luigidifraia sobre block-sync/byte-sync, ythiee "Floppy Drive Deep Dive",
linusakesson sobre decodificacion GCR, xentax sobre VIA2 $1C01/$1C0F).

- VIA2_PA ($1C01): puerto de datos del cabezal. El convertidor serie-paralelo de
  8 bits entrega cada byte GCR ya alineado. Configurado como entrada al leer.
  Leerlo participa en el handshake (resincroniza byte-ready).
- Byte-ready (/byte-sync): cableado a la entrada SO (Set Overflow) del 6502, de
  modo que su estado se consulta con el flag V. La forma obligatoria de leer un
  byte es: clv / bvc (espera mientras V=0) / lda VIA2_PA. No es una rutina de la
  ROM 1541, es la unica interfaz posible del hardware (el flag V esta cableado al
  pin SO). El bucle de fetch dispone de unos 19 ciclos con holgura; por encima de
  ~26 ciclos se perderian bytes.
- VIA2_PB ($1C00): bit 7 = /SYNC (activo en bajo: 0 mientras se leen los 10 bits
  '1' del SYNC). Se espera con bit VIA2_PB / bpl. Bits 0-1 stepper (medias pistas),
  bit 2 motor, bit 3 LED, bits 5-6 zona de velocidad (bitrate).

## Rutinas implementadas (seccion "capa fisica, hardware VIA2" en src/dos.s)

- disk_motor_on: enciende motor (bit 2) y LED (bit 3) y espera el arranque.
- disk_wait_sync: espera el SYNC (PB7=0) con timeout de 16 bits; carry=0 ok,
  carry=1 si agota el tiempo.
- disk_read10 / disk_read10b: leen 10 bytes GCR a RAW_BUF / RAW_BUF2 con el
  handshake SO.
- disk_read_raw: motor + SYNC + lee RAW_LEN bytes crudos a RAW_BUF (prueba).
- disk_phys_test: prueba de extremo a extremo. Lee la cabecera y el bloque de
  datos del primer sector bajo el cabezal SEGUIDOS, sin decodificar en medio, y
  decodifica ambos despues. Solo se ensambla y se llama con -D PHYS_TEST.

## Hallazgo clave: no decodificar entre la cabecera y el bloque de datos

El layout fisico de un sector es: SYNC, cabecera (10 GCR), gap corto, SYNC, bloque
de datos (325 GCR), gap inter-sector. La decodificacion de la cabecera tarda
cientos de ciclos; si se hace entre leer la cabecera y esperar el SYNC de datos,
el bloque de datos pasa volando y se capta el SYNC de la cabecera del sector
siguiente (se observo marca $08 y la cabecera del sector 9 en lugar de la marca
$07). La 1541 real lee cabecera y bloque a buffer y los decodifica despues. El
codigo sigue ese orden.

## Verificaciones en VICE (disco de prueba, cabeza en pista 19 al arrancar)

- Lectura cruda: sync_error=$00; RAW_BUF empieza 52 57 A5 25 73 ... El primer byte
  $52 es la codificacion GCR del identificador de cabecera $08 (GCR del nibble $0 =
  01010, del $8 = 01001; los primeros 8 bits son 01010010 = $52). Le sigue el gap
  GCR de bytes $00 (patron ciclico A5 29 4A 52 94).
- Cabecera decodificada: pista=19 sector=8, HEADER_BUF = 08 1A 08 13 31 30 0F 0F.
  Marca $08, ID de disco "01", relleno $0F $0F, y el checksum cuadra
  (08^13^31^30 = $1A).
- Bloque de datos: marca = $07 (DATA_MARK correcta), bytes 07 00 00 00.

## Como reproducir

Las pruebas de la capa fisica requieren VICE con true drive emulation y un ROM
ensamblado con -D PHYS_TEST (py65 no emula la VIA2 ni el flujo del disco). Ver
test/disco_fisico_vice.py.

## Stepper y SEEK (verificado en VICE)

Segun el manual de servicio 1540/1541, los bits 0-1 de VIA2_PB (STP0, STP1) forman
un contador binario de cuatro fases que la PLA convierte en las cuatro salidas del
motor paso a paso. Incrementar ese contador mueve el cabezal medio paso en un
sentido y decrementarlo en el otro. Como el cabezal es de 48 tpi sobre un
mecanismo de 84 pistas, cada pista son dos medios pasos (double-stepping). El
cabezal no tiene sensor de posicion: la pista actual se conoce leyendo una
cabecera (cada cabecera lleva su numero de pista) y se mantiene por software.

Rutinas (en src/dos.s): disk_step_in (fase+1), disk_step_out (fase-1), ambas
preservando los demas bits de PB; disk_step_delay (asentamiento); disk_seek (mueve
de cur_track a want_track contando pasos); disk_find_current_track (lee una
cabecera y fija cur_track); disk_read_hdr_retry (lee una cabecera valida
reintentando, porque la primera tras mover el cabezal suele estar corrupta).

Direccion verificada en VICE: disk_step_in mueve hacia adentro (pista mayor),
disk_step_out hacia afuera. Prueba (test/seek_vice.py, ensambla con -D SEEK_TEST):
desde la pista de arranque, seek hacia adentro a la 24 y luego hacia afuera a la
17, confirmando cada destino con una lectura de cabecera valida. El reintento de
lectura es imprescindible: sin el, la cabecera inmediatamente posterior al
movimiento daba hdr_error.

Nota sobre la zona de velocidad: las lecturas en pistas de zonas distintas (17 en
zona 3, 24 en zona 2) funcionaron en VICE sin ajustar los bits 5-6 de PB. En
hardware real el bitrate por zona debe coincidir con la pista; queda pendiente
seleccionar la zona por pista para correccion fuera del emulador.

## Lectura de un sector arbitrario y cadena completa (resuelto)

Busqueda fisica del sector (disk_find_sector_hw): con el cabezal ya en la pista,
recorre el anillo leyendo 10 bytes tras cada SYNC y distingue cabecera de bloque
de datos por el PRIMER byte GCR: $52 codifica la marca de cabecera ($08) y $53 la
de datos ($07). Solo cuando es una cabecera ($52) lee a continuacion su bloque de
datos (segundo SYNC + 325 bytes GCR a GCR_BLK) y, despues, decodifica la cabecera
para ver si es el sector buscado. Decodificar (lento) entre cabecera y datos hacia
perder el bloque; por eso se leen seguidos y se decodifica al final. Sin la
distincion $52/$53 la busqueda se desincronizaba (capturaba el SYNC de datos y
leia un bloque como si fuera cabecera).

Lectura del bloque completo: disk_read_block_gcr lee los 325 bytes en dos tramos
(256 + 69) con direccionamiento absoluto indexado; la transicion entre tramos
cuesta pocos ciclos, muy por debajo del tiempo de un byte, asi que no se pierde
ninguno. disk_read_data (capa logica) decodifica los 325 GCR a 260 bytes en
DATA_DEC_BUF, valida la marca $07 y el checksum (XOR de los 256 datos). El destino
($0400) va por detras del origen ($04BB), de modo que la decodificacion no pisa
bytes aun sin leer.

disk_read_sector_hw une todo: find_current_track (motor + cur_track) + seek +
find_sector_hw. Verificado (test/sector_vice.py, -D SECTOR_TEST): los 256 bytes
del sector 18/1 leidos del hardware coinciden BYTE A BYTE con el .d64.

Listado de directorio (disk_build_dir): lee fisicamente el BAM (18/0) y la cadena
de sectores de directorio (18/1, siguiendo enlaces) y genera en LIST_BUF el
programa BASIC del directorio (titulo, una linea por fichero, BLOCKS FREE).
Verificado (test/dir_vice.py, -D DIR_TEST) contra c1541 -dir.

Integracion con el bus: iec_talk, tras el turnaround, mira el nombre recibido en
DATA_BUF. Si es "$", genera el directorio y lo transmite; si no, iec_load_file
localiza el fichero (dir_find_in_buf sobre el directorio fisico) y transmite su
contenido bloque a bloque siguiendo la cadena de sectores (streaming), con EOI en
el ultimo byte del ultimo bloque. La transmision usa iec_send_buffer (buffer de
longitud variable de 16 bits; tx_last controla si el ultimo byte lleva EOI).

Verificado de extremo a extremo en el C64 real emulado (test/load_vice.py, ROM de
produccion sin flags): LOAD"$",8 carga el directorio del disco en $0801 y
LOAD"DATOS",8,1 carga un fichero por nombre en su direccion, recorriendo OPEN ->
nombre -> iec_talk -> lectura fisica (seek + busqueda + GCR + checksum) ->
generacion/streaming -> transmision con EOI -> carga en el C64.

## Escritura fisica de sector (disk_write_sector_hw)

La escritura es "in place": se localiza la cabecera del sector (no se reescribe),
se salta el header gap y se reescribe solo el bloque de datos (SYNC + 325 GCR).
Registros (fuente: specs de hardware, Nivel A): VIA2_PCR ($1C0C) selecciona el
modo de la cabeza (CB2 = 110 escritura, 111 lectura; PCR_WRITE = $CE) y DDRA del
puerto A ($1C03) = $FF pone el puerto en salida (revierte a $00 al terminar). El
byte-ready sigue siendo el flag V (SO del 6502), igual que en lectura. El bucle de
escritura hace prefetch (LDA antes del BVC) para que tras el byte-ready solo queden
CLV y STA; sin el prefetch el GCR se desalinea.

Tres detalles que costaron depuracion en VICE:

1. Codificacion GCR hacia atras. DATA_DEC_BUF ($0400) y GCR_BLK ($04BB) se solapan
   en 4 bytes; codificando hacia adelante el destino (5 bytes/grupo) adelanta al
   origen (4/grupo) y pisa los ultimos datos antes de leerlos. disk_build_data
   codifica del grupo 64 al 0 para que el grupo solapado se lea antes de
   sobrescribirlo. La decodificacion (lectura) no sufre esto porque su destino va
   por debajo del origen.

2. Header gap. La ventana valida para empezar a escribir tras la cabecera, medida
   por barrido en VICE, es de 4 a 6 bytes; WGAP_BYTES se fija en 5.

3. Zona de velocidad (disk_set_speed_zone). En ESCRITURA los bits se generan al
   bitrate de los bits 5-6 de VIA2_PB, que debe casar con la densidad de la pista:
   pistas 1-17 zona 3 ($60), 18-24 zona 2 ($40), 25-30 zona 1 ($20), 31+ zona 0
   ($00). Sin ajustarla, escribir fuera de la zona 2 produce un bloque que no
   vuelve a leerse (checksum erroneo). La LECTURA tolera la zona porque sigue el
   flujo que genera VICE; la escritura no. disk_write_sector_hw la fija tras el
   seek. Verificado en zona 2 (pista 20) y zona 3 (pista 1): relectura correcta y
   persistencia en el .d64 (test/write_vice.py).

## SAVE de fichero por bus (file_save_open / file_save_byte / file_save_close)

Cuando el C64 hace SAVE"X",8 el bus recibe OPEN ($Fx) + nombre, DATA ($6x) + los
bytes del fichero (direccion de carga incluida) y CLOSE ($Ex). iec_atn distingue
ahora estos tres comandos secundarios sobre un canal de escritura (!= 0):
OPEN deja iec_save_opening pendiente, el primer DATA copia el nombre (iec_copy_name)
y llama file_save_open, e iec_recv_data redirige cada byte a file_save_byte. CLOSE
invoca file_save_close. Un canal != 0 sin OPEN previo no entra en modo SAVE (los
datos siguen yendo a DATA_BUF), para no romper el listener generico.

El sector en construccion vive en SAVE_BUF; al llenarse (256) se asigna el
siguiente bloque, se fija el enlace y se graba el actual. La BAM se mantiene en RAM
durante todo el SAVE: se lee una sola vez al abrir (save_bam_load) y se graba una
sola vez al cerrar (save_bam_flush), evitando releerla/reescribirla por bloque.
Esto es posible porque GCR_BLK se reubico a $04BB-$05FF para que termine justo antes
de BAM_BUF ($0600) y deje de pisarla; su solape con DATA_DEC_BUF ($04BB-$0503, 73
bytes) lo absorben la codificacion inversa (build_data, grupo 64 a 0) y la
decodificacion hacia adelante, ambas verificadas en VICE en lectura y escritura.
El mapa $0400-$07FF queda: DATA_DEC_BUF $0400-$0503, GCR_BLK $04BB-$05FF (solapa
DATA_DEC), BAM_BUF $0600-$06FF, DIR_BUF/SAVE_BUF $0700-$07FF.

Al cerrar se graba el ultimo sector (enlace track 0, byte 1 = offset del ultimo
byte util) y se crea la entrada de directorio recorriendo la cadena de sectores de
directorio (dir_add_chain): busca un slot libre en 18/1 y los sucesivos; si todos
estan llenos, asigna y enlaza un nuevo sector de directorio en la pista 18
(dir_alloc_sector, que a diferencia de bam_alloc_next si reparte en la pista 18, y
opera sobre la BAM en RAM). La busqueda de fichero del LOAD recorre la misma cadena
(dir_find_chain), de modo que se soportan mas de 8 ficheros.

Offset del contador de bloques en la entrada de directorio: bytes 30-31 de la
entrada (formato CBM canonico), no 28-29 (esos son track/sector de reemplazo de
@SAVE). dir_make_entry, dir_extract y dir_list usan +30/+31; esto ademas corrige la
lectura del tamano en discos creados por c1541.

Verificado de extremo a extremo en VICE: SAVE"T",8 desde el C64 con KERNAL original
y desde el C64 100% libre (Pascuals-BASIC) produce un fichero PRG cuyo contenido,
extraido con c1541, coincide byte a byte con la memoria guardada por el C64
(test/save_bus_vice.py, test/save_bus_libre_vice.py). El SAVE multisector (302
bytes en dos sectores, pista 1 zona 3) tambien se relee correcto con c1541
(test/save_logic_vice.py). El encadenamiento de directorio se verifica grabando 10
ficheros (fuerza un segundo sector de directorio) y cargando el decimo, que cae en
ese sector, desde el C64 (test/dir_chain_vice.py). La consistencia de la BAM tras
el SAVE se comprueba con c1541 -validate, que reconstruye la BAM desde el directorio
sin alterar los bloques libres.

Nota de juego de caracteres: dos1541 graba el nombre tal como lo envia el C64 (p.ej.
'F' = $46 en el modo mayusculas por defecto). Discos cuyos nombres se crearon con
c1541 desde la linea de ordenes pueden llevar el nombre en otro codigo PETSCII (las
mayusculas ASCII a $C1..$DA), por lo que un LOAD tecleado en el C64 podria no
casar; es un detalle del host c1541, no del DOS.
