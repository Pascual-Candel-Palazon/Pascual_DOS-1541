; ============================================================================
;  dos1541 clean room  ::  hito 1c  ::  rol de TALKER (turnaround + EOI)
; ----------------------------------------------------------------------------
;  Reemplazo limpio del DOS de la Commodore 1541 (Nivel 1).
;  Escrito desde cero a partir de especificaciones publicas. Sin desensamblado
;  de la ROM original (ver PROCEDENCIA.md).
;
;  Anade al listener (1a/1b) el rol de TALKER:
;    - turnaround talk-attention: tras recibir TALK + canal y liberarse ATN, la
;      1541 toma el rol de talker (asierta CLK, libera DATA) y el host pasa a
;      listener.
;    - iec_send_byte: envia un byte como talker (LSB primero) con EOI opcional.
;    - iec_talk: transmite un buffer de prueba (TX_BUF) con EOI en el ultimo
;      byte. El origen real sera el buffer de canal cuando exista el sistema de
;      ficheros; por eso, al terminar, se limpia ST_TALK (canal agotado).
;
;  ADVERTENCIA DE POLARIDAD Y TIMING (validar en VICE / hardware): la polaridad
;  de los bits de VIA1 es hipotesis de especificacion publica; el harness usa
;  la misma convencion. Los retardos (BIT_DELAY) y el timeout de EOI son
;  elecciones propias; el harness solo verifica el orden relativo de los
;  eventos, no los valores en us.
;  Convencion: escribir 1 = asserted (linea a tierra); leer 1 = asserted;
;  dato en DATA: asserted = bit logico 0, liberada = bit logico 1.
; ============================================================================

VIA1_PB   = $1800
VIA1_PA   = $1801
VIA1_DDRB = $1802
VIA1_DDRA = $1803
VIA2_PB   = $1C00
VIA2_PA   = $1C01
VIA2_DDRB = $1C02
VIA2_DDRA = $1C03
VIA2_PCR  = $1C0C         ; Peripheral Control Register de VIA2

; PCR: CB2 (bits 7-5) = modo de cabeza (110 escritura, 111 lectura);
; CA2 (bits 3-1) = SOE del byte-ready (111 activado). Bits 4 y 0 a 0.
PCR_READ  = %11101110     ; $EE: cabeza en lectura, SOE activo
PCR_WRITE = %11001110     ; $CE: cabeza en escritura, SOE activo
.ifndef WGAP_BYTES
WGAP_BYTES = 5            ; bytes del header gap a saltar antes de escribir
.endif                    ; (ventana valida medida en VICE: 4 a 6; 5 es el centro)
.ifndef NSYNC
NSYNC = 5                 ; bytes $FF de SYNC del bloque de datos
.endif

DATA_IN   = %00000001
DATA_OUT  = %00000010
CLK_IN    = %00000100
CLK_OUT   = %00001000
ATNA      = %00010000
ATN_IN    = %10000000
VIA1_DDRB_INIT = DATA_OUT | CLK_OUT | ATNA

DATA_OUT_CLR = <(~DATA_OUT)
CLK_OUT_CLR  = <(~CLK_OUT)
ATNA_CLR     = <(~ATNA)

LED_BIT      = %00001000
VIA2_PB_OUTS = %01101111

ST_LISTEN = %00000001
ST_TALK   = %00000010
ST_LISTEN_CLR = <(~ST_LISTEN)
ST_TALK_CLR   = <(~ST_TALK)

; timeout de EOI en recepcion (contador de 8 bits), pulso de reconocimiento y
; retardo por bit en transmision. Valores propios, a afinar en VICE.
EOI_TO    = $40
EOI_PULSE = $20
BIT_DELAY = $10

DATA_BUF  = $0300         ; buffer provisional de recepcion
TX_LEN    = 3             ; longitud del buffer de transmision de prueba

; --- controlador de disco ---
MOTOR_BIT  = %00000100    ; VIA2_PB bit 2: motor del disco (1 = encendido)
STEP_MASK  = %00000011    ; VIA2_PB bits 0-1: fase del stepper (medias pistas)
ZONE_MASK  = %01100000    ; VIA2_PB bits 5-6: zona de velocidad (bitrate)
SYNC_FLAG  = %10000000    ; VIA2_PB bit 7: /SYNC, activo en bajo (0 = en SYNC)
RAW_BUF    = $02C0        ; cabecera GCR cruda (10 bytes); usado tambien en pruebas
RAW_BUF2   = $02D0        ; segundo buffer crudo de prueba (10 bytes)
GCR_BLK    = $04BB        ; bloque de datos GCR crudo (325 bytes, $04BB-$05FF).
                          ; Termina justo antes de BAM_BUF ($0600) para no pisarlo,
                          ; permitiendo mantener la BAM en RAM durante un SAVE. El
                          ; solape con DATA_DEC_BUF ($04BB-$0503) lo maneja la
                          ; codificacion inversa (build_data) y la decodificacion.
RAW_LEN    = 64           ; bytes crudos a leer en la prueba fisica
SYNC_MIN   = 5            ; bytes $FF minimos para reconocer un SYNC
NAME_BUF   = $0280        ; nombre de fichero buscado (16 bytes)
CMD_BUF    = $0240        ; comando recibido por el canal 15 (texto)
NAME_BUF2  = $0268        ; segundo nombre (RENAME: nombre nuevo, 16 bytes)
STATUS_BUF = $0290        ; cadena del canal de estado (hasta $02BF)
HEADER_BUF = $02F0        ; 8 bytes decodificados de la cabecera
HDR_TPL    = $02E0        ; 10 bytes GCR: plantilla de la cabecera buscada (escritura)
DATA_DEC_BUF = $0400      ; 260 bytes decodificados del bloque de datos (RAM real)
DIR_BUF    = $0700        ; sector de directorio (256 bytes)
CHAIN_BUF  = $0700        ; buffer de sector para la cadena de fichero (compartido)
SAVE_BUF   = $0700        ; buffer del sector en construccion durante un SAVE
FTYPE_PRG_CLOSED = $82    ; tipo de entrada de directorio: PRG ($02) + cerrado ($80)
HDR_MARK   = $08          ; marca de bloque de cabecera
DATA_MARK  = $07          ; marca de bloque de datos
MAX_SCAN   = $0800        ; bytes maximos a escanear por SYNC
MAX_TRIES  = 64           ; bloques maximos a examinar buscando un sector
BAM_BUF    = $0600        ; sector BAM (pista 18 sector 0) en RAM
LIST_BUF   = $0300        ; programa BASIC del directorio generado (LOAD "$")

.zeropage
iec_dev:   .res 1
iec_state: .res 1
iec_sa:    .res 1
iec_cmd:   .res 1
iec_byte:  .res 1
iec_eoi:   .res 1         ; EOI del ultimo byte recibido (transitorio)
iec_data_eoi: .res 1      ; una transferencia de datos termino con EOI
iec_abort: .res 1         ; recepcion abortada por cambio de ATN
iec_atn_exp: .res 1       ; nivel de ATN esperado ($80 comando, 0 datos)
data_idx:  .res 1
iec_chan_mode: .res 1     ; 0 = normal (nombre/LOAD), 1 = recibiendo datos de SAVE
iec_save_opening: .res 1  ; $FF tras OPEN de un canal de escritura (espera nombre)
iec_out:   .res 1         ; byte en transmision
iec_send_eoi: .res 1      ; $FF si el byte a enviar lleva EOI
tx_ptr:    .res 2         ; puntero del buffer a transmitir (talker)
tx_len:    .res 2         ; bytes restantes a transmitir (16 bits)
tx_last:   .res 1         ; $FF si este buffer es el ultimo (EOI en su ultimo byte)

; --- codec GCR ---
gcr_src:   .res 2         ; puntero de origen
gcr_dst:   .res 2         ; puntero de destino
gcr_o:     .res 5         ; registro de desplazamiento de 40 bits
gcr_code:  .res 1         ; codigo de 5 bits en proceso
gcr_tmp:   .res 1         ; byte/nibble temporal

; --- controlador de disco (lectura) ---
hdr_track:  .res 1        ; track extraido de la cabecera
hdr_sector: .res 1        ; sector extraido de la cabecera
hdr_error:  .res 1        ; $00 cabecera valida, $FF invalida
sync_error: .res 1        ; $00 SYNC localizado, $FF no encontrado
data_error: .res 1        ; $00 bloque de datos valido, $FF invalido
dsk_count:  .res 1        ; contador de grupos GCR
dsk_csum:   .res 1        ; checksum en calculo
dsk_ptr:    .res 2        ; puntero temporal
want_track: .res 1        ; track buscado / a escribir
want_sector: .res 1       ; sector buscado / a escribir
cur_track:  .res 1        ; pista actual del cabezal (mantenida por software)
want_id1:   .res 1        ; primer caracter del ID del disco
want_id2:   .res 1        ; segundo caracter del ID del disco
fsec_error: .res 1        ; $00 sector localizado y leido, $FF no
dsk_tries:  .res 1        ; intentos restantes en la busqueda
scan_cnt:   .res 2        ; limite de escaneo de SYNC (16 bits)

; --- BAM (mapa de bloques disponibles) ---
bam_track:  .res 1        ; pista para la operacion BAM
bam_sector: .res 1        ; sector para la operacion BAM
bam_result: .res 1        ; $FF libre, $00 ocupado
bam_e:      .res 1        ; offset base de la entrada BAM de la pista
bam_bidx:   .res 1        ; offset del byte de bitmap
bam_total_lo: .res 1      ; total de bloques libres (16 bits)
bam_total_hi: .res 1

; --- directorio ---
dir_found:   .res 1       ; $FF fichero encontrado, $00 no
dir_slotnum: .res 1       ; indice de slot (0..7) en el sector
dir_slot:    .res 1       ; offset del slot dentro de DIR_BUF
dir_ftype:   .res 1       ; byte de tipo de fichero de la entrada
dir_track:   .res 1       ; track del primer bloque del fichero
dir_sector:  .res 1       ; sector del primer bloque del fichero
dir_blocks_lo: .res 1     ; tamano en bloques (16 bits)
dir_blocks_hi: .res 1
dir_link_track:  .res 1   ; track del siguiente sector de directorio
dir_link_sector: .res 1   ; sector del siguiente sector de directorio
dir_chain_track:  .res 1  ; sector de directorio en curso durante el recorrido
dir_chain_sector: .res 1
alloc_track: .res 1       ; track del bloque asignado
alloc_sector: .res 1      ; sector del bloque asignado
alloc_ok:    .res 1       ; $FF si se asigno un bloque, $00 disco lleno
alloc_nsec:  .res 1       ; sectores de la pista en curso

; --- lectura de fichero (cadena de bloques) ---
file_next_track:  .res 1  ; track del siguiente bloque (0 = ultimo)
file_next_sector: .res 1  ; sector del siguiente bloque / offset final
file_nbytes:      .res 1  ; bytes utiles copiados de este bloque
out_ptr:          .res 2  ; puntero de salida del contenido del fichero
in_ptr:           .res 2  ; puntero de entrada (datos a escribir)

; --- escritura de fichero por bus (SAVE) ---
save_active: .res 1        ; $FF si hay un SAVE en curso
save_idx:    .res 1        ; offset de escritura en SAVE_BUF (2..255)
save_cur_track:  .res 1    ; bloque que se esta llenando
save_cur_sector: .res 1
save_first_track:  .res 1  ; primer bloque del fichero (para el directorio)
save_first_sector: .res 1
save_blocks_lo:  .res 1    ; bloques escritos (16 bits)
save_blocks_hi:  .res 1
save_err:    .res 1        ; $FF si el SAVE fallo (disco lleno, etc.)
savetmp:     .res 2        ; contador del hook de prueba de SAVE

; --- canal de estado / error (canal 15) ---
err_code:    .res 1       ; codigo de error actual
err_track:   .res 1       ; track asociado al error
err_sector:  .res 1       ; sector asociado al error
stat_idx:    .res 1       ; indice de escritura en STATUS_BUF
err_tmp:     .res 1       ; temporal
msg_ptr:     .res 2       ; puntero al mensaje de error
cmd_error:   .res 1       ; $FF si el comando tiene error de sintaxis
fmt_track:   .res 1       ; pista actual al formatear el BAM
fmt_rem:     .res 1       ; sectores restantes por marcar en la pista
fmt_cnt:     .res 1       ; bytes de bitmap restantes (3 por pista)
list_ptr:    .res 2       ; puntero de escritura del listado de directorio
list_byte:   .res 1       ; byte en curso (preserva A en list_put)
list_y:      .res 1       ; Y preservado en list_put
cur_lo:      .res 1       ; numero de bloques de la entrada (lo)
cur_hi:      .res 1       ; numero de bloques de la entrada (hi)
list_dig:    .res 1       ; temporal (digitos / longitud / tipo)

.code
; ----------------------------------------------------------------------------
reset:
    sei
    cld
    ldx #$FF
    txs

    lda #VIA2_PB_OUTS
    sta VIA2_DDRB
    lda #$00
    sta VIA2_PA
    sta VIA2_DDRA
    sta VIA2_PB

    lda #VIA1_DDRB_INIT
    sta VIA1_DDRB
    lda #$00
    sta VIA1_DDRA
    sta VIA1_PB

    lda #8
    sta iec_dev
    lda #$00
    sta iec_state
    sta iec_sa
    sta iec_eoi
    sta iec_data_eoi
    sta iec_abort
    sta iec_atn_exp
    sta data_idx
    sta iec_chan_mode
    sta iec_save_opening
    sta save_active
    sta iec_send_eoi

.ifdef PHYS_TEST
    jsr disk_phys_test          ; prueba de la capa fisica (ensamblar con -D PHYS_TEST)
