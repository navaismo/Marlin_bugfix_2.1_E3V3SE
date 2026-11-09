"""Use the actual Python sender and production MCU executor together."""
import base64
import importlib
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import unittest
from test_c13_cleanup_protocol import ROOT, framebuffer

PLUGIN=Path(os.environ.get('M9001_PLUGIN_ROOT','/home/shaka/Projects/Python/OctoPrint-LCD_E3V3SE'))
MP=Path(os.environ.get('M9001_MEATPACK_PATH','/home/shaka/Projects/Python/OctoPrint-MeatPack/OctoPrint_MeatPack/meatpack.py'))
package=types.ModuleType('cleanup_integration');package.__path__=[str(PLUGIN/'octoprint_LCD_E3V3SE')]
sys.modules[package.__name__]=package
drawing=importlib.import_module(package.__name__+'.drawing')
card=importlib.import_module(package.__name__+'.print_card')


class Bridge:
    def __init__(self,exe):
        self.process=subprocess.Popen([str(exe)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,
                                      env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'),bufsize=1)
        self.lines=[];self.commands=[]
        self.client=drawing.DrawingClient(self.send)
        self.client.connected()
    def pump(self,text):
        self.process.stdin.write(text+'\nZ\n');self.process.stdin.flush()
        while True:
            line=self.process.stdout.readline().rstrip('\n')
            if line=='Z':return
            if not line:raise RuntimeError('MCU harness stopped')
            self.lines.append(line)
            if line.startswith('L '):self.client.received(line[2:])
    def send(self,command):
        self.commands.append(command)
        self.pump('C '+command[6:]+'\nT '+('150' if command.startswith('M9001 E') else '180'))
    def close(self):
        self.process.stdin.close();self.process.wait(timeout=2);self.process.stdout.close()
        assert self.process.returncode==0


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='c13-integration-')
        cls.exe=Path(cls.folder.name)/'draw'
        subprocess.run(['clang++','-std=c++17','-O1','-g','-fsanitize=address,undefined',
                        '-DLCD_DRAW_NATIVE_TEST',str(ROOT/'test/c13_cleanup/harness.cpp'),
                        str(ROOT/'Marlin/src/e3v3se/LcdDraw.cpp'),'-o',str(cls.exe)],check=True)
    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()

    def test_exact_full_card_real_thumbnail_and_backgrounds(self):
        from PIL import Image
        images=[Image.new('RGB',(96,96),(255,0,0)),Image.new('RGBA',(192,192),(0,0,0,0)),
                Image.open(ROOT/'test/c13_cleanup/thumbnail.png')]
        for image in images:
            with self.subTest(size=image.size):
                pixels=card.rgb565(image);bridge=Bridge(self.exe)
                try:
                    bridge.client.render(card.card_operations(pixels))
                    actual,frames=framebuffer('\n'.join(bridge.lines))
                    for y in range(96):
                        self.assertEqual(actual[(26+y)*240+12:(26+y)*240+108],pixels[y*96:y*96+96])
                    # Host output preserves the native progress and title, with all four frame sides intact.
                    for x in range(10,110):
                        self.assertEqual(actual[25*240+x],card.GREEN)
                        self.assertEqual(actual[122*240+x],card.GREEN)
                    for y in range(25,123):
                        self.assertEqual(actual[y*240+10],card.GREEN)
                        self.assertEqual(actual[y*240+109],card.GREEN)
                        self.assertEqual(actual[y*240+125:(y+1)*240],[0x1234]*115)
                    self.assertEqual(actual[24*240+10],0x1234)
                    self.assertTrue(any('DONE' in line for line in bridge.lines))
                    self.assertEqual(actual[123*240],0x1234)
                    self.assertFalse(any(cmd.startswith('M9001 U2') for cmd in bridge.commands))
                finally:bridge.close()

    def test_high_entropy_strip_fallback_matches_every_pixel(self):
        pixels=list(range(1,9217));ops=card.card_operations(pixels)
        self.assertTrue(any(op[0]==2 for op in ops))
        bridge=Bridge(self.exe)
        try:
            bridge.client.render(ops)
            actual,frames=framebuffer('\n'.join(bridge.lines))
            for y in range(96):
                self.assertEqual(actual[(26+y)*240+12:(26+y)*240+108],pixels[y*96:y*96+96])
            self.assertTrue(any('DONE' in line for line in bridge.lines))
        finally:bridge.close()

    def test_native_abort_and_later_new_session(self):
        bridge=Bridge(self.exe)
        try:
            bridge.pump('G M 600')
            bridge.client.render(card.card_operations(None))
            self.assertTrue(any('DONE' in line for line in bridge.lines))
            bridge.pump('A 0')
            with self.assertRaises(RuntimeError):
                bridge.client.render(card.card_operations(None))
        finally:bridge.close()

    def test_actual_meatpack_round_trip_both_modes_and_numbered_checksums(self):
        spec=importlib.util.spec_from_file_location('actual_cleanup_meatpack',MP)
        mp=importlib.util.module_from_spec(spec);spec.loader.exec_module(mp);mp.initialize()
        header=(ROOT/'Marlin/src/feature/meatpack.h').read_text().split('// Implement the MeatPack serial class')[0]
        header=re.sub(r'^#include[^\n]*|^#pragma once','',header,flags=re.M)
        decoder=re.sub(r'^#include[^\n]*','',(ROOT/'Marlin/src/feature/meatpack.cpp').read_text(),flags=re.M)
        prefix='''
#include <iostream>
#include <cstdint>
#include "Marlin/src/core/macros.h"
#define HAS_MEATPACK 1
#define EMERGENCY_PARSER 0
#define SERIAL_ECHO(...)
#define DEBUG_ECHOLNPGM(...)
#define PORT_REDIRECT(...)
using serial_index_t=int;
'''
        main='''int main(){MeatPack d;unsigned v;while(std::cin>>std::hex>>v){d.handle_rx_char(v,0);char b[2];auto n=d.get_result_char(b);std::cout.write(b,n);}}'''
        source=Path(self.folder.name)/'mp.cpp';exe=source.with_suffix('')
        source.write_text(prefix+header+decoder+main)
        subprocess.run(['clang++','-std=c++17','-O1','-fsanitize=address,undefined','-I',str(ROOT),str(source),'-o',str(exe)],check=True)
        commands=['M105','M115','M108','M410','M876 S0','M9001 Q']
        commands += [drawing.packet('D',123,bytes((0,1))+bytes((i+j)%256 for j in range(42))) for i in range(256)]
        for cmd in commands[6:]:self.assertNotIn('G',cmd)
        lines=[]
        for i,cmd in enumerate(commands):
            line='N{} {}'.format(2147483000+i,cmd);check=0
            for c in line.encode():check^=c
            line+='*'+str(check)+'\n';self.assertLessEqual(len(line.rstrip()),95);lines.append(line)
        for compact in (False,True):
            mp.set_no_spaces(compact)
            packed=bytes([255,255,251,255,255,247 if compact else 246])+b''.join(bytes(mp.pack_line(line)) for line in lines)
            result=subprocess.run([str(exe)],input=' '.join('{:02X}'.format(c) for c in packed),text=True,capture_output=True,
                                  env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'),check=True)
            self.assertEqual(result.stdout,''.join(lines))
        # Demonstrate the reason standard Base64 cannot be used unchanged.
        bad='M9001 DG2xgAAAA\n'
        self.assertNotEqual(mp._unified_method(bad),bad)

if __name__=='__main__':unittest.main()
