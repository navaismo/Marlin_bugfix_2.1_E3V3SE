#!/usr/bin/env python3
"""Measure host encoding/wire counts and replay through the production executor.
No elapsed time reported by this script is a physical LCD measurement.
"""
import argparse
import ast
import base64
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import zlib
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'test'))
from test_c13_cleanup_protocol import framebuffer
from test_c13_cleanup_integration import Bridge,drawing,card,MP
from PIL import Image


def numbered(commands):
    out=[]
    for i,c in enumerate(commands,1):
        line='N{} {}'.format(i,c);check=0
        for value in line.encode():check^=value
        out.append(line+'*'+str(check)+'\n')
    return out


def legacy(pixels,chunk):
    cmds=['M9001 START']
    for y in range(96):
        for x in range(0,96,chunk):
            cmds.append('M9001 C {} {} {}'.format(y,x,''.join('{:04X}'.format(c) for c in pixels[y*96+x:y*96+min(x+chunk,96)])))
    return cmds+['M9001 END']


def hex_batches(ops):
    batches=[];b=b''
    for op in ops:
        if len(b)+len(op)>24:batches.append(b);b=b''
        b+=op
    if b:batches.append(b)
    if any(len(op)>24 for op in ops):
        # The same STRIP records are split into <=10 pixels for a 24-byte HEX batch.
        small=[]
        for op in ops:
            if op[0]!=2:small.append(op);continue
            for pos in range(0,op[3],10):
                n=min(10,op[3]-pos);small.append(bytes((2,op[1]+pos,op[2],n))+op[4+2*pos:4+2*(pos+n)])
        return hex_batches(small)
    out=[]
    for i,b in enumerate(batches):
        raw=struct.pack('>BIH',2,1,i)+b
        raw+=struct.pack('>I',zlib.crc32(b'D'+raw))
        out.append('M9001 D'+raw.hex().upper())
    return out