.endif
.ifdef SEEK_TEST
    jsr disk_seek_test          ; prueba del stepper (ensamblar con -D SEEK_TEST)
.endif
.ifdef SECTOR_TEST
    jsr disk_sector_test        ; prueba de lectura de sector (ensamblar con -D SECTOR_TEST)
.endif
.ifdef DIR_TEST
    jsr disk_dir_test           ; prueba del listado de directorio (ensamblar con -D DIR_TEST)
.endif
.ifdef WRITE_TEST
    jsr disk_write_test         ; prueba de escritura de sector (ensamblar con -D WRITE_TEST)
.endif
.ifdef SAVE_TEST
    jsr disk_savetest           ; prueba de escritura de fichero (ensamblar con -D SAVE_TEST)
.endif
.ifdef ADJ_TEST
    jsr disk_adjtest            ; escribe 18/0 y relee 18/1 (comprobar sector adyacente)
.endif
.ifdef MULTI_TEST
    jsr disk_multitest          ; graba 10 ficheros (fuerza 2 sectores de directorio)
.endif

    cli

; ----------------------------------------------------------------------------
;  bucle principal
; ----------------------------------------------------------------------------
mainloop:
    lda VIA1_PB
    and #ATN_IN
    bne @atn
    lda iec_state
    and #ST_TALK
    bne @talk
    lda iec_state
    and #ST_LISTEN
    beq mainloop
    jsr iec_recv_data
    jmp mainloop
@talk:
    jsr iec_talk
    jmp mainloop
@atn:
    jsr iec_atn
    jmp mainloop

; ----------------------------------------------------------------------------
;  iec_recv_data: recibe datos como listener hasta EOI o retorno de ATN
; ----------------------------------------------------------------------------
iec_recv_data:
    lda #$00
    sta iec_atn_exp
    lda iec_chan_mode
    cmp #1
    beq @save_loop              ; recibiendo datos de un SAVE
@loop:
    lda VIA1_PB
    and #ATN_IN
    bne @ret
    jsr iec_recv_byte
    ldx iec_abort
    bne @ret
    ldx data_idx
    sta DATA_BUF,x
    inc data_idx
    lda iec_eoi
    beq @loop
    lda #$FF
    sta iec_data_eoi
@ret:
    rts
@save_loop:
    lda VIA1_PB
    and #ATN_IN
    bne @ret
    jsr iec_recv_byte
    ldx iec_abort
    bne @ret
    lda iec_byte
    jsr file_save_byte          ; cada byte va al fichero en disco
    lda iec_eoi
    beq @save_loop
    lda #$FF
    sta iec_data_eoi
    rts

; ----------------------------------------------------------------------------
;  iec_talk: turnaround y transmision del buffer de prueba como talker
; ----------------------------------------------------------------------------
iec_talk:
    jsr iec_turnaround
    ; elegir el origen de los datos a transmitir segun el nombre recibido
    lda DATA_BUF
    cmp #'$'                    ; LOAD "$": directorio
    bne @notdir
    jsr disk_build_dir          ; genera el listado en LIST_BUF, list_ptr al final
    lda #<LIST_BUF
    sta tx_ptr
    lda #>LIST_BUF
    sta tx_ptr+1
    lda list_ptr                ; longitud = list_ptr - LIST_BUF (16 bits)
    sec
    sbc #<LIST_BUF
    sta tx_len
    lda list_ptr+1
    sbc #>LIST_BUF
    sta tx_len+1
    lda #$FF                    ; el directorio es un unico buffer: EOI al final
    sta tx_last
    jsr iec_send_buffer
    jmp @done
@notdir:
    ; LOAD de un fichero por nombre: localizarlo y transmitir su contenido
    jsr iec_load_file
@done:
    ; canal agotado: limpiar ST_TALK para no retransmitir
    lda iec_state
    and #ST_TALK_CLR
    sta iec_state
    rts

;  iec_turnaround: la 1541 toma el rol de talker (asierta CLK, libera DATA) y
;  espera a que el host se vuelva listener (asierte DATA).
iec_turnaround:
    lda VIA1_PB
    ora #CLK_OUT
    sta VIA1_PB
    lda VIA1_PB
    and #DATA_OUT_CLR
    sta VIA1_PB
@w_listener:
    lda VIA1_PB
    and #DATA_IN
    beq @w_listener
    rts

;  iec_talk_send: turnaround y transmision del buffer ya preparado en tx_ptr/tx_len.
;  Punto de entrada para verificar el mecanismo de envio de forma aislada.
iec_talk_send:
    jsr iec_turnaround
    jsr iec_send_buffer
    rts

;  iec_send_buffer: transmite tx_len bytes (16 bits) desde (tx_ptr) como talker.
;  Si tx_last != 0, el ultimo byte del buffer lleva EOI; si tx_last == 0, ningun
;  byte lleva EOI (para bloques intermedios de un fichero). Asume turnaround hecho.
iec_send_buffer:
    lda tx_len
    ora tx_len+1
    beq @done                   ; nada que transmitir
@sloop:
    lda tx_last                 ; EOI solo si es el ultimo buffer y queda 1 byte
    beq @no_eoi
    lda tx_len+1
    bne @no_eoi
    lda tx_len
    cmp #1
    bne @no_eoi
    lda #$FF
    bne @set_eoi                ; siempre toma (A != 0)
@no_eoi:
    lda #$00
@set_eoi:
    sta iec_send_eoi
    ldy #$00
    lda (tx_ptr),y
    sta iec_out
    jsr iec_send_byte
    inc tx_ptr                  ; avanzar puntero
    bne @nohi
    inc tx_ptr+1
@nohi:
    lda tx_len                  ; decrementar contador de 16 bits
    sec
    sbc #1
    sta tx_len
    lda tx_len+1
    sbc #0
    sta tx_len+1
    lda tx_len
    ora tx_len+1
    bne @sloop
@done:
    rts

;  iec_copy_name: copia el nombre recibido (DATA_BUF, data_idx bytes) a NAME_BUF,
;  rellenando con $A0 hasta 16 bytes. Compartida por LOAD y SAVE.
iec_copy_name:
    ldx #$00
@cn:
    cpx #16
    beq @done
    cpx data_idx
    bcc @char
    lda #$A0
    bne @put                    ; siempre ($A0 != 0)
@char:
    lda DATA_BUF,x
@put:
    sta NAME_BUF,x
    inx
    bne @cn                     ; siempre (x < 16)
@done:
    rts

;  iec_load_file: localiza el fichero cuyo nombre se recibio (DATA_BUF, data_idx
;  bytes) y transmite su contenido por el bus, bloque a bloque, siguiendo la
;  cadena de sectores. El ultimo byte del ultimo bloque lleva EOI. Si el fichero
;  no existe, no transmite nada (el host obtiene FILE NOT FOUND por tiempo).
iec_load_file:
    jsr iec_copy_name           ; nombre recibido (DATA_BUF) -> NAME_BUF, relleno $A0
    jsr dir_find_chain          ; busca en la cadena de sectores de directorio
    lda dir_found
    beq @notfound
    ; transmitir la cadena de bloques desde dir_track/dir_sector
    lda dir_track
    sta want_track
    lda dir_sector
    sta want_sector
@blockloop:
    jsr disk_read_sector_hw     ; bloque -> DATA_DEC_BUF+1
    lda fsec_error
    bne @notfound
    lda DATA_DEC_BUF+1          ; enlace track (0 = ultimo bloque)
    sta file_next_track
    lda DATA_DEC_BUF+2          ; enlace sector / offset final
    sta file_next_sector
    lda file_next_track
    bne @full
    ; ultimo bloque: bytes utiles = offset final - 1
    lda file_next_sector
    sec
    sbc #1
    sta file_nbytes
    jmp @emit
@full:
    lda #254                    ; bloque completo: 254 bytes de datos
    sta file_nbytes
@emit:
    lda #<(DATA_DEC_BUF+3)       ; datos del bloque: desde +3 (tras el enlace)
    sta tx_ptr
    lda #>(DATA_DEC_BUF+3)
    sta tx_ptr+1
    lda file_nbytes
    sta tx_len
    lda #$00
    sta tx_len+1
    lda file_next_track         ; EOI solo en el ultimo bloque
    bne @notlast
    lda #$FF
    sta tx_last
    jsr iec_send_buffer
    rts                         ; fichero completo
@notlast:
    lda #$00
    sta tx_last
    jsr iec_send_buffer
    lda file_next_track         ; seguir la cadena
    sta want_track
    lda file_next_sector
    sta want_sector
    jmp @blockloop
@notfound:
    rts

; ----------------------------------------------------------------------------
;  iec_send_byte: envia iec_out como talker (LSB primero). Si iec_send_eoi!=0,
;  realiza el handshake de EOI antes de los bits.
; ----------------------------------------------------------------------------
iec_send_byte:
    ; talker listo: liberar CLK
    lda VIA1_PB
    and #CLK_OUT_CLR
    sta VIA1_PB
    ; esperar listener listo: DATA liberada
@w_drel:
    lda VIA1_PB
    and #DATA_IN
    bne @w_drel
    ; EOI?
    lda iec_send_eoi
    beq @bits
    ; esperar el pulso de reconocimiento del listener (DATA asserted y liberada)
@w_eoi_a:
    lda VIA1_PB
    and #DATA_IN
    beq @w_eoi_a
@w_eoi_r:
    lda VIA1_PB
    and #DATA_IN
    bne @w_eoi_r
@bits:
    ; non-EOI: asertar CLK un periodo para indicar el inicio (el listener lo espera
    ; como senal de arranque antes de leer los bits).
    lda VIA1_PB
    ora #CLK_OUT
    sta VIA1_PB
    ldy #BIT_DELAY
@d0:
    dey
    bne @d0
    ldx #8
@bit:
    lsr iec_out             ; bit logico (LSB) al carry
    bcs @one
    ; logico 0 -> asertir DATA
    lda VIA1_PB
    ora #DATA_OUT
    sta VIA1_PB
    jmp @strobe
@one:
    ; logico 1 -> liberar DATA
    lda VIA1_PB
    and #DATA_OUT_CLR
    sta VIA1_PB
@strobe:
    ; liberar CLK: senala que el dato es valido (el listener lee en este flanco)
    lda VIA1_PB
    and #CLK_OUT_CLR
    sta VIA1_PB
    ldy #BIT_DELAY
@d1:
    dey
    bne @d1
    ; asertir CLK: dato no valido, prepara el siguiente bit
    lda VIA1_PB
    ora #CLK_OUT
    sta VIA1_PB
    ldy #BIT_DELAY
@d2:
    dey
    bne @d2
    dex
    bne @bit
    ; ceder la linea de datos al listener
    lda VIA1_PB
    and #DATA_OUT_CLR
    sta VIA1_PB
    ; esperar acknowledge de frame: el listener asierta DATA
@w_ack:
    lda VIA1_PB
    and #DATA_IN
    beq @w_ack
    ; reposo: asertir CLK
    lda VIA1_PB
    ora #CLK_OUT
    sta VIA1_PB
    rts

; ----------------------------------------------------------------------------
;  iec_atn: atiende comandos mientras ATN este asserted
; ----------------------------------------------------------------------------
iec_atn:
    lda #ATN_IN
    sta iec_atn_exp
    ; volver a rol listener: liberar CLK (por si veniamos de talker) y asertir DATA
    lda VIA1_PB
    and #CLK_OUT_CLR
    sta VIA1_PB
    ; tomar control de DATA por software: asertar DATA_OUT y poner ATNA=1 para
    ; cancelar la asercion automatica de DATA que el hardware hace bajo ATN. Sin
    ; esto, liberar DATA_OUT mas adelante no libera la linea (el hardware la sigue
    ; forzando) y el handshake con el controlador se bloquea.
    lda VIA1_PB
    ora #(DATA_OUT | ATNA)
    sta VIA1_PB
@cmdloop:
    lda VIA1_PB
    and #ATN_IN
    bne @cl_recv
    jmp @done
@cl_recv:
    jsr iec_recv_byte
    lda iec_abort
    beq @cl_proc
    jmp @done
@cl_proc:
    lda iec_byte
    sta iec_cmd

    cmp #$3F
    bne @not_unlisten
    lda iec_state
    and #ST_LISTEN_CLR
    sta iec_state
    jmp @cmdloop
@not_unlisten:
    cmp #$5F
    bne @not_untalk
    lda iec_state
    and #ST_TALK_CLR
    sta iec_state
    jmp @cmdloop
@not_untalk:
    cmp #$60
    bcs @secondary

    lda iec_cmd
    and #$E0
    cmp #$20
    bne @check_talk
    lda iec_cmd
    and #$1F
    cmp iec_dev
    bne @cmdloop
    lda iec_state
    ora #ST_LISTEN
    sta iec_state
    jmp @cmdloop
@check_talk:
    cmp #$40
    bne @cmdloop
    lda iec_cmd
    and #$1F
    cmp iec_dev
    bne @cmdloop
    lda iec_state
    ora #ST_TALK
    sta iec_state
    jmp @cmdloop

@secondary:
    lda iec_state
    and #(ST_LISTEN | ST_TALK)
    beq @cmdloop
    lda iec_cmd
    and #$0F
    sta iec_sa
    lda iec_cmd
    and #$F0
    cmp #$F0
    beq @sec_open
    cmp #$60
    beq @sec_data
    cmp #$E0
    beq @sec_close
    jmp @cmdloop
@sec_open:
    lda iec_sa                  ; canal 0 = LOAD; canal != 0 = posible SAVE
    bne @so_go
    lda #$00                    ; canal 0: nombre nuevo, reiniciar el indice de
    sta data_idx                ; recepcion. Sin esto, en una peticion posterior
    sta iec_chan_mode           ; el nombre se acumula mal alineado en DATA_BUF.
    jmp @cmdloop
