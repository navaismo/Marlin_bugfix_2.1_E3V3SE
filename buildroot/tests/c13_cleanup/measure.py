#!/usr/bin/env python3
"""Record linked sections/symbols and compiler stack frames, never runtime peak."""
import json
from pathlib import Path
import shlex
import shutil
import subprocess
from elftools.elf.elffile import ELFFile

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'.pio/c13-cleanup'
TOOL=Path.home()/'.platformio/packages/toolchain-gccarmnoneeabi/bin/arm-none-eabi-nm'


def measure(path):
    with path.open('rb') as stream:
        elf=ELFFile(stream)
        sections={s.name:s['sh_size'] for s in elf.iter_sections()}
        flash=sum(s['sh_size'] for s in elf.iter_sections() if s['sh_flags'] & 2 and s['sh_type']!='SHT_NOBITS')
        return {'data':sections.get('.data',0),'bss':sections.get('.bss',0),
                'ram':sections.get('.data',0)+sections.get('.bss',0),
                'flash':sum(sections.get(name,0) for name in ('.text','.rodata','.data')),
                'flash_allocated_load_sections':flash,
                'linker_stack_heap_reservation':sections.get('._user_heap_stack',0),
                'vector_address':hex(elf.get_section_by_name('.isr_vector')['sh_addr'])}


def main():
    final=OUT/'final';final.mkdir(parents=True,exist_ok=True)
    for ext in ('elf','bin'):
        path=max((ROOT/'.pio/build/STM32F103RET6_creality').glob('firmware-*.'+ext),key=lambda p:p.stat().st_mtime)
        shutil.copy2(path,final/('firmware.'+ext))
    shutil.copy2(ROOT/'.pio/build/STM32F103RET6_creality/firmware.map',final/'firmware.map')
    stages={name:measure(OUT/name/'firmware.elf') for name in ('baseline','phase-a','phase-b','phase-c','final')}
    for name in stages:
        symbols=subprocess.check_output([str(TOOL),'-S','--size-sort','-C',str(OUT/name/'firmware.elf')],text=True)
        (OUT/name/'symbols.txt').write_text(symbols)
    db=json.loads((ROOT/'compile_commands.json').read_text())
    stack=final/'stack';stack.mkdir(exist_ok=True)
    for suffix in ('e3v3se/LcdDraw.cpp','e3v3se/LcdDrawIO.cpp','e3v3se/OctoHost.cpp',
                   'lcd/dwin/creality/dwin.cpp','MarlinCore.cpp'):
        entry=next(e for e in db if e['file'].endswith(suffix))
        args=shlex.split(entry['command']);i=args.index('-o');del args[i:i+2]
        args=[a for a in args if not a.startswith('-flto')]
        target=stack/(Path(suffix).name+'.o')
        args+=['-fno-lto','-fstack-usage','-o',str(target)]
        r=subprocess.run(args,cwd=entry['directory'],text=True,capture_output=True)
        (stack/(Path(suffix).name+'.log')).write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError(r.stderr[-2000:])
    frames=[]
    for path in stack.glob('*.su'):
        for line in path.read_text().splitlines():
            function,size,kind=line.split('\t');frames.append({'function':function,'bytes':int(size),'kind':kind})
    final_symbols=(final/'symbols.txt').read_text()
    removed=['thumb_runs','thumb_open_prev','thumb_open_cur','thumb_run_emitted','OctoImageLine','CardReader::']
    result={'stages':stages,'frame_scope':'Compiler per-function frames (-fno-lto); not call-chain, ISR or runtime peak stack.',
            'frames':sorted(frames,key=lambda f:f['bytes'],reverse=True),
            'absent_from_final_elf':{s:s not in final_symbols for s in removed},
            'executor_symbols':[line for line in final_symbols.splitlines() if 'LcdDraw::state' in line]}
    (ROOT/'docs/c13-cleanup/memory.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(stages,indent=2))
if __name__=='__main__':main()
