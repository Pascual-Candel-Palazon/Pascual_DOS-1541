# Diagnostico del bus IEC en hardware emulado (VICE)

Estado: el bus IEC NO completa el handshake con el C64 real. Primer fallo de la
fase de hardware, en una zona que el harness py65 no podia cubrir (timing y
semantica de las lineas, marcada desde el principio como "hipotesis a validar en
VICE").

## Como se reproduce

`python3 test/diag_bus.py` (requiere VICE y las ROMs del C64). Arranca el C64 con
nuestra ROM como unidad (-dos1541), inyecta `LOAD"$",8` por el buffer de teclado y
lee el estado.

## Evidencia observada

- El C64 llega a "SEARCHING FOR $" y se queda ahi indefinidamente (sin "DEVICE NOT
  PRESENT" y sin timeout en muchos segundos de warp). C64 ST($90)=$00.
- La unidad: iec_dev=8 (reset ejecutado), pero iec_state=0, iec_sa=0, data_idx=0:
  no llego a procesar el comando ni a recibir ningun byte.
- VIA1_PB de la unidad ($1800) = $81 estable: ATN_IN=1 (el C64 asierta ATN y lo
  mantiene), CLK_IN=0, DATA_IN=1. La linea ATN llega fisicamente a la unidad.
- PC de la unidad clavado en $C1FB, dentro de iec_recv_byte ($C1AE): la unidad
  esta colgada en un bucle de espera de transicion de CLK durante la recepcion del
  byte.

## Interpretacion

mainloop detecta ATN con la polaridad correcta (and #ATN_IN; bne con ATN_IN=1) y
entra en iec_atn -> iec_recv_byte. Pero el handshake byte a byte (los pasos de
"listener ready", deteccion de EOI y lectura bit a bit sincronizada con los flancos
de CLK que marca el C64) no se sincroniza con el timing/semantica reales. La unidad
queda esperando una transicion que no interpreta como espera, y el C64 queda
esperando el handshake de la unidad: deadlock estable.

## Causa raiz probable (a confirmar al arreglar)

1. Polaridad/semantica de las lineas CLK_IN/DATA_IN tal como las lee la VIA1 real,
   frente a la convencion idealizada del harness.
2. Gestion de ATNA (bit $10 de VIA1_PB): en la 1541 hay una compuerta de hardware
   que combina ATN entrante con ATNA y asierta DATA automaticamente bajo ATN hasta
   que el software iguala ATNA. iec_atn no gestiona ATNA; conviene revisarlo.
3. Timing de los bucles de espera de bit en iec_recv_byte frente a los flancos
   reales del C64.

## Siguiente paso

Revisar el protocolo de handshake del bus IEC (documentacion publica del bus serie
Commodore, Nivel A) y corregir iec_recv_byte y la gestion de ATNA en iec_atn,
iterando con test/diag_bus.py. La capa logica y de datos (verificada y contrastada
con VICE/c1541) no se toca; el trabajo es exclusivamente de la capa de bus/fisica.

## Avance: bug de ATNA corregido (handshake desbloqueado)

Confirmado empiricamente con el monitor: bajo ATN, la linea DATA del bus obedece
`DATA_asserted = DATA_OUT OR (ATN_IN AND NOT ATNA)`. Con ATNA=0 el hardware fuerza
DATA baja; con ATNA=1 el software recupera el control via DATA_OUT.

Fix aplicado en iec_atn: al aceptar el ATN se asierta DATA_OUT y se pone ATNA=1 en
una sola escritura (mantiene DATA asertada sin glitch pero tomando el control); al
salir (ATN liberado) se restaura ATNA=0. Asi, cuando iec_recv_byte libera DATA_OUT
para senalar "listener listo", la linea SE LIBERA de verdad y el controlador avanza.

Resultado en VICE tras el fix: la unidad ya NO se cuelga (PC pasa de $C1FB a
mainloop), el C64 completa la fase ATN y libera ATN (VIA1_PB $81 -> $03). Las 9
baterias logicas siguen en verde.

## Pendiente: muestreo de bits incorrecto (segundo bug)

Con instrumentacion temporal se vio que la unidad ahora recibe bytes (la estructura
del handshake byte a byte progresa), pero su contenido es $FF $FF en vez del
comando esperado (LISTEN 8 = $28). Es decir, el bucle de lectura bit a bit de
iec_recv_byte muestrea DATA siempre como liberada. Es un problema de polaridad o,
mas probable, de FLANCO/timing en que momento se lee DATA respecto al CLK del
talker. Hay que fijar el muestreo del bit segun el protocolo del bus serie
(documentacion publica, Nivel A) y reverificar con test/diag_bus.py (objetivo
intermedio: que la unidad reciba $28 y quede en ST_LISTEN). La respuesta completa al
LOAD ademas requerira la capa fisica del disco, aun ausente.

## Resuelto: muestreo de bits (recepcion y transmision)

Confirmado con la especificacion publica del bus serie (Butterfield "How the
VIC/64 Serial Bus Works", ejemplo de talker en Lemon64): el talker pone el bit en
DATA y LIBERA el reloj para senalar dato valido; el listener lee cuando ve CLK
liberado, luego espera a que CLK se asierte para el siguiente bit. El codigo leia
con CLK asertado (la fase "dato no valido"), de ahi el $FF constante.

Fix en iec_recv_byte (bucle de bits): leer DATA con CLK liberado (CLK_IN=0), luego
esperar CLK asertado. Fix simetrico en iec_send_byte: liberar CLK para senalar dato
valido y asertarlo para preparar el siguiente, con un asertado inicial de arranque.

Verificacion en VICE de un LOAD"$",8 completo: la unidad recibe la secuencia
$28 $F0 $24 $3F $48 $60 $5F $28 $E0 $3F, es decir LISTEN 8, OPEN, '$', UNLISTEN,
TALK 8, secondary, UNTALK (tras la transmision), LISTEN 8, CLOSE, UNLISTEN; el C64
retorna a READY. Recepcion de comandos, turnaround y recepcion del UNTALK
post-transmision quedan validados en hardware emulado.

El harness py65 (test/test_iec.py) usaba un modelo del bus con la convencion
INCORRECTA, que coincidia con el codigo erroneo y daba un falso 9/9. Se corrigio el
modelo (talker y listener) a la convencion real del protocolo. El caso de
turnaround del harness verifica turnaround + transmision con EOI; el cierre del
canal (UNTALK posterior) no se modela por una limitacion de timing del modelo
tick-based en la transicion transmision->recepcion, y se valida en hardware (VICE)
segun lo anterior.

Pendiente estructural: la capa fisica del disco (lectura GCR a nivel de bit, SYNC,
shift register de la VIA2, cola de trabajos, control de motor y cabeza). Sin ella,
iec_talk transmite un buffer de prueba; con ella, la 1541 podra leer el sector 18/1
y enviar el directorio real. La transmision (iec_send_byte) quedara entonces
verificable tambien en hardware.

----------------------------------------------------------------------------
Deteccion de ATN a mitad de byte y sistema 100% libre (C64 libre + 1541 libre)
----------------------------------------------------------------------------

Hito: se ha enfrentado este dos1541 al C64 con ROMs libres del repo
Pascuals-BASIC (BASIC derivado del fuente MIT de Microsoft, KERNAL clean-room,
chargen LGPL de MEGA65 Open ROMs), sin ninguna ROM propietaria de Commodore y
sin dispositivo virtual de VICE (-drive8truedrive, el unico camino es C64 libre
-> bus IEC -> dos1541). Es la primera vez que se juntan: el dos1541 estaba
validado contra el KERNAL original y el C64 libre contra una 1541 real, nunca
entre si.

Bug encontrado (deadlock en el primer intento): el C64 libre llega a READY y se
teclea LOAD"$",8, pero el directorio no carga. Diagnostico por PC y lineas de
bus: la unidad se queda en iec_recv_byte @w_clk_ass (a mitad de un byte,
esperando CLK asertado) y el C64 en su KISEND @wr (esperando RFD, es decir que la
unidad libere DATA). La secuencia LISTEN 8 ($28), OPEN ($F0), '$' ($24) se recibe
bien (data_idx=1, iec_state=$01); el C64 intenta enviar TALK 8 ($48) asertando
ATN, pero el dos1541, tras recibir el nombre, habia vuelto a iec_recv_byte a por
un segundo byte de datos y solo sondeaba ATN al inicio de cada byte (@w_clkrel),
no a mitad. La 1541 real detecta ATN por hardware (linea ATN -> CA1 de VIA1, por
IRQ) y aborta al instante; el C64 libre confia en eso y no marca EOI en el
nombre. El KERNAL original si marcaba EOI en el nombre, por eso el dos1541 salia
limpio y el deadlock nunca se habia visto.

Fix (en iec_recv_byte): vigilar ATN tambien durante la espera entre bits, en el
bucle @w_clk_ass (no en @w_clk_rel, que es el muestreo critico del bit). El
camino rapido cuando CLK ya esta asertado queda intacto (lda VIA1_PB; and
#CLK_IN; bne @ass_ok); solo si CLK sigue liberado se comprueba ATN (and #ATN_IN;
cmp iec_atn_exp; bne @abort). @abort ya ponia iec_abort=$FF y volvia al mainloop,
que procesa el comando ATN. Asi el dos1541 detecta el ATN a mitad de byte como lo
haria el hardware real.

Intentos descartados (rompian el KERNAL original por timing): comprobar ATN en
ambos bucles cada iteracion, y comprobar ATN en @w_clk_rel. Anadir trabajo al
muestreo del bit (@w_clk_rel) desplaza el instante de lectura de DATA y el KERNAL
original, mas ajustado en el timing que el libre, pierde bits. Poniendo la
vigilancia solo en @w_clk_ass (la espera entre bits, que no muestrea) se resuelve
el deadlock con el C64 libre sin tocar el timing que necesita el original.

Verificado tras el fix (todo en VICE, ROM de produccion sin flags):
  - C64 libre + 1541 libre: LOAD"$",8 carga el directorio real en $0801
    (PRUEBA / OBJETO / PRG / BLOCKS FREE) y LOAD"DATOS",8,1 carga el fichero por
    nombre byte a byte en $5000. Prueba autonoma: test/libre_vice.py (clona y
    construye el C64 libre si no esta).
  - KERNAL original + dos1541 (test/load_vice.py): LOAD"$",8 y LOAD"DATOS",8,1 OK.
  - Lectura fisica (sector_vice.py) y directorio fisico (dir_vice.py): OK.
  - Baterias py65 (make test): 9/9.

Pendiente (mejora de robustez, no urgente): implementar la IRQ de ATN real (CA1
de VIA1) como en el hardware, que abortaria la operacion en curso sin depender de
ningun polling y seria el camino mas fiel al chip.