@so_go:
    lda #$FF
    sta iec_save_opening        ; el nombre llega ahora; abrir al ver el DATA
    lda #$00
    sta data_idx
    sta iec_chan_mode
    jmp @cmdloop
@sec_data:
    lda iec_sa
    bne @sd_go
    jmp @cmdloop                ; canal 0 (LOAD lo gestiona iec_talk)
@sd_go:
    lda iec_save_opening
    bne @sd_open                ; veniamos de OPEN: abrir el fichero
    lda save_active
    bne @sd_mode                ; SAVE ya en curso
    jmp @cmdloop                ; ni OPEN ni SAVE: datos normales (DATA_BUF)
@sd_open:
    jsr iec_copy_name           ; nombre recibido -> NAME_BUF
    jsr file_save_open          ; asigna el primer bloque
    lda #$00
    sta iec_save_opening
@sd_mode:
    lda #1
    sta iec_chan_mode           ; los datos que siguen -> file_save_byte
    jmp @cmdloop
@sec_close:
    lda iec_sa
    bne @sc_go
    jmp @cmdloop
@sc_go:
    jsr file_save_close         ; ultimo sector + entrada de directorio
    lda #$00
    sta iec_chan_mode
    sta iec_save_opening
    jmp @cmdloop
@done:
    ; ATN liberado: devolver el control de DATA al hardware (ATNA=0) para que la
    ; asercion automatica vuelva a operar en el proximo ATN.
    lda VIA1_PB
    and #ATNA_CLR
    sta VIA1_PB
    rts

; ----------------------------------------------------------------------------
;  iec_recv_byte: recibe un byte como listener (LSB primero) con deteccion de
;  EOI. Devuelve A=byte; fija iec_eoi y/o iec_abort segun corresponda.
; ----------------------------------------------------------------------------
iec_recv_byte:
    lda #$00
    sta iec_abort
@w_clkrel:
    lda VIA1_PB
    and #ATN_IN
    cmp iec_atn_exp
    beq @check_clk
    jmp @abort
@check_clk:
    lda VIA1_PB
    and #CLK_IN
    bne @w_clkrel
    ; listener listo: liberar DATA
    lda VIA1_PB
    and #DATA_OUT_CLR
    sta VIA1_PB

    lda #$00
    sta iec_byte
    sta iec_eoi

    ; primer bit con timeout (deteccion de EOI)
    ldx #EOI_TO
@eoi_wait:
    lda VIA1_PB
    and #CLK_IN
    bne @first_clk
    dex
    bne @eoi_wait
    ; timeout -> EOI
    lda #$FF
    sta iec_eoi
    lda VIA1_PB
    ora #DATA_OUT
    sta VIA1_PB
    ldx #EOI_PULSE
@eoi_pulse:
    dex
    bne @eoi_pulse
    lda VIA1_PB
    and #DATA_OUT_CLR
    sta VIA1_PB
@w_first:
    lda VIA1_PB
    and #CLK_IN
    beq @w_first

@first_clk:
    ; el talker libera CLK cuando el dato es valido y lo asierta para preparar el
    ; siguiente bit. Por tanto se lee DATA en el flanco de CLK liberado, no asertado.
    ldx #8                  ; 8 bits, LSB primero
@bit:
@w_clk_rel:
    lda VIA1_PB
    and #CLK_IN
    bne @w_clk_rel          ; esperar CLK liberado (CLK_IN=0): dato valido (intacto)
    lda VIA1_PB
    and #DATA_IN
    eor #DATA_IN
    lsr a
    ror iec_byte
@w_clk_ass:
    lda VIA1_PB
    and #CLK_IN
    bne @ass_ok             ; CLK asertado: siguiente bit (camino rapido, intacto)
    lda VIA1_PB             ; aun liberado: vigilar ATN durante la espera (el HW real
    and #ATN_IN             ; lo hace por IRQ). Un comando entrante aborta la recepcion
    cmp iec_atn_exp
    bne @abort
    beq @w_clk_ass
@ass_ok:
    dex
    bne @bit

    lda VIA1_PB
    ora #DATA_OUT
    sta VIA1_PB
    lda iec_byte
    rts

@abort:
    lda #$FF
    sta iec_abort
    rts

; ----------------------------------------------------------------------------
;  Codec GCR (Group Coded Recording), formato publico de la 1541.
;  Codificacion 4-a-5 bits: 4 bytes de datos <-> 5 bytes GCR. El flujo de 40
;  bits se construye MSB primero. Tablas al final (RODATA).
; ----------------------------------------------------------------------------
;  gcr_encode: lee 4 bytes en (gcr_src), escribe 5 bytes GCR en (gcr_dst).
gcr_encode:
    lda #$00
    sta gcr_o+0
    sta gcr_o+1
    sta gcr_o+2
    sta gcr_o+3
    sta gcr_o+4
    ldy #0                  ; indice de byte de entrada (0..3)
@byteloop:
    lda (gcr_src),y
    sta gcr_tmp
    lsr a
    lsr a
    lsr a
    lsr a                   ; nibble alto
    jsr gcr_emit_nibble
    lda gcr_tmp
    and #$0F                ; nibble bajo
    jsr gcr_emit_nibble
    iny
    cpy #4
    bne @byteloop
    ; copiar el registro a (gcr_dst)
    ldy #4
@copy:
    lda gcr_o,y
    sta (gcr_dst),y
    dey
    bpl @copy
    rts

;  gcr_emit_nibble: A = nibble (0..15). Mete su codigo de 5 bits (MSB primero)
;  en el registro de desplazamiento gcr_o.
gcr_emit_nibble:
    tax
    lda gcr_enc_tab,x
    sta gcr_code
    asl gcr_code
    asl gcr_code
    asl gcr_code            ; alinear bit4 del codigo en bit7
    ldx #5
@bits:
    asl gcr_code            ; saca el bit (MSB primero) al carry
    rol gcr_o+4             ; desplaza el registro de 40 bits a la izquierda
    rol gcr_o+3
    rol gcr_o+2
    rol gcr_o+1
    rol gcr_o+0
    dex
    bne @bits
    rts

;  gcr_decode: lee 5 bytes GCR en (gcr_src), escribe 4 bytes en (gcr_dst).
gcr_decode:
    ldy #4
@load:
    lda (gcr_src),y
    sta gcr_o,y
    dey
    bpl @load
    ldy #0                  ; indice de byte de salida (0..3)
@byteout:
    jsr gcr_get_nibble      ; nibble alto
    asl a
    asl a
    asl a
    asl a
    sta gcr_tmp
    jsr gcr_get_nibble      ; nibble bajo
    ora gcr_tmp
    sta (gcr_dst),y
    iny
    cpy #4
    bne @byteout
    rts

;  gcr_get_nibble: extrae 5 bits (MSB primero) del registro y los traduce a un
;  nibble via la tabla inversa. Devuelve el nibble en A ($FF si codigo invalido).
gcr_get_nibble:
    lda #$00
    sta gcr_code
    ldx #5
@bits:
    asl gcr_o+4
    rol gcr_o+3
    rol gcr_o+2
    rol gcr_o+1
    rol gcr_o+0             ; bit7 de gcr_o+0 (MSB del flujo) -> carry
    rol gcr_code            ; acumula
    dex
    bne @bits
    ldx gcr_code
    lda gcr_dec_tab,x
    rts

; ----------------------------------------------------------------------------
;  Controlador de disco (capa fisica, hardware VIA2).
;  Interfaz obligatoria del hardware: el byte-ready del cabezal esta cableado a la
;  entrada SO del 6502 (flag V), y el flujo GCR llega ya alineado por VIA2_PA. El
;  SYNC es VIA2_PB bit 7, activo en bajo. Verificable solo en VICE (py65 no emula
;  la VIA2 ni el flujo del disco).
; ----------------------------------------------------------------------------
;  disk_motor_on: enciende motor (bit 2) y LED (bit 3) y espera el arranque.
disk_motor_on:
    lda VIA2_PB
    ora #(MOTOR_BIT | LED_BIT)
    sta VIA2_PB
    ldx #$20
@s1:
    ldy #$00
@s2:
    dey
    bne @s2
    dex
    bne @s1
    rts

;  disk_wait_sync: espera el SYNC (VIA2_PB bit 7 = 0) con timeout de 16 bits.
;  Devuelve carry=0 si lo localizo, carry=1 si agoto el tiempo.
disk_wait_sync:
    ldx #$00
    ldy #$00
@w:
    bit VIA2_PB
    bpl @ok                 ; bit 7 = 0 -> SYNC
    iny
    bne @w
    inx
    bne @w
    sec                     ; timeout
    rts
@ok:
    clc
    rts

;  disk_read10: lee 10 bytes GCR del cabezal a RAW_BUF con el handshake SO.
disk_read10:
    ldy #$00
    clv
@rd:
    bvc @rd                 ; esperar byte listo (V = 1)
    clv
    lda VIA2_PA
    sta RAW_BUF,y
    iny
    cpy #10
    bne @rd
    rts

;  disk_read10b: igual que disk_read10 pero al segundo buffer RAW_BUF2.
disk_read10b:
    ldy #$00
    clv
@rd:
    bvc @rd
    clv
    lda VIA2_PA
    sta RAW_BUF2,y
    iny
    cpy #10
    bne @rd
    rts

;  disk_read_raw: prueba; motor, SYNC y lee RAW_LEN bytes crudos a RAW_BUF.
disk_read_raw:
    jsr disk_motor_on
    jsr disk_wait_sync
    bcc @go
    lda #$FF
    sta sync_error
    rts
@go:
    lda #$00
    sta sync_error
    ldy #$00
    clv
@rd:
    bvc @rd
    clv
    lda VIA2_PA
    sta RAW_BUF,y
    iny
    cpy #RAW_LEN
    bne @rd
    rts

;  disk_phys_test: prueba de extremo a extremo de la lectura fisica. Enciende el
;  motor, lee la cabecera y el bloque de datos del primer sector bajo el cabezal
;  (seguidos, sin decodificar en medio, como la 1541 real), y luego decodifica
;  ambos. Deja hdr_track/hdr_sector/hdr_error de la cabecera y la marca del bloque
;  en DATA_DEC_BUF+0 ($07 esperado). Solo para verificacion en VICE.
disk_phys_test:
    jsr disk_motor_on
    jsr disk_wait_sync          ; SYNC de la cabecera
    jsr disk_read10             ; cabecera -> RAW_BUF (sin decodificar aun)
    jsr disk_wait_sync          ; SYNC del bloque de datos (inmediato)
    jsr disk_read10b            ; bloque de datos -> RAW_BUF2
    lda #<RAW_BUF
    sta gcr_src
    lda #>RAW_BUF
    sta gcr_src+1
    jsr disk_read_header        ; -> hdr_track, hdr_sector, hdr_error
    lda #<RAW_BUF2
    sta gcr_src
    lda #>RAW_BUF2
    sta gcr_src+1
    lda #<DATA_DEC_BUF
    sta gcr_dst
    lda #>DATA_DEC_BUF
    sta gcr_dst+1
    jsr gcr_decode              ; DATA_DEC_BUF[0] = marca de datos
    rts

;  Stepper: los bits 0-1 de VIA2_PB forman un contador binario de 4 fases (manual
;  de servicio 1540/1541, STP0/STP1). Incrementar o decrementar ese contador mueve
;  el cabezal medio paso. Una pista son dos medios pasos (double-stepping: cabezal
;  de 48 tpi sobre mecanismo de 84 pistas). La direccion fisica de cada sentido se
;  determina por observacion en VICE. Se preservan los demas bits de PB.
disk_step_in:
    lda VIA2_PB
    tax
    and #STEP_MASK
    clc
    adc #1
    and #STEP_MASK              ; (fase + 1) mod 4
    sta gcr_tmp
    txa
    and #<(~STEP_MASK)          ; PB sin los bits de fase
    ora gcr_tmp
    sta VIA2_PB
    rts

disk_step_out:
    lda VIA2_PB
    tax
    and #STEP_MASK
    sec
    sbc #1
    and #STEP_MASK              ; (fase - 1) mod 4
    sta gcr_tmp
    txa
    and #<(~STEP_MASK)
    ora gcr_tmp
    sta VIA2_PB
    rts

;  disk_step_delay: retardo de asentamiento del cabezal tras un medio paso.
disk_step_delay:
    ldx #$10
@d1:
    ldy #$00
@d2:
    dey
    bne @d2
    dex
    bne @d1
    rts

;  disk_find_current_track: lee una cabecera bajo el cabezal y fija cur_track.
disk_find_current_track:
    jsr disk_motor_on
    jsr disk_read_hdr_retry
    lda hdr_error                ; sin cabecera valida (p.ej. sin disco): no hay
    bne @keep                    ; dato fiable de posicion, conservar cur_track
    lda hdr_track                ; tal cual estaba, en vez de "olvidar" donde
    sta cur_track                ; esta el cabezal y reseekear a ciegas cada vez
@keep:
    rts

;  disk_read_hdr_retry: lee una cabecera valida reintentando hasta 24 veces. Tras
;  mover el cabezal la primera cabecera suele estar corrupta, asi que se reintenta
;  hasta que disk_read_header de hdr_error=$00 (o se agoten los intentos).
disk_read_hdr_retry:
    ldx #24
@try:
    txa
    pha
    jsr disk_wait_sync
    bcs @nosync         ; timeout: no hay SYNC, no leer (disk_read10 no tiene
                         ; limite de tiempo y se quedaria esperando para siempre)
    jsr disk_read10
    lda #<RAW_BUF
    sta gcr_src
    lda #>RAW_BUF
    sta gcr_src+1
    jsr disk_read_header
    jmp @chk
@nosync:
    lda #$FF
    sta hdr_error
@chk:
    pla
    tax
    lda hdr_error
    beq @ok
    dex
    bne @try
@ok:
    rts

;  disk_read_block_gcr: lee los 325 bytes GCR del bloque de datos a GCR_BLK con el
;  handshake SO. Se leen en dos tramos (256 + 69) para usar direccionamiento
;  absoluto indexado; la transicion entre tramos cuesta pocos ciclos, muy por
;  debajo del tiempo de un byte, asi que no se pierde ninguno.
disk_read_block_gcr:
    ldy #$00
    clv
@r1:
    bvc @r1
    clv
    lda VIA2_PA
    sta GCR_BLK,y
    iny
    bne @r1                     ; 256 bytes ($00..$FF)
    ldy #$00
@r2:
    bvc @r2
    clv
    lda VIA2_PA
    sta GCR_BLK+256,y
    iny
    cpy #(325-256)              ; 69 bytes restantes
    bne @r2
    rts

;  disk_find_sector_hw: con el cabezal ya en la pista (seek hecho), busca el sector
;  want_sector recorriendo el anillo. En cada vuelta lee la cabecera y el bloque de
;  datos SEGUIDOS (sin decodificar en medio, para no perder el bloque), y solo
;  despues decodifica la cabecera; si es el sector buscado, decodifica y valida el
;  bloque. fsec_error = $00 exito (256 datos en DATA_DEC_BUF+1), $FF fallo.
disk_find_sector_hw:
    lda #MAX_TRIES
    sta dsk_tries
@try:
    jsr disk_wait_sync          ; SYNC (de cabecera o de bloque de datos)
    bcs @fail
    jsr disk_read10             ; 10 bytes -> RAW_BUF
    lda RAW_BUF
    cmp #$52                    ; primer byte GCR de la marca de cabecera ($08)
    bne @next                   ; $53 seria un bloque de datos: ignorarlo
    ; es una cabecera: leer su bloque de datos enseguida (sin decodificar en medio)
    jsr disk_wait_sync          ; SYNC del bloque de datos
    bcs @fail
    jsr disk_read_block_gcr     ; bloque -> GCR_BLK
    ; ahora decodificar la cabecera y comprobar si es la buscada
    lda #<RAW_BUF
    sta gcr_src
    lda #>RAW_BUF
    sta gcr_src+1
    jsr disk_read_header
    lda hdr_error
    bne @next
    lda hdr_track
    cmp want_track
    bne @next
    lda hdr_sector
    cmp want_sector
    bne @next
    ; sector encontrado: decodificar el bloque ya leido en GCR_BLK
    lda #<GCR_BLK
    sta gcr_src
    lda #>GCR_BLK
    sta gcr_src+1
    jsr disk_read_data          ; -> DATA_DEC_BUF, data_error
    lda data_error
    bne @fail
    lda #$00
    sta fsec_error
    rts
@next:
    dec dsk_tries
    bne @try
@fail:
    lda #$FF
    sta fsec_error
    rts

;  disk_read_sector_hw: lee el sector want_track/want_sector del disco fisico.
;  Posiciona el cabezal (seek) y busca el sector. Resultado: 256 bytes en
;  DATA_DEC_BUF+1, fsec_error = $00 exito / $FF fallo.
disk_read_sector_hw:
    jsr disk_find_current_track ; motor on + cur_track segun la cabecera bajo el cabezal
    jsr disk_seek               ; mover a want_track
    jsr disk_find_sector_hw     ; localizar want_sector y leer su bloque
    rts

; ----------------------------------------------------------------------------
;  disk_write_block_gcr: escribe el bloque de datos en el disco. Asume que GCR_BLK
;  tiene los 325 bytes GCR ya codificados (disk_build_data con gcr_dst=GCR_BLK) y
;  que el cabezal esta posicionado en el header gap (justo tras la cabecera). Pone
;  la cabeza en modo escritura (PCR CB2=0) con el puerto A de la VIA2 como salida,
;  graba un SYNC de NSYNC bytes $FF y a continuacion los 325 bytes GCR, y vuelve a
;  modo lectura. La escritura es "in place" sobre el bloque de datos (no reescribe
;  la cabecera).
;
;  Sincronizacion (derivada del hardware, Nivel A, simetrica a la capa de lectura):
;  el byte-ready del controlador esta cableado a la entrada SO del 6502, asi que el
;  flag V es la unica forma de saber cuando el latch de salida admite el siguiente
;  byte, igual que en lectura es la unica forma de saber que hay byte disponible.
;  La ventana entre el flanco de byte-ready y el inicio de la serializacion del
;  byte siguiente es de pocos ciclos: no cabe un LDA dentro de ella. Por eso el
;  byte se deja precargado en A ANTES de esperar el flanco, y tras el flanco solo
;  resta CLV + STA. Es el reflejo del patron de lectura (alli CLV/BVC/LDA, aqui
;  LDA/BVC/CLV/STA). Por el mismo presupuesto de ciclos, el recorrido del buffer
;  usa direccionamiento indexado simple en tramos que no cruzan pagina; GCR_BLK
;  ocupa 325 bytes (mas de una pagina), de modo que se recorre como dos tramos
;  contiguos: el primero hasta el fin de pagina, el segundo el resto.
; ----------------------------------------------------------------------------
.proc disk_write_block_gcr
    lda #$FF
    sta VIA2_DDRA               ; puerto A = salida hacia el cabezal
    lda #PCR_WRITE
    sta VIA2_PCR                ; cabeza en escritura (PCR antes de cargar el latch)
    lda #$FF
    sta VIA2_PA                 ; latch = $FF, que sirve de marca SYNC
    clv
    ldx #NSYNC                  ; el latch queda en $FF: solo contamos los byte-ready
sync_loop:
    bvc sync_loop
    clv
    dex
    bne sync_loop
    ; recorrido del buffer GCR en dos tramos contiguos, con el byte precargado.
    ldy #$00                    ; tramo 1: GCR_BLK[0..255]
tramo1:
    lda GCR_BLK,y               ; byte siguiente listo en A
    bvc *                       ; bloquear hasta que el controlador pida byte
    clv                         ; consumir el flanco
    sta VIA2_PA                 ; entregar el byte dentro de la ventana
    iny
    bne tramo1
    ldy #$00                    ; tramo 2: GCR_BLK[256..324] (325-256 = 69 bytes)
tramo2:
    lda GCR_BLK+256,y
    bvc *
    clv
    sta VIA2_PA
    iny
    cpy #(325-256)
    bne tramo2
    bvc *                       ; dejar que el ultimo byte termine de serializarse
    clv
    lda #PCR_READ
    sta VIA2_PCR                ; restaurar modo lectura sin demora intermedia
    lda #$00
    sta VIA2_DDRA               ; puerto A = entrada
    rts
.endproc

; ----------------------------------------------------------------------------
;  disk_write_sector_hw: escribe el bloque want_track/want_sector. Asume GCR_BLK
;  ya codificado (disk_build_data con gcr_dst=GCR_BLK). Posiciona el cabezal, lee
;  una cabecera para capturar los ID del disco, genera la plantilla GCR de la
;  cabecera buscada y localiza el sector comparando los 5 primeros bytes GCR en
;  crudo (sin decodificar: decodificar perderia la posicion antes del gap). Al
;  encontrarlo salta el header gap y graba el bloque. fsec_error = $00 / $FF.
; ----------------------------------------------------------------------------
disk_write_sector_hw:
    jsr disk_find_current_track
    jsr disk_seek
    jsr disk_set_speed_zone     ; bitrate segun la zona de want_track (clave al escribir)
    ; 1) leer una cabecera valida para capturar los ID del disco
    lda #MAX_TRIES
    sta dsk_tries
