#!/usr/bin/env python3
"""Check the workflow's single PLR switch and its actual config edits."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[1]


def enabled(text, macro):
    return bool(re.search(r'^\s*#define\s+' + macro + r'\b', text, re.M))


def main():
    workflow = yaml.load((ROOT/'.github/workflows/build-marlin.yml').read_text(), Loader=yaml.BaseLoader)
    inputs = workflow['on']['workflow_dispatch']['inputs']
    assert inputs['power_loss_recovery']['type'] == 'boolean'
    assert inputs['power_loss_recovery']['default'] == 'false'
    assert 'dwin_plr_menu' not in inputs
    apply_step = next(s['run'] for s in workflow['jobs']['build']['steps'] if s.get('name') == 'Apply firmware options')
    pairs = re.findall(r'(POWER_LOSS_RECOVERY|DWIN_PLR_MENU)=\$\{\{\s*inputs\.([a-z_]+)\s*\}\}', apply_step)
    assert dict(pairs) == {'POWER_LOSS_RECOVERY':'power_loss_recovery', 'DWIN_PLR_MENU':'power_loss_recovery'}
    committed = (ROOT/'Marlin/Configuration_adv.h').read_text()
    assert not enabled(committed, 'POWER_LOSS_RECOVERY')
    assert not enabled(committed, 'DWIN_PLR_MENU')
    with tempfile.TemporaryDirectory(prefix='plr-build-option-') as folder:
        root = Path(folder)
        (root/'Marlin').mkdir()
        for name in ('Configuration.h','Configuration_adv.h'):
            (root/'Marlin'/name).write_bytes((ROOT/'Marlin'/name).read_bytes())
        def apply(*args):
            subprocess.run([sys.executable,str(ROOT/'.github/scripts/apply_marlin_options.py'),*args],
                           cwd=root,check=True,capture_output=True,text=True)
            return (root/'Marlin/Configuration_adv.h').read_text()
        for value in ('true','false','true','false'):
            result = apply(*(f'{macro}={value}' for macro, _ in pairs))
            assert enabled(result,'POWER_LOSS_RECOVERY') == (value == 'true')
            assert enabled(result,'DWIN_PLR_MENU') == (value == 'true')
        # The configuration helper must refuse the menu without base recovery.
        result = apply('POWER_LOSS_RECOVERY=false','DWIN_PLR_MENU=true')
        assert not enabled(result,'POWER_LOSS_RECOVERY') and not enabled(result,'DWIN_PLR_MENU')
    print('PASS single workflow PLR switch: default off, recovery + menu on/off together, dependency enforced')


if __name__ == '__main__':
    main()
