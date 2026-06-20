import os, sys, subprocess, time
if not os.path.exists('/home/claude/Pascuals-BASIC/bin/kernal_c64.bin'):
    subprocess.run('cd /home/claude && git clone https://github.com/Pascual-Candel-Palazon/Pascuals-BASIC && cd Pascuals-BASIC && sh build.sh', shell=True)
sys.path.insert(0,'test')
from vice_monitor import ViceMonitor, launch_x64sc
B='/home/claude/Pascuals-BASIC/bin'; WORK='/tmp/dos1541_sbl3'; os.makedirs(WORK,exist_ok=True)
DISK=WORK+'/disco.d64'
subprocess.run('cp dos.bin %s/'%WORK,shell=True)
subprocess.run('c1541 -format "p,01" d64 %s >/dev/null 2>&1'%DISK,shell=True)
extra=['-kernal',B+'/kernal_c64.bin','-basic',B+'/basic_c64.bin','-chargen',B+'/chargen.bin',
       '-dos1541',WORK+'/dos.bin','-drive8type','1541','-drive8truedrive','-8',DISK]
p=launch_x64sc(WORK,port=6574,extra=extra,logpath=WORK+'/v.log')
mem0801=None
try:
    time.sleep(10); m=ViceMonitor(6574); m.connect()
    m.mem_set(0x0277, bytes([0x31,0x3F,0x31,0x0D]), memspace=0)   # "1?1" + CR
    m.mem_set(0x00C6, bytes([4]), memspace=0)
    m.resume(); time.sleep(3); m.connect()
    mem0801=bytes(m.mem_get(0x0801,0x0850,memspace=0))            # 80 bytes desde $0801
    m.mem_set(0x0277, bytes([0x53,0x41,0x56,0x45,0x22,0x54,0x22,0x2C,0x38,0x0D]), memspace=0)
    m.mem_set(0x00C6, bytes([10]), memspace=0)
    m.resume(); time.sleep(15); m.connect(); m.resume(); m.quit()
finally:
    p.terminate()
    try: p.wait(timeout=5)
    except Exception: p.kill()
time.sleep(1)
print('--- directorio ---'); print(subprocess.run('c1541 %s -dir'%DISK,shell=True,capture_output=True,text=True).stdout.strip())
os.chdir(WORK); subprocess.run('rm -f t; c1541 %s -extract'%DISK,shell=True,capture_output=True,text=True)
if os.path.exists(WORK+'/t') and mem0801:
    got=open(WORK+'/t','rb').read()
    print('fichero "t": %d bytes'%len(got))
    print('  fichero:', ' '.join('%02X'%b for b in got))
    print('  dir de carga:', '%02X %02X (= $0801)'%(got[0],got[1]))
    body=got[2:]; mem=mem0801[:len(body)]
    print('  cuerpo == memoria $0801.. del C64 libre:', body==mem)
    print('  memoria:', ' '.join('%02X'%b for b in mem))