@idtry:
    jsr disk_wait_sync
    bcs @fail
    jsr disk_read10
    lda RAW_BUF
    cmp #$52                    ; marca de cabecera en GCR
    bne @idnext
    lda #<RAW_BUF
    sta gcr_src
    lda #>RAW_BUF
    sta gcr_src+1
    jsr disk_read_header
    lda hdr_error
    beq @gotid
@idnext:
    dec dsk_tries
    bne @idtry
    beq @fail
@gotid:
    lda HEADER_BUF+5            ; id1
    sta want_id1
    lda HEADER_BUF+4            ; id2
    sta want_id2
    ; 2) plantilla GCR de la cabecera buscada
    lda #<HDR_TPL
    sta gcr_dst
    lda #>HDR_TPL
    sta gcr_dst+1
    jsr disk_build_header       ; -> 10 bytes GCR en HDR_TPL
    ; 3) localizar la cabecera de want_sector comparando GCR crudo
    lda #MAX_TRIES
    sta dsk_tries
@try:
    jsr disk_wait_sync
    bcs @fail
    jsr disk_read10             ; 10 bytes GCR -> RAW_BUF
    ldx #5                      ; comparar marca, csum, sector, track (5 bytes GCR)
@cmp:
    lda RAW_BUF-1,x
    cmp HDR_TPL-1,x
    bne @next
    dex
    bne @cmp
    ; coincide: saltar el header gap y escribir (seguimos en modo lectura)
    ldx #WGAP_BYTES
@gap:
    bvc @gap
    clv
    dex
    bne @gap
    jsr disk_write_block_gcr
    lda #$00
    sta fsec_error
    rts
@next:
    dec dsk_tries
    bne @try
@fail:
    lda #$FF
    sta fsec_error
    rts

; ----------------------------------------------------------------------------
;  Orquestador de SAVE: graba un fichero PRG a partir del flujo de bytes del bus.
;  Por la estrechez de RAM (GCR_BLK solapa BAM_BUF) la BAM se relee de 18/0 y se
;  reescribe en cada asignacion, en vez de mantenerse en RAM. El sector en
;  construccion vive en SAVE_BUF; al llenarse o al cerrar se codifica
;  (disk_build_data) y se graba (disk_write_sector_hw).
; ----------------------------------------------------------------------------
;  save_write_dec_to: codifica DATA_DEC_BUF y lo graba en want_track/want_sector.
save_write_dec_to:
    lda #<GCR_BLK
    sta gcr_dst
    lda #>GCR_BLK
    sta gcr_dst+1
    jsr disk_build_data
    jsr disk_write_sector_hw
    rts

;  save_alloc_block: lee la BAM (18/0), asigna el primer bloque libre desde la
;  pista 1 y reescribe la BAM. Devuelve alloc_track/sector y alloc_ok.
;  save_bam_load: lee la BAM (18/0) a BAM_BUF una sola vez al iniciar el SAVE.
save_bam_load:
    lda #18
    sta want_track
    lda #0
    sta want_sector
    jsr disk_read_sector_hw     ; BAM -> DATA_DEC_BUF+1..+256
    ldx #$00
@cp:
    lda DATA_DEC_BUF+1,x
    sta BAM_BUF,x
    inx
    bne @cp
    rts

;  save_bam_flush: graba la BAM (BAM_BUF) en 18/0 una sola vez al cerrar el SAVE.
;  GCR_BLK ya no solapa BAM_BUF, asi que la BAM puede vivir en RAM todo el SAVE.
save_bam_flush:
    ldx #$00
@cp:
    lda BAM_BUF,x
    sta DATA_DEC_BUF+1,x
    inx
    bne @cp
    lda #18
    sta want_track
    lda #0
    sta want_sector
    jsr save_write_dec_to
    rts

;  save_alloc_block: asigna el siguiente bloque desde la pista 1 sobre la BAM que ya
;  esta en RAM (no toca el disco). Devuelve alloc_track/sector y alloc_ok.
save_alloc_block:
    lda #1
    sta bam_track
    jsr bam_alloc_next          ; -> alloc_track/sector/ok (modifica BAM_BUF)
    rts

;  save_write_cur: graba SAVE_BUF (256 bytes) en save_cur_track/sector.
save_write_cur:
    ldx #$00
@cp:
    lda SAVE_BUF,x
    sta DATA_DEC_BUF+1,x
    inx
    bne @cp
    lda save_cur_track
    sta want_track
    lda save_cur_sector
    sta want_sector
    jsr save_write_dec_to
    rts

;  file_save_open: inicia un SAVE. NAME_BUF debe tener el nombre. save_err = $FF
;  si no se pudo asignar el primer bloque (disco lleno).
file_save_open:
    lda #$00
    sta save_blocks_lo
    sta save_blocks_hi
    sta save_err
    jsr save_bam_load           ; BAM a RAM una sola vez
    jsr save_alloc_block
    lda alloc_ok
    beq @full
    lda alloc_track
    sta save_cur_track
    sta save_first_track
    lda alloc_sector
    sta save_cur_sector
    sta save_first_sector
    inc save_blocks_lo
    lda #2
    sta save_idx
    lda #$FF
    sta save_active
    rts
@full:
    lda #$FF
    sta save_err
    lda #$00
    sta save_active
    rts

;  file_save_byte: anade el byte en A al sector en construccion. Al llenarlo (256)
;  asigna el siguiente bloque, fija el enlace y graba el sector actual.
file_save_byte:
    ldx save_idx
    sta SAVE_BUF,x
    inc save_idx
    bne @ret
    jsr save_alloc_block
    lda alloc_ok
    bne @ok
    lda #$FF
    sta save_err
    rts
@ok:
    lda alloc_track
    sta SAVE_BUF+0
    lda alloc_sector
    sta SAVE_BUF+1
    jsr save_write_cur
    lda alloc_track
    sta save_cur_track
    lda alloc_sector
    sta save_cur_sector
    inc save_blocks_lo
    bne @noc
    inc save_blocks_hi
@noc:
    lda #2
    sta save_idx
@ret:
    rts

;  dir_alloc_sector: asigna un sector libre en la PISTA 18 para el directorio
;  (bam_alloc_next la salta por reservarla) sobre la BAM que ya esta en RAM.
;  Devuelve alloc_sector y alloc_ok.
dir_alloc_sector:
    lda #18
    sta bam_track
    jsr disk_sectors_per_track  ; A = sectores de la pista 18
    sta alloc_nsec
    lda #$00
    sta bam_sector
