# PROCEDENCIA

Reglas de procedencia del codigo de dos1541. Objetivo: un reemplazo limpio del
DOS de la 1541, publicable bajo licencia libre, sin material derivado de la
ROM original de Commodore.

## Niveles permitidos

**Nivel A. Interfaz de hardware y especificaciones publicas.** Permitido.
Direcciones de las VIA y del 6502, distribucion de bits de los puertos,
vectores de interrupcion, formato fisico del disco (pistas, sectores, SYNC,
codificacion GCR 4 a 5), estructura del formato de imagen .d64, estructura del
BAM y del directorio, protocolo del bus serie IEC. Todo ello documentado en
manuales de usuario, hojas de datos, articulos tecnicos y descripciones de
formato de dominio publico.

Nota de trazabilidad (hito 2a): la tabla GCR de 4 a 5 bits implementada en
src/dos.s (gcr_enc_tab / gcr_dec_tab) procede de la descripcion publica del
formato, no de ningun desensamblado. Su correccion se comprueba por round-trip
contra una referencia independiente en test/test_gcr.py, no copiando una
implementacion ajena.

Nota de trazabilidad (capa fisica de lectura): el patron de lectura del cabezal
(clv / bvc espera / lda VIA2_PA, y la espera del SYNC con bit VIA2_PB / bpl) es
interfaz obligatoria del hardware, no una rutina de la ROM 1541. El byte-ready
del controlador esta cableado a la entrada SO del 6502, de modo que el flag V es
la unica forma de saber que hay un byte disponible; y el SYNC esta cableado a
PB7. Cualquier codigo que lea el disco debe usar ese patron porque lo dicta el
cableado, igual que leer un puerto con un flag de "dato listo". Procede de la
documentacion publica del controlador de disco (Butterfield; luigidifraia sobre
block-sync/byte-sync; ythiee; linusakesson; xentax), Nivel A, no de inspeccionar
la ROM de Commodore.

Nota de trazabilidad (capa fisica de escritura): el patron de escritura del
cabezal (precargar el byte en A, bvc espera, clv, sta VIA2_PA) es el reflejo
exacto del de lectura y se deriva del mismo cableado. El byte-ready del
controlador esta en la entrada SO del 6502, asi que el flag V es la unica forma
de sincronizar con el latch de salida; y la ventana entre el flanco y el inicio
de la serializacion del byte siguiente es de pocos ciclos, demasiado corta para
un lda dentro de ella, lo que obliga a tener el byte ya en A antes de esperar.
Por el mismo presupuesto de ciclos, el recorrido del buffer usa direccionamiento
indexado simple en tramos que no cruzan pagina. Todo ello se sigue de la hoja de
datos del 6522 (puertos, handshake CA1/CA2, SR) y de la documentacion publica
del controlador de la 1541 (Di Fraia; ythiee), Nivel A. La rutina se rederivo
desde ese hardware, sin tomar su estructura de ningun desensamblado; la
convergencia con el firmware original (lda/bvc/clv/sta) la impone el cableado, no
una copia. La correccion se comprueba por round-trip de escritura mas relectura
en VICE (zona 2 y camino SAVE en zona rapida), no contra ninguna ROM.

**Nivel B. Comportamiento observable.** Permitido. Lo que hace una 1541 real
vista como caja negra: que bytes devuelve en el bus ante un comando, que imagen
.d64 produce un formateo o un guardado, que mensaje de error emite en el canal
15. La 1541 fisica, o la ROM original ejecutandose en VICE, sirven como oraculo
de referencia, observando entradas y salidas, nunca el codigo interno.

**Nivel C. Desensamblado del codigo original.** Prohibido. No se lee, no se
consulta y no se copia ninguna forma del codigo de la ROM de Commodore:
direcciones internas de rutinas, layout de la pagina cero del DOS, codigos del
job queue, ni cualquier estructura interna conocida solo por desensamblado.

## Consecuencia de diseno

Como el Nivel C esta prohibido, este DOS no puede ni pretende ser compatible
con software que dependa de internals (fast loaders, protecciones). Esa es la
frontera del alcance Nivel 1 de SPEC.md y es una decision, no una carencia.

## Fuentes contaminadas (lista negra)

No usar como referencia bajo ningun concepto:

- mist64/dos1541: reconstruccion de la ROM original con simbolos y comentarios
  originales. Es Nivel C.
- Desensamblados comentados de la ROM de la 1541 (por ejemplo el de g3sl). Nivel C.
- JiffyDOS, SpeedDOS, DolphinDOS y similares: son parches sobre la ROM original,
  ademas propietarios.
- Volcados binarios de la ROM original (zimmers.net y otros): solo admisibles
  como oraculo de comportamiento ejecutandose como caja negra (Nivel B), jamas
  desensamblados ni inspeccionados (Nivel C).

## Pendiente

Consulta a abogado de propiedad intelectual antes de la publicacion, en linea
con el criterio ya aplicado al proyecto C64.

## Validacion contra la referencia VICE (c1541)

Ademas del round-trip interno, el formato en disco se valida contra la herramienta
c1541 de VICE, usada como caja negra (Nivel B): se le pide formatear una imagen
.d64 y escribir ficheros, y se comparan byte a byte los sectores que produce
(BAM 18/0, entradas de directorio 18/1) contra los que generan nuestras rutinas.
No se inspecciona ni se porta el codigo de VICE; solo se observa su salida, igual
que se observaria un disco real. Esta validacion es opcional (test/test_vice_ref.py
se salta si c1541 no esta instalado) y complementa, sin sustituir, al harness
logico. Resultado actual, en ambos sentidos: (1) BAM (cabecera y bitmap de las 35
pistas, sector 18/0 completo) y entrada de directorio identicos a la referencia;
(2) un fichero multi-bloque escrito por c1541 se lee con nuestras rutinas de
cadena y se reconstruye identico; (3) un disco generado integramente por nuestro
DOS (BAM, directorio y datos) es listado y leido correctamente por c1541. La capa
de datos queda asi contrastada en lectura y escritura contra la implementacion de
referencia. Sigue pendiente de validar la capa fisica (bus IEC, GCR a nivel de
bit, timing), que c1541 no ejercita y que requiere el emulador completo o hardware.
