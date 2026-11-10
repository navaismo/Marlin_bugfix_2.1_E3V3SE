#!/usr/bin/env python3
"""Focused cleanup regressions. Does not flash, install, reset or change branches."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--plugin-root',type=Path,default=Path('/home/shaka/Projects/Python/OctoPrint-LCD_E3V3SE'))
args=p.parse_args();plugin=args.plugin_root.resolve()
logs=ROOT/'.pio/c13-cleanup/logs';logs.mkdir(parents=True,exist_ok=True)
cases=[(name,[sys.executable,str(ROOT/'test'/(name+'.py'))],ROOT) for name in (
 'test_c13_cleanup_protocol','test_c13_cleanup_integration','test_c13_cleanup_ui','test_dwin_host_status',
 'test_dwin_advanced_pause','test_dwin_pause_purge','test_dwin_thumbnail_progress',
 'test_dwin_runout_owner','test_dwin_calibration_error','test_dwin_move_exit','test_autooffset_safety')]
cases += [('profile',[sys.executable,'buildroot/share/e3v3se/config_profile.py','--profile','c13_octoprint','check'],ROOT),
          ('eeprom',[sys.executable,'buildroot/share/e3v3se/check_eeprom_upgrade.py','--ref','244be9d8012cca3c4eb1efbfa084f1f9df0fa1d4','--output','docs/c13-cleanup/eeprom.json'],ROOT),
          ('plugin_host',[sys.executable,'-m','unittest','discover','-s','tests'],plugin),
          ('plugin_frontend',['node','tests/test_purge_frontend.js'],plugin)]
results=[]
for name,cmd,cwd in cases:
    r=subprocess.run(cmd,cwd=cwd,env=dict(os.environ,M9001_PLUGIN_ROOT=str(plugin)),text=True,capture_output=True)
    output=r.stdout+r.stderr;(logs/(name+'.log')).write_text(output)
    results.append({'name':name,'returncode':r.returncode,'command':cmd,'cwd':str(cwd),'log':str(logs/(name+'.log'))})
    print(('PASS ' if not r.returncode else 'FAIL ')+name,flush=True)
(ROOT/'docs/c13-cleanup/tests.json').write_text(json.dumps(results,indent=2)+'\n')
sys.exit(any(r['returncode'] for r in results))