@sl:
    lda bam_sector
    cmp alloc_nsec
    bcs @full
    jsr bam_is_free
    lda bam_result
    bne @found
    inc bam_sector
    jmp @sl
@found:
    jsr bam_alloc               ; marca 18/bam_sector ocupado en BAM_BUF
    lda bam_sector
    sta alloc_sector
    lda #$FF
    sta alloc_ok
    rts
@full:
    lda #$00
    sta alloc_ok
    rts

;  dir_find_chain: recorre la cadena de sectores de directorio (18/1, enlace, ...)
;  buscando el nombre en NAME_BUF. dir_found = $FF con dir_ftype/track/sector/blocks.
dir_find_chain:
    lda #18
    sta dir_chain_track
    lda #1
    sta dir_chain_sector
@loop:
    lda dir_chain_track
    sta want_track
    lda dir_chain_sector
    sta want_sector
    jsr disk_read_sector_hw
    lda fsec_error
    bne @notfound
    ldy #$00
@cp:
    lda DATA_DEC_BUF+1,y
    sta DIR_BUF,y
    iny
    bne @cp
    jsr dir_get_link            ; enlace antes de buscar (dir_find_in_buf no lo toca)
    jsr dir_find_in_buf
    lda dir_found
    bne @done
    lda dir_link_track
    beq @notfound               ; fin de la cadena
    sta dir_chain_track
    lda dir_link_sector
    sta dir_chain_sector
    jmp @loop
@notfound:
    lda #$00
    sta dir_found
@done:
    rts

;  dir_add_chain: recorre la cadena buscando un slot libre y escribe la entrada
;  (dir_ftype/track/sector/blocks + NAME_BUF). Si la cadena esta llena, asigna y
;  enlaza un nuevo sector de directorio en la pista 18.
dir_add_chain:
    lda #18
    sta dir_chain_track
    lda #1
    sta dir_chain_sector
@loop:
    lda dir_chain_track
    sta want_track
    lda dir_chain_sector
    sta want_sector
    jsr disk_read_sector_hw
    ldy #$00
@cp:
    lda DATA_DEC_BUF+1,y
    sta DIR_BUF,y
    iny
    bne @cp
    jsr dir_get_link
    jsr dir_make_entry
    lda dir_found
    bne @write                  ; slot libre encontrado en este sector
    lda dir_link_track
    beq @extend                 ; fin de cadena: hay que extender
    sta dir_chain_track
    lda dir_link_sector
    sta dir_chain_sector
    jmp @loop
@write:
    ldx #$00
@wcp:
    lda DIR_BUF,x
    sta DATA_DEC_BUF+1,x
    inx
    bne @wcp
    lda dir_chain_track
    sta want_track
    lda dir_chain_sector
    sta want_sector
    jsr save_write_dec_to
    rts
@extend:
    jsr dir_alloc_sector        ; nuevo sector en la pista 18
    lda alloc_ok
    bne @ext_ok
    rts                         ; directorio lleno (dir_found = 0)
@ext_ok:
    lda #18                     ; enlazar el sector actual al nuevo y reescribirlo
    sta DIR_BUF+0
    lda alloc_sector
    sta DIR_BUF+1
    ldx #$00
@ecp:
    lda DIR_BUF,x
    sta DATA_DEC_BUF+1,x
    inx
    bne @ecp
    lda dir_chain_track
    sta want_track
    lda dir_chain_sector
    sta want_sector
    jsr save_write_dec_to
    lda #$00                    ; nuevo sector de directorio: limpiar
    tax
@zcp:
    sta DIR_BUF,x
    inx
    bne @zcp
    lda #$00                    ; enlace: ultimo sector (track 0)
    sta DIR_BUF+0
    lda #$FF
    sta DIR_BUF+1
    jsr dir_make_entry          ; crea la entrada en el slot 0 del nuevo sector
    ldx #$00
@ncp:
    lda DIR_BUF,x
    sta DATA_DEC_BUF+1,x
    inx
    bne @ncp
    lda #18
    sta want_track
    lda alloc_sector
    sta want_sector
    jsr save_write_dec_to
    rts

;  file_save_close: graba el ultimo sector (parcial) y crea la entrada de
;  directorio recorriendo/extendiendo la cadena de sectores de directorio.
file_save_close:
    lda save_active
    bne @go
    rts
@go:
    lda #$00                    ; ultimo bloque: enlace track = 0
    sta SAVE_BUF+0
    lda save_idx                ; byte 1 = offset del ultimo byte util (save_idx-1)
    sec
    sbc #1
    sta SAVE_BUF+1
    jsr save_write_cur
    lda #FTYPE_PRG_CLOSED
    sta dir_ftype
    lda save_first_track
    sta dir_track
    lda save_first_sector
    sta dir_sector
    lda save_blocks_lo
    sta dir_blocks_lo
    lda save_blocks_hi
    sta dir_blocks_hi
    jsr dir_add_chain           ; entrada en la cadena (extiende si esta llena)
    jsr save_bam_flush          ; graba la BAM a disco una sola vez
    lda #$00
    sta save_active
    rts

;  disk_build_dir: genera el programa BASIC del directorio (LOAD "$",8) en LIST_BUF
;  leyendo el disco fisico. Lee el BAM (18/0) para el titulo y el recuento de
;  bloques libres, y recorre la cadena de sectores de directorio (18/1, 18/4, ...)
;  emitiendo una linea por cada entrada usada. list_ptr queda al final del listado
;  (su longitud es list_ptr - LIST_BUF). Asume el directorio en la pista 18.
disk_build_dir:
    lda #18
    sta want_track
    lda #0
    sta want_sector
    jsr disk_read_sector_hw     ; BAM 18/0 -> DATA_DEC_BUF+1
    lda fsec_error              ; sin disco / sin SYNC: la BAM no se ha leido.
    bne @nodisk                 ; NO construir el listado sobre un buffer basura
    ldy #$00
@cb:
    lda DATA_DEC_BUF+1,y
    sta BAM_BUF,y
    iny
    bne @cb                     ; copiar 256 bytes a BAM_BUF
    ; iniciar el listado con la linea de titulo
    lda #<LIST_BUF
    sta list_ptr
    lda #>LIST_BUF
    sta list_ptr+1
    jsr dir_make_title_line
    ; recorrer la cadena de sectores de directorio
    lda #1
    sta want_sector             ; primer sector de directorio (want_track=18)
@dirsec:
    lda #18
    sta want_track
    jsr disk_find_sector_hw     ; sector de directorio -> DATA_DEC_BUF+1
    lda fsec_error
    bne @fin                    ; sector ilegible: terminar el listado
    ldy #$00
@cd:
    lda DATA_DEC_BUF+1,y
    sta DIR_BUF,y
    iny
    bne @cd                     ; copiar 256 bytes a DIR_BUF
    jsr dir_get_link            ; enlace al siguiente sector (antes de pisar DIR_BUF)
    ; emitir una linea por cada entrada usada (8 slots de 32 bytes)
    lda #$00
    sta dir_slot
    lda #8
    sta dir_slotnum
@slot:
    ldx dir_slot
    lda DIR_BUF+2,x             ; byte de tipo de la entrada
    beq @noent                  ; $00 = entrada no usada
    jsr dir_make_listing_line
@noent:
    lda dir_slot
    clc
    adc #32
    sta dir_slot
    dec dir_slotnum
    bne @slot
    ; siguiente sector de directorio?
    lda dir_link_track
    beq @fin                    ; track 0 = fin de la cadena
    lda dir_link_sector
    sta want_sector
    jmp @dirsec
@fin:
    jsr dir_make_free_line
    jsr dir_make_end
    rts
@nodisk:
    ; sin disco: programa de directorio vacio y bien formado (sin basura).
    ; list_ptr aun no se ha fijado en esta ruta, asi que lo fijamos aqui y
    ; emitimos solo el marcador de fin ($00 $00). El C64 obtiene un programa
    ; BASIC vacio limpio; el error 21 ya lo registra la capa de lectura.
    lda #<LIST_BUF
    sta list_ptr
    lda #>LIST_BUF
    sta list_ptr+1
    jsr dir_make_end
    rts

;  disk_set_speed_zone: fija el bitrate (bits 5-6 de VIA2_PB) segun la zona de
;  velocidad de want_track. Pistas 1-17 zona 3 ($60), 18-24 zona 2 ($40), 25-30
;  zona 1 ($20), 31+ zona 0 ($00). Imprescindible para escribir: en escritura los
;  bits se generan a esta velocidad y deben casar con la densidad de la pista.
disk_set_speed_zone:
    lda want_track
    cmp #31
    bcs @z0
    cmp #25
    bcs @z1
    cmp #18
    bcs @z2
    ldx #$60                    ; zona 3 (pistas 1-17)
    bne @set
@z2:
    ldx #$40                    ; zona 2 (18-24)
    bne @set
@z1:
    ldx #$20                    ; zona 1 (25-30)
    bne @set
@z0:
    ldx #$00                    ; zona 0 (31+)
@set:
    lda VIA2_PB
    and #<(~ZONE_MASK)          ; limpiar bits 5-6
    sta VIA2_PB
    txa
    ora VIA2_PB                 ; aplicar los bits de la zona
    sta VIA2_PB
    rts

;  disk_seek: mueve el cabezal de cur_track a want_track por conteo de pasos (dos
;  medios pasos por pista). disk_step_in incrementa la pista, disk_step_out la
;  decrementa (verificado en VICE). Requiere cur_track ya inicializado.
disk_seek:
@loop:
    lda want_track
    cmp cur_track
    beq @done
    bcc @out                    ; want_track < cur_track -> hacia afuera
    jsr disk_step_in            ; want_track > cur_track -> hacia adentro
    jsr disk_step_delay
    jsr disk_step_in
    jsr disk_step_delay
    inc cur_track
    jmp @loop
@out:
    jsr disk_step_out
    jsr disk_step_delay
    jsr disk_step_out
    jsr disk_step_delay
    dec cur_track
    jmp @loop
@done:
    rts

;  disk_seek_test: lee la pista actual, hace seek hacia adentro (pista 24) y luego
;  hacia afuera (pista 17), confirmando cada destino leyendo la cabecera. Deja la
;  pista intermedia en want_sector y la final en hdr_track. Solo VICE.
disk_seek_test:
    jsr disk_find_current_track ; cur_track = pista bajo el cabezal
    lda #24
    sta want_track              ; objetivo lejano hacia adentro
    jsr disk_seek
    jsr disk_read_hdr_retry     ; hdr_track tras el primer seek
    lda hdr_track
    sta want_sector             ; observable: pista intermedia (deberia ser 24)
    sta cur_track               ; resincronizar con la realidad
    lda #17
    sta want_track              ; objetivo hacia afuera
    jsr disk_seek
    jsr disk_read_hdr_retry     ; hdr_track tras el segundo seek (deberia ser 17)
    rts

;  disk_sector_test: lee el sector de directorio 18/1 del disco fisico (seek +
;  busqueda + bloque de datos). Deja fsec_error y los 256 datos en DATA_DEC_BUF+1.
;  Solo verificacion en VICE (ensamblar con -D SECTOR_TEST).
disk_sector_test:
    lda #18
    sta want_track
    lda #1
    sta want_sector
    jsr disk_read_sector_hw
    rts

;  disk_dir_test: genera el programa de directorio del disco fisico en LIST_BUF.
;  Solo verificacion en VICE (ensamblar con -D DIR_TEST).
disk_dir_test:
    jsr disk_build_dir
    rts

;  disk_write_test: escribe un patron conocido (byte i = i) en el sector 20/0 del
;  disco fisico y lo relee en la misma sesion. Tras ejecutarse, DATA_DEC_BUF+1
;  debe contener 00 01 02 ... FF si la escritura y la relectura fueron correctas.
;  Solo verificacion en VICE (ensamblar con -D WRITE_TEST).
disk_write_test:
    ldx #$00
@fill:
    txa
    sta DATA_DEC_BUF+1,x
    inx
    bne @fill
    lda #<GCR_BLK               ; destino de la codificacion GCR
    sta gcr_dst
    lda #>GCR_BLK
    sta gcr_dst+1
    jsr disk_build_data         ; DATA_DEC_BUF -> 325 bytes GCR en GCR_BLK
    lda #20
    sta want_track
    lda #0
    sta want_sector
    jsr disk_write_sector_hw
    lda #20                     ; releer el mismo sector para verificar
    sta want_track
    lda #0
    sta want_sector
    jsr disk_read_sector_hw
    rts

;  disk_savetest: graba un fichero PRG "TEST" de 302 bytes (2 de carga $1000 + 300
;  de patron byte i = i & $FF) usando el orquestador de SAVE. Fuerza dos sectores
;  (254 + 48). Solo verificacion en VICE (ensamblar con -D SAVE_TEST).
disk_savetest:
    ldx #$00
@nm:
    lda savetest_name,x
    sta NAME_BUF,x
    inx
    cpx #16
    bne @nm
    jsr file_save_open
    lda save_err
    bne @done
    lda #$00                    ; direccion de carga $1000 (low, high)
    jsr file_save_byte
    lda #$10
    jsr file_save_byte
    lda #$00
    sta savetmp
    sta savetmp+1
@loop:
    lda savetmp
    jsr file_save_byte
    lda save_err
    bne @done
    inc savetmp
    bne @nc
    inc savetmp+1
@nc:
    lda savetmp+1
    cmp #>300
    bne @loop
    lda savetmp
    cmp #<300
    bne @loop
    jsr file_save_close
@done:
    rts

savetest_name:
    .byte 'T','E','S','T',$A0,$A0,$A0,$A0,$A0,$A0,$A0,$A0,$A0,$A0,$A0,$A0