def counts(commands,mp):
    raw=[cmd+'\n' for cmd in commands]
    lines=numbered(commands)
    return {'commands':len(commands),'ascii_bytes':sum(map(len,raw)),
            'numbered_bytes':sum(map(len,lines)),
            'meatpack_numbered_bytes':sum(len(mp.pack_line(line)) for line in lines)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='docs/c13-cleanup/transport.json')
    args=parser.parse_args()
    drawing.secrets.randbelow=lambda upper:0  # Stable wire-byte measurements.
    output=ROOT/args.output;output.parent.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('mp_actual',MP);mp=importlib.util.module_from_spec(spec);spec.loader.exec_module(mp)
    mp.initialize();mp.set_no_spaces(True)
    exe=ROOT/'.pio/c13-cleanup/native-benchmark';exe.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['clang++','-std=c++17','-O1','-g','-fsanitize=address,undefined','-DLCD_DRAW_NATIVE_TEST',
                    str(ROOT/'test/c13_cleanup/harness.cpp'),str(ROOT/'Marlin/src/e3v3se/LcdDraw.cpp'),'-o',str(exe)],check=True)
    original=subprocess.check_output(['git','-C','/home/shaka/Projects/Python/OctoPrint-LCD_E3V3SE','show',
                                      '9d28be81958c37b8c2606e29e32648b208a0f537:octoprint_LCD_E3V3SE/__init__.py'],text=True)
    method=next(n for n in ast.walk(ast.parse(original)) if isinstance(n,ast.FunctionDef) and n.name=='send_image_to_marlin')
    namespace={};exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),'baseline_sender','exec'),namespace)
    samples={'solid':[0xF800]*9216,'alternating':[0xF800 if i%2 else 0x07E0 for i in range(9216)],
             'black':[0]*9216,'unique':list(range(1,9217)),
             'thumbnail':card.rgb565(Image.open(ROOT/'test/c13_cleanup/thumbnail.png'))}
    result={'scope':'Thumbnail-only comparison uses the same initialized black 96x96 destination and exact RGB565 pixels.',
            'timing':'Host CPU/IPC wall time only. Harness clock is simulated. Physical panel timing is unmeasured.',
            'meatpack':'Actual local OctoPrint encoder, NSP enabled; numbered N1...; mode-negotiation bytes excluded from all cases.',
            'fixtures':{}}
    for name,pixels in samples.items():
        start=time.perf_counter()
        ops=[drawing.color(0),drawing.rect(12,26,107,121)]+card.thumbnail_operations(pixels)
        prepare=time.perf_counter()-start
        bridge=Bridge(exe)
        try:
            start=time.perf_counter();bridge.client.render(ops);host_time=time.perf_counter()-start
            actual,frames=framebuffer('\n'.join(bridge.lines))
            for y in range(96):assert actual[(26+y)*240+12:(26+y)*240+108]==pixels[y*96:y*96+96]
            data_cmds=[cmd for cmd in bridge.commands if cmd.startswith('M9001 D')]
            hex_cmds=hex_batches(ops)
            foreground=sum(c!=0 for c in pixels)
            original_commands=[]
            old_self=SimpleNamespace(_printer=SimpleNamespace(is_printing=lambda:True,is_paused=lambda:False,
                    commands=lambda command,**kwargs:original_commands.append(command)),
                    _plugin_logger=SimpleNamespace(info=lambda *a:None,error=lambda *a:None))
            start=time.perf_counter();namespace['send_image_to_marlin'](old_self,pixels,'M9001');old_cpu=time.perf_counter()-start
            assert original_commands==legacy(pixels,12)
            start=time.perf_counter();encoded=[]
            for seq,data in enumerate(drawing.batches(ops)):
                encoded.append(drawing.packet('D',1,struct.pack('>H',seq)+data))
            encode_cpu=time.perf_counter()-start
            item={'baseline_sender_host_seconds':old_cpu,'new_packet_encoding_host_seconds':encode_cpu,'legacy_idle':counts(legacy(pixels,20),mp),'legacy_numbered':counts(legacy(pixels,12),mp),
                  'optimized':counts(bridge.commands[1:],mp),
                  'encoding_only':{'hex24':counts(hex_cmds,mp),'g_free_base64_42':counts(data_cmds,mp)},
                  'old_tjc_frames':foreground*2,'old_tjc_bytes':foreground*24,
                  'old_application_replies':99,'old_operations':foreground,
                  'new_tjc_frames':len(frames),'new_tjc_bytes':sum(len(f) for f,t in frames),
                  'new_application_replies':sum(line.startswith('L M9001 ACK') or line.startswith('L M9001 DONE') for line in bridge.lines),
                  'new_operations':len(ops),'prepare_host_seconds':prepare,'sender_and_executor_host_seconds':host_time,
                  'pixel_comparison':'exact; all 9216 pixels match','physical_render_seconds':None}
            result['fixtures'][name]=item
        finally:bridge.close()
    ops=card.card_operations(samples['thumbnail']);bridge=Bridge(exe)
    try:
        start=time.perf_counter();bridge.client.render(ops);elapsed=time.perf_counter()-start
        actual,frames=framebuffer('\n'.join(bridge.lines))
        result['complete_card']={**counts(bridge.commands[1:],mp),'operations':len(ops),'tjc_frames':len(frames),
                                 'tjc_bytes':sum(len(f) for f,t in frames),'host_seconds':elapsed,'physical_seconds':None}
        rgb=[((p>>11&31)*255//31,(p>>5&63)*255//63,(p&31)*255//31) for p in actual]
        image=Image.new('RGB',(240,320));image.putdata(rgb)
        image.crop((0,25,240,123)).save(output.parent/'host-card.png')
    finally:bridge.close()
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(output)
    for name,item in result['fixtures'].items():
        print(name,item['legacy_numbered']['numbered_bytes'],'->',item['optimized']['numbered_bytes'],
              'TJC',item['old_tjc_frames'],'->',item['new_tjc_frames'])
if __name__=='__main__':main()
