# Build de la ROM DOS 1541 clean room.
ASM   = ca65
LINK  = ld65
CFG   = src/dos1541.cfg

dos.bin: src/dos.o $(CFG)
	$(LINK) -C $(CFG) -Ln dos.lbl -o $@ src/dos.o

src/dos.o: src/dos.s
	$(ASM) -g -o $@ $<

test: dos.bin
	python3 test/test_iec.py
	python3 test/test_gcr.py
	python3 test/test_disk.py
	python3 test/test_bam.py
	python3 test/test_dir.py
	python3 test/test_dir_nodisk.py
	python3 test/test_file.py
	python3 test/test_save.py
	python3 test/test_cmd.py
	python3 test/test_chan.py
	python3 test/test_hdr_retry_nosync.py
	python3 test/test_cur_track_preserved.py
	python3 test/test_vice_ref.py

clean:
	rm -f src/dos.o dos.bin dos.lbl

.PHONY: test clean