;  disk_adjtest: escribe un patron (byte i = i) en 1/5 (zona 3) y lo relee, para
;  comprobar la escritura en una zona distinta de la pista 20 (zona 2).
disk_adjtest:
    ldx #$00
@f:
    txa
    sta DATA_DEC_BUF+1,x
    inx
    bne @f
    lda #<GCR_BLK
    sta gcr_dst
    lda #>GCR_BLK
    sta gcr_dst+1
    jsr disk_build_data
    lda #1
    sta want_track
    lda #5
    sta want_sector
    jsr disk_write_sector_hw
    lda #1
    sta want_track
    lda #5
    sta want_sector
    jsr disk_read_sector_hw
    rts

;  disk_multitest: graba 10 ficheros "F0".."F9" de 4 bytes (carga $1000 + dos bytes
;  con el indice). Al pasar de 8 fuerza el encadenamiento de un segundo sector de
;  directorio. Solo verificacion en VICE (ensamblar con -D MULTI_TEST).
disk_multitest:
    lda #$00
    sta savetmp                 ; indice de fichero 0..9
@floop:
    lda #'F'
    sta NAME_BUF+0
    lda savetmp
    clc
    adc #'0'
    sta NAME_BUF+1
    ldx #2
@pad:
    lda #$A0
    sta NAME_BUF,x
    inx
    cpx #16
    bne @pad
    jsr file_save_open
    lda save_err
    bne @done
    lda #$00                    ; carga $1000
    jsr file_save_byte
    lda #$10
    jsr file_save_byte
    lda savetmp                 ; dos bytes de datos = indice
    jsr file_save_byte
    lda savetmp
    jsr file_save_byte
    jsr file_save_close
    inc savetmp
    lda savetmp
    cmp #10
    bne @floop
@done:
    rts

; ----------------------------------------------------------------------------
;  Controlador de disco (capa logica, sin timing).
;  La pista se modela como bytes; el SYNC son bytes $FF. El alineamiento de bits
;  del SYNC real lo resuelve el hardware (VIA2) y pertenece a la capa de IRQ.
; ----------------------------------------------------------------------------
;  disk_find_sync: avanza gcr_src hasta el primer byte tras un SYNC de al menos
;  SYNC_MIN bytes $FF. Escanea hasta MAX_SCAN bytes (puntero de 16 bits, cruza
;  bloques de datos largos). sync_error = $00 ok, $FF fallo.
disk_find_sync:
    lda #$00
    sta sync_error
    ldx #$00                ; contador de $FF consecutivos
    lda #<MAX_SCAN
    sta scan_cnt
    lda #>MAX_SCAN
    sta scan_cnt+1
@loop:
    ldy #$00
    lda (gcr_src),y
    cmp #$FF
    beq @isff
    cpx #SYNC_MIN
    bcs @found              ; ya habia SYNC: gcr_src apunta al bloque
    ldx #$00
    jmp @next
@isff:
    inx
@next:
    inc gcr_src
    bne @declim
    inc gcr_src+1
@declim:
    lda scan_cnt
    bne @lo
    dec scan_cnt+1
@lo:
    dec scan_cnt
    lda scan_cnt
    ora scan_cnt+1
    bne @loop
    lda #$FF                ; limite agotado
    sta sync_error
@found:
    rts

;  disk_read_header: decodifica la cabecera (10 bytes GCR en gcr_src) a 8 bytes
;  en HEADER_BUF, valida marca y checksum, extrae track/sector.
;  hdr_error = $00 valida, $FF invalida.
disk_read_header:
    lda #<HEADER_BUF
    sta gcr_dst
    lda #>HEADER_BUF
    sta gcr_dst+1
    jsr gcr_decode          ; bytes 0..3: marca, csum, sector, track
    jsr disk_adv_src5
    jsr disk_adv_dst4
    jsr gcr_decode          ; bytes 4..7: id2, id1, relleno, relleno

    lda HEADER_BUF+0
    cmp #HDR_MARK
    bne @bad
    ; checksum = sector EOR track EOR id2 EOR id1
    lda HEADER_BUF+2
    eor HEADER_BUF+3
    eor HEADER_BUF+4
    eor HEADER_BUF+5
    cmp HEADER_BUF+1
    bne @bad
    lda HEADER_BUF+3
    sta hdr_track
    lda HEADER_BUF+2
    sta hdr_sector
    lda #$00
    sta hdr_error
    rts
@bad:
    lda #$FF
    sta hdr_error
    rts

;  disk_read_data: decodifica el bloque de datos (325 bytes GCR en gcr_src) a
;  260 bytes en DATA_DEC_BUF, valida marca $07 y checksum. Los 256 bytes utiles
;  quedan en DATA_DEC_BUF+1. data_error = $00 valido, $FF invalido.
disk_read_data:
    lda #<DATA_DEC_BUF
    sta gcr_dst
    lda #>DATA_DEC_BUF
    sta gcr_dst+1
    lda #65                 ; 260 bytes = 65 grupos de 4
    sta dsk_count
@loop:
    jsr gcr_decode
    jsr disk_adv_src5
    jsr disk_adv_dst4
    dec dsk_count
    bne @loop

    lda DATA_DEC_BUF+0
    cmp #DATA_MARK
    bne @bad
    ; checksum = XOR de los 256 bytes (DATA_DEC_BUF+1 .. +256)
    lda #<(DATA_DEC_BUF+1)
    sta dsk_ptr
    lda #>(DATA_DEC_BUF+1)
    sta dsk_ptr+1
    lda #$00
    sta dsk_csum
    ldy #$00
@csum:
    lda (dsk_ptr),y
    eor dsk_csum
    sta dsk_csum
    iny
    bne @csum               ; 256 iteraciones
    lda dsk_csum
    cmp DATA_DEC_BUF+257
    bne @bad
    lda #$00
    sta data_error
    rts
@bad:
    lda #$FF
    sta data_error
    rts

;  disk_adv_src5 / disk_adv_dst4: avanzan los punteros del codec.
disk_adv_src5:
    lda gcr_src
    clc
    adc #5
    sta gcr_src
    bcc @1
    inc gcr_src+1
@1: rts
disk_adv_dst4:
    lda gcr_dst
    clc
    adc #4
    sta gcr_dst
    bcc @1
    inc gcr_dst+1
@1: rts

;  disk_find_sector: busca en la pista el sector want_track/want_sector, lo
;  localiza por su cabecera y lee su bloque de datos. Recorre hasta MAX_TRIES
;  bloques. fsec_error = $00 exito (datos en DATA_DEC_BUF+1), $FF fallo.
disk_find_sector:
    lda #MAX_TRIES
    sta dsk_tries
@try:
    jsr disk_find_sync
    lda sync_error
    bne @fail
    jsr disk_read_header
    lda hdr_error
    bne @nextblock          ; no era una cabecera (p.ej. un bloque de datos)
    lda hdr_track
    cmp want_track
    bne @nextblock
    lda hdr_sector
    cmp want_sector
    bne @nextblock
    ; cabecera encontrada: el siguiente SYNC es su bloque de datos
    jsr disk_find_sync
    lda sync_error
    bne @fail
    jsr disk_read_data
    lda data_error
    bne @fail
    lda #$00
    sta fsec_error
    rts
@nextblock:
    dec dsk_tries
    bne @try
@fail:
    lda #$FF
    sta fsec_error
    rts

;  disk_sectors_per_track: A = track (1..35) -> A = numero de sectores segun la
;  geometria por zonas de velocidad de la 1541.
disk_sectors_per_track:
    cmp #18
    bcc @z0                 ; 1..17
    cmp #25
    bcc @z1                 ; 18..24
    cmp #31
    bcc @z2                 ; 25..30
    lda #17                 ; 31..35
    rts
@z0:
    lda #21
    rts
@z1:
    lda #19
    rts
@z2:
    lda #18
    rts

;  disk_build_data: construye el bloque de datos a grabar a partir de los 256
;  bytes en DATA_DEC_BUF+1: anade marca $07, checksum y relleno, y codifica los
;  260 bytes a 325 bytes GCR en (gcr_dst). Espejo de disk_read_data.
disk_build_data:
    lda #DATA_MARK
    sta DATA_DEC_BUF+0
    ; checksum = XOR de los 256 bytes
    lda #<(DATA_DEC_BUF+1)
    sta dsk_ptr
    lda #>(DATA_DEC_BUF+1)
    sta dsk_ptr+1
    lda #$00
    sta dsk_csum
    ldy #$00
@cs:
    lda (dsk_ptr),y
    eor dsk_csum
    sta dsk_csum
    iny
    bne @cs
    lda dsk_csum
    sta DATA_DEC_BUF+257
    lda #$00
    sta DATA_DEC_BUF+258
    sta DATA_DEC_BUF+259
    ; codificar 260 bytes (65 grupos de 4) a (gcr_dst), que apunta al inicio del
    ; buffer GCR (lo fija el llamador). DATA_DEC_BUF y un GCR_BLK contiguo se
    ; solapan en 4 bytes y el destino avanza 5 por grupo frente a 4 del origen, asi
    ; que hacia adelante el primer grupo pisaria el origen del ultimo. Se codifica
    ; HACIA ATRAS (grupo 64 -> 0): el grupo solapado se lee antes de sobrescribirlo.
    lda gcr_dst                 ; gcr_dst += 320 (inicio del ultimo grupo)
    clc
    adc #<320
    sta gcr_dst
    lda gcr_dst+1
    adc #>320
    sta gcr_dst+1
    lda #<(DATA_DEC_BUF+256)
    sta gcr_src
    lda #>(DATA_DEC_BUF+256)
    sta gcr_src+1
    lda #65
    sta dsk_count
@enc:
    jsr gcr_encode
    jsr disk_dec_src4
    jsr disk_dec_dst5
    dec dsk_count
    bne @enc
    rts

;  disk_dec_src4 / disk_dec_dst5: retroceso de punteros para codificar al reves.
disk_dec_src4:
    lda gcr_src
    sec
    sbc #4
    sta gcr_src
    bcs @1
    dec gcr_src+1
@1: rts
disk_dec_dst5:
    lda gcr_dst
    sec
    sbc #5
    sta gcr_dst
    bcs @1
    dec gcr_dst+1
@1: rts

;  disk_build_header: construye la cabecera a grabar a partir de want_track,
;  want_sector, want_id1, want_id2 (marca $08 y checksum) y la codifica a 10
;  bytes GCR en (gcr_dst). Espejo de disk_read_header.
disk_build_header:
    lda #HDR_MARK
    sta HEADER_BUF+0
    lda want_sector
    eor want_track
    eor want_id2
    eor want_id1
    sta HEADER_BUF+1
    lda want_sector
    sta HEADER_BUF+2
    lda want_track
    sta HEADER_BUF+3
    lda want_id2
    sta HEADER_BUF+4
    lda want_id1
    sta HEADER_BUF+5
    lda #$0F
    sta HEADER_BUF+6
    sta HEADER_BUF+7
    lda #<HEADER_BUF
    sta gcr_src
    lda #>HEADER_BUF
    sta gcr_src+1
    jsr gcr_encode
    jsr disk_adv_src4
    jsr disk_adv_dst5
    jsr gcr_encode
    rts

;  disk_adv_src4 / disk_adv_dst5: avance de punteros para la codificacion.
disk_adv_src4:
    lda gcr_src
    clc
    adc #4
    sta gcr_src
    bcc @1
    inc gcr_src+1
@1: rts
disk_adv_dst5:
    lda gcr_dst
    clc
    adc #5
    sta gcr_dst
    bcc @1
    inc gcr_dst+1
@1: rts

; ----------------------------------------------------------------------------
;  BAM (Block Availability Map). Opera sobre el sector BAM en BAM_BUF (256
;  bytes ya decodificados). Entrada por pista: offset 4+(track-1)*4, con el
;  contador de libres en +0 y el bitmap de 24 bits en +1..+3 (bit a 1 = libre,
;  bit 0 del primer byte = sector 0).
; ----------------------------------------------------------------------------
;  bam_calc_e: bam_e = 4 + (bam_track-1)*4
bam_calc_e:
    lda bam_track
    sec
    sbc #1
    asl a
    asl a
    clc
    adc #4
    sta bam_e
    rts

;  bam_free_on_track: A = numero de bloques libres en bam_track
bam_free_on_track:
    jsr bam_calc_e
    ldy bam_e
    lda BAM_BUF,y
    rts

;  bam_is_free: bam_result = $FF si (bam_track,bam_sector) esta libre, $00 si no
bam_is_free:
    jsr bam_calc_e
    lda bam_sector
    lsr a
    lsr a
    lsr a
    clc
    adc bam_e
    adc #1
    tay
    lda bam_sector
    and #7
    tax
    lda BAM_BUF,y
    and bit_mask,x
    beq @occ
    lda #$FF
    sta bam_result
    rts
@occ:
    lda #$00
    sta bam_result
    rts

;  bam_alloc: marca (bam_track,bam_sector) como ocupado y decrementa el contador
bam_alloc:
    jsr bam_calc_e
    lda bam_sector
    lsr a
    lsr a
    lsr a
    clc
    adc bam_e
    adc #1
    sta bam_bidx
    lda bam_sector
    and #7
    tax
    ldy bam_bidx
    lda BAM_BUF,y
    and bit_mask,x
    beq @done               ; ya ocupado
    lda bit_mask,x
    eor #$FF
    and BAM_BUF,y
    sta BAM_BUF,y
    ldx bam_e
    dec BAM_BUF,x
@done:
    rts

;  bam_free_block: marca (bam_track,bam_sector) como libre e incrementa contador
bam_free_block:
    jsr bam_calc_e
    lda bam_sector
    lsr a
    lsr a
    lsr a
    clc
    adc bam_e
    adc #1
    sta bam_bidx
    lda bam_sector
    and #7
    tax
    ldy bam_bidx
    lda BAM_BUF,y
    and bit_mask,x
    bne @done               ; ya libre
    lda bit_mask,x
    ora BAM_BUF,y
    sta BAM_BUF,y
    ldx bam_e
    inc BAM_BUF,x
@done:
    rts

;  bam_total_free: suma los contadores de las pistas 1..35 (excepto la 18, que
;  es el directorio). Resultado en bam_total_lo / bam_total_hi.
bam_total_free:
    lda #$00
    sta bam_total_lo
    sta bam_total_hi
    lda #1
    sta bam_track
@loop:
    lda bam_track
    cmp #18
    beq @skip
    jsr bam_calc_e
    ldy bam_e
    lda BAM_BUF,y
    clc
    adc bam_total_lo
    sta bam_total_lo
    bcc @skip
    inc bam_total_hi
@skip:
    inc bam_track
    lda bam_track
    cmp #36
    bne @loop
    rts

; ----------------------------------------------------------------------------
;  Directorio. Opera sobre un sector de directorio en DIR_BUF (256 bytes). Cada
;  sector tiene 8 entradas de 32 bytes en los offsets 0,32,...,224. Bytes 0-1
;  del sector: enlace al siguiente sector de directorio. Campos de cada slot:
;  +2 tipo, +3/+4 track/sector del primer bloque, +5..+20 nombre (16, $A0),
;  +28/+29 tamano en bloques. Formato publico del .d64.
; ----------------------------------------------------------------------------
;  dir_get_link: extrae el enlace al siguiente sector de directorio.
dir_get_link:
    lda DIR_BUF+0
    sta dir_link_track
    lda DIR_BUF+1
    sta dir_link_sector
    rts

;  dir_extract: con dir_slot apuntando a un slot, copia tipo, track/sector y
;  tamano a las variables dir_*.
dir_extract:
    lda dir_slot
    clc
    adc #2
    tay
    lda DIR_BUF,y           ; +2 tipo
    sta dir_ftype
    iny
    lda DIR_BUF,y           ; +3 track
    sta dir_track
    iny
    lda DIR_BUF,y           ; +4 sector
    sta dir_sector
    lda dir_slot
    clc
    adc #30
    tay
    lda DIR_BUF,y           ; +30 bloques lo
    sta dir_blocks_lo
    iny
    lda DIR_BUF,y           ; +31 bloques hi
    sta dir_blocks_hi
    rts

;  dir_find_in_buf: busca en DIR_BUF el nombre en NAME_BUF (16 bytes, $A0 de
;  relleno). dir_found = $FF si lo encuentra, con dir_ftype/track/sector/blocks.
dir_find_in_buf:
    lda #$00
    sta dir_found
    sta dir_slotnum
@slot:
    lda dir_slotnum
    asl a
    asl a
    asl a
    asl a
    asl a                   ; slotnum * 32
    sta dir_slot
    clc
    adc #2
    tay
    lda DIR_BUF,y
    and #$0F                ; tipo (bits 0-3)
    beq @next               ; 0 -> entrada vacia o borrada
    ; comparar 16 bytes del nombre
    lda dir_slot
    clc
    adc #5
    tay
    ldx #0
@cmp:
    lda DIR_BUF,y
    cmp NAME_BUF,x
    bne @next
    iny
    inx
    cpx #16
    bne @cmp
    ; coincide
    jsr dir_extract
    lda #$FF
    sta dir_found
    rts
@next:
    inc dir_slotnum
    lda dir_slotnum
    cmp #8
    bne @slot
    rts

;  dir_make_entry: escribe una entrada nueva en el primer slot libre de DIR_BUF
;  (tipo 0). Toma dir_ftype, dir_track, dir_sector, dir_blocks_lo/hi y el nombre
;  en NAME_BUF. dir_found = $FF si se creo, $00 si no habia slot libre.
dir_make_entry:
    lda #$00
    sta dir_found
    sta dir_slotnum
@mslot:
    lda dir_slotnum
    asl a
    asl a
    asl a
    asl a
    asl a
    sta dir_slot
    clc
    adc #2
    tay
    lda DIR_BUF,y
    and #$0F
    beq @free
    inc dir_slotnum
    lda dir_slotnum
    cmp #8
    bne @mslot
    rts                     ; sin slot libre, dir_found = 0
@free:
    lda dir_slot
    clc
    adc #2
    tay
    lda dir_ftype
    sta DIR_BUF,y
    iny
    lda dir_track
    sta DIR_BUF,y
    iny
    lda dir_sector
    sta DIR_BUF,y
    lda dir_slot
    clc
    adc #5
    tay
    ldx #$00
@mnm:
    lda NAME_BUF,x
    sta DIR_BUF,y
    iny
    inx
    cpx #16
    bne @mnm
    lda dir_slot
    clc
    adc #30
    tay
    lda dir_blocks_lo
    sta DIR_BUF,y
    iny
    lda dir_blocks_hi
    sta DIR_BUF,y
    lda #$FF
    sta dir_found
    rts

; ----------------------------------------------------------------------------
;  Lectura de fichero por cadena de bloques. Cada bloque de datos en CHAIN_BUF:
;  bytes 0-1 = enlace (track/sector) al siguiente bloque, o track 0 y byte 1 =
;  offset del ultimo byte util en el bloque final. Los datos van de +2 en
;  adelante (254 bytes en bloques completos). El contenido se vuelca por out_ptr.
; ----------------------------------------------------------------------------
;  file_block_process: procesa el bloque en CHAIN_BUF. Copia sus bytes utiles a
;  (out_ptr) y avanza out_ptr; deja el enlace en file_next_track/sector y el
;  numero de bytes en file_nbytes. Llamar con out_ptr ya inicializado.
file_block_process:
    lda CHAIN_BUF+0
    sta file_next_track
    lda CHAIN_BUF+1
    sta file_next_sector
    lda file_next_track
    bne @full               ; track != 0 -> bloque completo
    ; ultimo bloque: bytes utiles = offset final - 1
    lda file_next_sector
    sec
    sbc #1
    sta file_nbytes
    jmp @copy
@full:
    lda #254
    sta file_nbytes
@copy:
    ldy #$00
@cp:
    cpy file_nbytes
    beq @advance
    lda CHAIN_BUF+2,y
    sta (out_ptr),y
    iny
    bne @cp
@advance:
    lda out_ptr
    clc
    adc file_nbytes
    sta out_ptr
    bcc @ret
    inc out_ptr+1
@ret:
    rts

;  file_build_block: construye en CHAIN_BUF el bloque a grabar a partir de los
;  datos en (in_ptr). Entrada: file_nbytes = bytes utiles; file_next_track/sector
;  = enlace al siguiente bloque (file_next_track = 0 indica ultimo bloque, en cuyo
;  caso el byte 1 se fija al offset del ultimo byte util). Rellena con $00 hasta
;  254. Espejo de file_block_process.
file_build_block:
    lda file_next_track
    sta CHAIN_BUF+0
    bne @link
    lda file_nbytes         ; ultimo bloque: offset del ultimo byte = nbytes+1
    clc
    adc #1
    sta CHAIN_BUF+1
    jmp @data
@link:
    lda file_next_sector
    sta CHAIN_BUF+1
@data:
    ldy #$00
@cp:
    cpy file_nbytes
    beq @pad
    lda (in_ptr),y
    sta CHAIN_BUF+2,y
    iny
    bne @cp
@pad:
    cpy #254
    beq @done
    lda #$00
    sta CHAIN_BUF+2,y
    iny
    bne @pad
@done:
    rts

; ----------------------------------------------------------------------------
;  bam_alloc_next: asigna el siguiente bloque libre empezando por la pista en
;  bam_track, avanzando de pista (saltando la 18) si hace falta. Politica simple
;  (sin intercalado, que es una optimizacion posterior). Salida: alloc_track,
;  alloc_sector y alloc_ok ($FF asignado, $00 disco lleno).
bam_alloc_next:
    lda #$00
    sta alloc_ok
@track_loop:
    lda bam_track
    cmp #36
    bcs @fail
    cmp #18
    beq @next_track         ; la pista 18 es el directorio
    jsr bam_free_on_track
    beq @next_track         ; sin bloques libres en esta pista
    lda bam_track
    jsr disk_sectors_per_track
    sta alloc_nsec
    lda #$00
    sta bam_sector
@sec_loop:
    lda bam_sector
    cmp alloc_nsec
    bcs @next_track
    jsr bam_is_free
    lda bam_result
    bne @found
    inc bam_sector
    jmp @sec_loop
@found:
    jsr bam_alloc
    lda bam_track
    sta alloc_track
    lda bam_sector
    sta alloc_sector
    lda #$FF
    sta alloc_ok
    rts
@next_track:
    inc bam_track
    jmp @track_loop
@fail:
    lda #$00
    sta alloc_ok
    rts

; ----------------------------------------------------------------------------
;  Canal de estado (canal 15). Construye en STATUS_BUF la cadena de respuesta
;  "NN,MENSAJE,TT,SS" + CR a partir de err_code, err_track y err_sector. El
;  mensaje se busca en err_tab (formato publico de los codigos de error del DOS).
; ----------------------------------------------------------------------------
;  status_put: escribe A en STATUS_BUF[stat_idx] y avanza. Preserva A e Y.
status_put:
    ldx stat_idx
    sta STATUS_BUF,x
    inc stat_idx
    rts

;  to_2digits: A (0..99) -> X = decenas, A = unidades
to_2digits:
    ldx #0
@d:
    cmp #10
    bcc @done
    sec
    sbc #10
    inx
    jmp @d
@done:
    rts

;  status_put_2dig: escribe A (0..99) como dos digitos ASCII
status_put_2dig:
    jsr to_2digits
    sta err_tmp
    txa
    clc
    adc #'0'
    jsr status_put
    lda err_tmp
    clc
    adc #'0'
    jsr status_put
    rts

;  err_find_msg: deja msg_ptr apuntando al mensaje de err_code (o al generico)
err_find_msg:
    ldx #0
@l:
    lda err_tab,x
    cmp #$FF
    beq @found
    cmp err_code
    beq @found
    inx
    inx
    inx
    jmp @l
@found:
    lda err_tab+1,x
    sta msg_ptr
    lda err_tab+2,x
    sta msg_ptr+1
    rts

;  err_build_status: construye la cadena de estado en STATUS_BUF
err_build_status:
    lda #0
    sta stat_idx
    lda err_code
    jsr status_put_2dig
    lda #','
    jsr status_put
    jsr err_find_msg
    ldy #0
@msg:
    lda (msg_ptr),y
    beq @msgend
    jsr status_put
    iny
    jmp @msg
@msgend:
    lda #','
    jsr status_put
    lda err_track
    jsr status_put_2dig
    lda #','
    jsr status_put
    lda err_sector
    jsr status_put_2dig
    lda #$0D
    jsr status_put
    rts

; ----------------------------------------------------------------------------
;  Comandos del canal 15.
; ----------------------------------------------------------------------------
;  cmd_parse_format: de CMD_BUF "N:nombre,id" copia el nombre del disco a NAME_BUF
;  (16 bytes, relleno $A0, parando en ',') y los dos caracteres de ID a NAME_BUF2.
;  Falta de ':' o de ',' da cmd_error = $FF.
cmd_parse_format:
    lda #$00
    sta cmd_error
    ldx #$00
@fc:
    lda CMD_BUF,x
    beq @err
    cmp #':'
    beq @c1
    inx
    cpx #40
    bne @fc
    beq @err
@c1:
    inx                     ; saltar ':'
    ldy #$00
@cn:
    lda CMD_BUF,x
    beq @err                ; sin ',' -> error (NEW requiere id)
    cmp #','
    beq @nameend
    sta NAME_BUF,y
    inx
    iny
    cpy #16
    bne @cn
    lda CMD_BUF,x           ; nombre de 16: debe seguir ','
    cmp #','
    bne @err
@nameend:
    lda #$A0
@pn:
    cpy #16
    beq @id
    sta NAME_BUF,y
    iny
    jmp @pn
@id:
    inx                     ; saltar ','
    ldy #$00
@ci:
    lda CMD_BUF,x
    beq @idpad
    sta NAME_BUF2,y
    inx
    iny
    cpy #2
    bne @ci
    rts
@idpad:
    lda #$A0
@pi:
    cpy #2
    beq @done
    sta NAME_BUF2,y
    iny
    jmp @pi
@done:
    rts
@err:
    lda #$FF
    sta cmd_error
    rts

;  disk_write_header: escribe en BAM_BUF la identidad del disco (formato del DOS):
;  nombre (NAME_BUF) en $90..$9F, $A0 $A0, ID (NAME_BUF2) en $A2..$A3, $A0, "2A"
;  en $A5..$A6, cuatro $A0 mas, y el resto del sector a $00. Llamar tras
;  disk_format_bam (que escribe el bitmap en $00..$8F).
disk_write_header:
    ldx #$00
@nm:
    lda NAME_BUF,x
    sta BAM_BUF+144,x
    inx
    cpx #16
    bne @nm
    lda #$A0
    sta BAM_BUF+160
    sta BAM_BUF+161
    lda NAME_BUF2+0
    sta BAM_BUF+162
    lda NAME_BUF2+1
    sta BAM_BUF+163
    lda #$A0
    sta BAM_BUF+164
    lda #$32                ; '2'
    sta BAM_BUF+165
    lda #$41                ; 'A'
    sta BAM_BUF+166
    lda #$A0
    sta BAM_BUF+167
    sta BAM_BUF+168
    sta BAM_BUF+169
    sta BAM_BUF+170
    ldx #171                ; resto del sector a $00
    lda #$00
@z:
    sta BAM_BUF,x
    inx
    bne @z
    rts

;  cmd_parse_name: extrae de CMD_BUF el nombre tras ':' y lo copia a NAME_BUF
;  (16 bytes, relleno $A0), parando en fin de cadena o en ','. Un nombre sin
;  ':' da cmd_error = $FF.
cmd_parse_name:
    lda #$00
    sta cmd_error
    ldx #$00
@find:
    lda CMD_BUF,x
    beq @no_colon
    cmp #':'
    beq @found
    inx
    cpx #40
    bne @find
@no_colon:
    lda #$FF
    sta cmd_error
    rts
@found:
    inx                     ; saltar ':'
    ldy #$00
@copy:
    lda CMD_BUF,x
    beq @pad
    cmp #','
    beq @pad
    sta NAME_BUF,y
    inx
    iny
    cpy #16
    bne @copy
    rts
@pad:
    lda #$A0
@padloop:
    cpy #16
    beq @done
    sta NAME_BUF,y
    iny
    jmp @padloop
@done:
    rts

;  dir_scratch_entry: marca como borrada (tipo 0) la entrada en dir_slot.
dir_scratch_entry:
    lda dir_slot
    clc
    adc #2
    tay
    lda #$00
    sta DIR_BUF,y
    rts

;  cmd_parse_rename: de CMD_BUF "R:nuevo=viejo" copia el nombre NUEVO a NAME_BUF2
;  (parando en '=') y el VIEJO a NAME_BUF (parando en ',' o fin), ambos con
;  relleno $A0 a 16 bytes. Falta de ':' o de '=' da cmd_error = $FF. El nombre
;  buscado en el directorio queda en NAME_BUF; el que se escribira, en NAME_BUF2.
cmd_parse_rename:
    lda #$00
    sta cmd_error
    ldx #$00
@find_colon:
    lda CMD_BUF,x
    beq @err
    cmp #':'
    beq @c1
    inx
    cpx #40
    bne @find_colon
    beq @err
@c1:
    inx                     ; saltar ':'
    ldy #$00
@cp_new:
    lda CMD_BUF,x
    beq @err                ; sin '=' -> error
    cmp #'='
    beq @pad_new
    sta NAME_BUF2,y
    inx
    iny
    cpy #16
    bne @cp_new
    lda CMD_BUF,x           ; nombre nuevo de 16: debe seguir '='
    cmp #'='
    bne @err
@pad_new:
    lda #$A0
@pn:
    cpy #16
    beq @after_eq
    sta NAME_BUF2,y
    iny
    jmp @pn
@after_eq:
    inx                     ; saltar '='
    ldy #$00
@cp_old:
    lda CMD_BUF,x
    beq @pad_old
    cmp #','
    beq @pad_old
    sta NAME_BUF,y
    inx
    iny
    cpy #16
    bne @cp_old
    rts
@pad_old:
    lda #$A0
@po:
    cpy #16
    beq @done
    sta NAME_BUF,y
    iny
    jmp @po
@done:
    rts
@err:
    lda #$FF
    sta cmd_error
    rts

;  dir_rename_entry: escribe NAME_BUF2 (nombre nuevo) en el campo de nombre de
;  la entrada en dir_slot (offset +5..+20).
dir_rename_entry:
    lda dir_slot
    clc
    adc #5
    tay
    ldx #$00
@l:
    lda NAME_BUF2,x
    sta DIR_BUF,y
    iny
    inx
    cpx #16
    bne @l
    rts

;  disk_format_bam: construye en BAM_BUF un BAM de disco recien formateado: todas
;  las pistas con todos sus sectores libres, salvo 18/0 (el propio BAM) y 18/1
;  (primer sector de directorio), que quedan ocupados. Escribe la cabecera (enlace
;  a 18/1 y la marca de formato 'A'). El nombre y el ID del disco se escriben
;  aparte. Comprobado en test/test_cmd.py (NEW deja 664 bloques libres).
disk_format_bam:
    lda #18
    sta BAM_BUF+0           ; enlace: pista del primer sector de directorio
    lda #1
    sta BAM_BUF+1           ; sector
    lda #$41                ; 'A' = formato DOS 2.0
    sta BAM_BUF+2
    lda #$00
    sta BAM_BUF+3
    lda #1
    sta fmt_track
@tloop:
    lda fmt_track
    sec
    sbc #1
    asl a
    asl a                   ; (pista-1)*4
    clc
    adc #4                  ; + cabecera
    tax                     ; X = offset de la entrada de esta pista
    lda fmt_track
    jsr disk_sectors_per_track
    sta BAM_BUF,x           ; contador de libres = numero de sectores
    sta fmt_rem
    inx                     ; -> primer byte de bitmap
    lda #3
    sta fmt_cnt
@bloop:
    lda fmt_rem
    cmp #8
    bcc @partial
    lda #$FF                ; >=8 sectores: byte completo libre
    sta BAM_BUF,x
    lda fmt_rem
    sec
    sbc #8
    sta fmt_rem
    jmp @bnext
@partial:
    ldy fmt_rem
    lda low_mask9,y         ; los fmt_rem bits bajos a 1
    sta BAM_BUF,x
    lda #0
    sta fmt_rem
@bnext:
    inx
    dec fmt_cnt
    bne @bloop
    inc fmt_track
    lda fmt_track
    cmp #36
    bne @tloop
    ; marcar ocupados los dos sectores del sistema (18/0 y 18/1)
    lda #18
    sta bam_track
    lda #0
    sta bam_sector
    jsr bam_alloc
    lda #18
    sta bam_track
    lda #1
    sta bam_sector
    jsr bam_alloc
    rts

; ----------------------------------------------------------------------------
;  Listado de directorio (LOAD "$",8). La unidad genera un pseudo-programa BASIC
;  que el C64 LISTa como directorio. Cada linea es: enlace (2 bytes, no nulo, que
;  el cargador re-vincula), numero de linea (2 bytes LE = numero de bloques),
;  cuerpo de texto y un $00 de fin. dir_make_listing_line produce la linea de una
;  entrada de fichero; el titulo y "BLOCKS FREE." se generan aparte y la cadena de
;  sectores de directorio se recorre por encima. Formato observable del DOS.
; ----------------------------------------------------------------------------
;  list_put: escribe A en (list_ptr) y avanza list_ptr (16 bits). Preserva A,X,Y.
list_put:
    sta list_byte
    sty list_y
    ldy #$00
    lda list_byte
    sta (list_ptr),y
    inc list_ptr
    bne @nc
    inc list_ptr+1
@nc:
    ldy list_y
    lda list_byte
    rts

;  ll_count_digits: numero de digitos decimales (1..3) de cur_hi:cur_lo (0..664).
ll_count_digits:
    lda cur_hi
    bne @three
    lda cur_lo
    cmp #100
    bcs @three
    cmp #10
    bcs @two
    lda #1
    rts
@two:
    lda #2
    rts
@three:
    lda #3
    rts

;  dir_make_listing_line: genera por list_ptr la linea BASIC de la entrada en
;  dir_slot. Entrada valida (tipo != 0). list_ptr debe apuntar al destino.
dir_make_listing_line:
    lda #$01                ; enlace placeholder no nulo (el cargador re-vincula)
    jsr list_put
    lda #$01
    jsr list_put
    lda dir_slot            ; numero de linea = numero de bloques (slot+30/+31)
    clc
    adc #30
    tax
    lda DIR_BUF,x
    sta cur_lo
    jsr list_put
    inx
    lda DIR_BUF,x
    sta cur_hi
    jsr list_put
    jsr ll_count_digits     ; relleno = 4 - digitos espacios (alinea las comillas)
    sta list_dig
    lda #4
    sec
    sbc list_dig
    tax
@sp:
    lda #' '
    jsr list_put
    dex
    bne @sp
    lda #'"'
    jsr list_put
    lda dir_slot            ; nombre: slot+5..+20, parar en $A0
    clc
    adc #5
    tax
    ldy #$00
@nm:
    lda DIR_BUF,x
    cmp #$A0
    beq @nmend
    jsr list_put
    inx
    iny
    cpy #16
    bne @nm
@nmend:
    lda #'"'
    jsr list_put
    sty list_dig            ; relleno tras nombre = 17 - longitud (alinea el tipo)
    lda #17
    sec
    sbc list_dig
    tax
@sp2:
    lda #' '
    jsr list_put
    dex
    bne @sp2
    lda dir_slot            ; tipo: ftype_tab[(slot+2 & 7)*3], 3 letras
    clc
    adc #2
    tax
    lda DIR_BUF,x
    and #$07
    sta list_dig
    asl a
    clc
    adc list_dig            ; (tipo & 7) * 3
    tax
    ldy #$00
@ty:
    lda ftype_tab,x
    jsr list_put
    inx
    iny
    cpy #3
    bne @ty
    lda #$00                ; fin de linea
    jsr list_put
    rts

;  dir_make_title_line: genera por list_ptr la linea de titulo del listado
;  (numero de linea 0, video inverso, nombre e ID del disco leidos del BAM).
dir_make_title_line:
    lda #$01
    jsr list_put
    lda #$01
    jsr list_put
    lda #$00                ; numero de linea = 0
    jsr list_put
    lda #$00
    jsr list_put
    lda #$12                ; RVS ON (video inverso del titulo)
    jsr list_put
    lda #'"'
    jsr list_put
    ldx #$00
@nm:
    lda BAM_BUF+144,x       ; nombre del disco
    jsr list_put
    inx
    cpx #16
    bne @nm
    lda #'"'
    jsr list_put
    lda #' '
    jsr list_put
    lda BAM_BUF+162         ; ID del disco
    jsr list_put
    lda BAM_BUF+163
    jsr list_put
    lda #' '
    jsr list_put
    lda #'2'
    jsr list_put
    lda #'A'
    jsr list_put
    lda #$00
    jsr list_put
    rts

;  dir_make_free_line: genera la linea "BLOCKS FREE." con el numero de bloques
;  libres como numero de linea (recalculado del BAM con bam_total_free).
dir_make_free_line:
    jsr bam_total_free
    lda #$01
    jsr list_put
    lda #$01
    jsr list_put
    lda bam_total_lo        ; numero de linea = bloques libres
    jsr list_put
    lda bam_total_hi
    jsr list_put
    ldx #$00
@t:
    lda free_text,x
    beq @end
    jsr list_put
    inx
    jmp @t
@end:
    lda #$00
    jsr list_put
    rts

;  dir_make_end: cierra el pseudo-programa con un enlace nulo (00 00).
dir_make_end:
    lda #$00
    jsr list_put
    lda #$00
    jsr list_put
    rts
;  fisico valido: pista 1..35 y sector dentro del numero de sectores de esa pista.
;  Devuelve A = $FF si valido, $00 si no. Lo usa VALIDATE para no seguir cadenas
;  corruptas (enlace fuera de rango) de forma indefinida.
disk_link_valid:
    lda file_next_track
    beq @bad                ; pista 0 no es un bloque (es fin de cadena)
    cmp #36
    bcs @bad                ; pista >= 36 fuera de rango
    lda file_next_track
    jsr disk_sectors_per_track
    cmp file_next_sector
    beq @bad                ; sector == nsec -> fuera (validos 0..nsec-1)
    bcc @bad                ; nsec < sector -> fuera
    lda #$FF
    rts
@bad:
    lda #$00
    rts

; ----------------------------------------------------------------------------
irq_brk:
    rti
nmi:
    rti

.segment "RODATA"
TX_BUF: .byte $11, $22, $33

; tabla GCR directa: nibble (0..15) -> codigo de 5 bits
gcr_enc_tab:
    .byte $0A,$0B,$12,$13,$0E,$0F,$16,$17
    .byte $09,$19,$1A,$1B,$0D,$1D,$1E,$15
; tabla GCR inversa: codigo de 5 bits (0..31) -> nibble ($FF si invalido)
gcr_dec_tab:
    .byte $FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF
    .byte $FF,$08,$00,$01,$FF,$0C,$04,$05
    .byte $FF,$FF,$02,$03,$FF,$0F,$06,$07
    .byte $FF,$09,$0A,$0B,$FF,$0D,$0E,$FF
; mascaras de bit individual: bit_mask[n] = 1<<n
bit_mask:
    .byte $01,$02,$04,$08,$10,$20,$40,$80
; mascaras acumuladas: low_mask9[n] = (1<<n)-1, con los n bits bajos a 1
low_mask9:
    .byte $00,$01,$03,$07,$0F,$1F,$3F,$7F,$FF
; tipos de fichero del listado: indice = (tipo & 7), tres letras cada uno
ftype_tab:
    .byte "DEL"
    .byte "SEQ"
    .byte "PRG"
    .byte "USR"
    .byte "REL"
; texto de la linea de cierre del listado de directorio
free_text:
    .byte "BLOCKS FREE.", 0

; --- canal de estado: tabla de codigos y mensajes (subconjunto del DOS) ---
err_tab:
    .byte $00
    .word msg_ok
    .byte $01
    .word msg_scratched
    .byte $1E                ; 30 decimal: SYNTAX ERROR
    .word msg_syntax
    .byte $3E                ; 62 decimal: FILE NOT FOUND
    .word msg_notfound
    .byte $3F                ; 63 decimal: FILE EXISTS
    .word msg_exists
    .byte $48                ; 72 decimal: DISK FULL
    .word msg_full
    .byte $FF                ; por defecto
    .word msg_generic
msg_ok:        .byte " OK", 0
msg_scratched: .byte " FILES SCRATCHED", 0
msg_syntax:    .byte " SYNTAX ERROR", 0
msg_notfound:  .byte " FILE NOT FOUND", 0
msg_exists:    .byte " FILE EXISTS", 0
msg_full:      .byte " DISK FULL", 0
msg_generic:   .byte " ERROR", 0

.segment "VECTORS"
    .word nmi
    .word reset
    .word irq_brk
