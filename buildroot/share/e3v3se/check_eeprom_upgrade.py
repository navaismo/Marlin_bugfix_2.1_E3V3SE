#!/usr/bin/env python3
"""Compare ARM EEPROM layout and active serialization with a prior firmware revision.

Requires pyelftools and a PlatformIO compile_commands.json for the active profile.
Generate it with pio run -e <target> -t compiledb. No firmware is flashed or linked.
"""
from pathlib import Path
import subprocess, json, shlex, tempfile, re, argparse
from elftools.elf.elffile import ELFFile

cli=argparse.ArgumentParser()
cli.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3])
cli.add_argument('--ref',required=True,help='Previous compatible firmware commit')
cli.add_argument('--database',type=Path,help='compile_commands.json from a matching build/profile')
cli.add_argument('--output',type=Path,default=None)
args=cli.parse_args(); root=args.root
path='Marlin/src/module/settings.cpp'
old=subprocess.check_output(['git','show',f'{args.ref}:{path}'],cwd=root,text=True)
new=(root/path).read_text()
version_pattern = r'^#define EEPROM_VERSION "([^"]+)"'
old_version = re.search(version_pattern, old, re.M)[1]
new_version = re.search(version_pattern, new, re.M)[1]
assert new_version == old_version, (old_version, new_version)
def schema(text):
 return text[text.index('typedef struct SettingsDataStruct {'):text.index('} SettingsData;')+len('} SettingsData;')]
old_schema=schema(old).replace('SettingsDataStruct','OldSettingsDataStruct').replace('} SettingsData;','} OldSettingsData;')
needle='} SettingsData;'
injected=new.replace(needle,needle+'\n'+old_schema+'''
__attribute__((used)) volatile SettingsData e3v3se_new_layout;
__attribute__((used)) volatile OldSettingsData e3v3se_old_layout;
''',1)
db=json.loads((args.database or root/'compile_commands.json').read_text())
entry=next(e for e in db if Path(e['file']).as_posix().endswith(path))
command=shlex.split(entry['command'])
compiler=command[0]
flags=[];skip=False
for i,arg in enumerate(command[1:]):
 if skip:skip=False;continue
 if arg in ('-o','-MF','-MT','-MQ'):
  skip=True;continue
 if arg in ('-c','-flto','-MMD','-MD','-MP'):continue
 if arg.endswith('/settings.cpp') or arg==path:continue
 if arg.startswith('-I') and not Path(arg[2:]).is_absolute():
  arg='-I'+str(Path(entry['directory'])/arg[2:])
 flags.append(arg)
flags += ['-I'+str(root/'Marlin/src/module'),'-fno-lto','-g3']
with tempfile.TemporaryDirectory(prefix='eeprom-upgrade-') as folder:
 folder=Path(folder); source=folder/'compare.cpp'; obj=folder/'compare.o'
 source.write_text(injected)
 r=subprocess.run([compiler,*flags,'-c',str(source),'-o',str(obj)],cwd=root,text=True,capture_output=True)
 if r.returncode:
  print(r.stderr[-5000:]);raise SystemExit(r.returncode)
 manifests={}
 with obj.open('rb') as file:
  dwarf=ELFFile(file).get_dwarf_info()
  for cu in dwarf.iter_CUs():
   for die in cu.iter_DIEs():
    name=die.attributes.get('DW_AT_name')
    if die.tag!='DW_TAG_structure_type' or not name or name.value not in (b'SettingsDataStruct',b'OldSettingsDataStruct'):continue
    if 'DW_AT_byte_size' not in die.attributes:continue
    members=[]
    for child in die.iter_children():
     if child.tag=='DW_TAG_member':
      a=child.attributes
      members.append([a['DW_AT_name'].value.decode(),a['DW_AT_data_member_location'].value])
    manifests[name.value.decode()]={'size':die.attributes['DW_AT_byte_size'].value,'members':members}
 assert len(manifests)==2,manifests.keys()
 assert manifests['SettingsDataStruct']==manifests['OldSettingsDataStruct'], json.dumps(manifests,indent=2)
 traces={}
 for label,body in [('old',old),('new',new)]:
  # Replace only serialization macros to reveal the active write/read sequence.
  trace='\n#undef EEPROM_WRITE\n#undef EEPROM_READ\n'
  trace+='#define EEPROM_WRITE(...) E3V3SE_WRITE_TRACE(#__VA_ARGS__)\n#define EEPROM_READ(...) E3V3SE_READ_TRACE(#__VA_ARGS__)\n#undef EEPROM_READ_ALWAYS\n#define EEPROM_READ_ALWAYS(...) E3V3SE_READ_ALWAYS_TRACE(#__VA_ARGS__)\n'
  index=body.index('bool MarlinSettings::save()')
  body=body[:index]+trace+body[index:]
  source.write_text(body)
  p=subprocess.run([compiler,*flags,'-E','-P',str(source)],cwd=root,text=True,capture_output=True)
  if p.returncode:
   print(p.stderr[-2500:]);raise SystemExit(p.returncode)
  traces[label]=re.findall(r'E3V3SE_(?:WRITE|READ|READ_ALWAYS)_TRACE\(".*?"\)',p.stdout)
 assert traces['old']==traces['new'],json.dumps(traces,indent=2)
 result={'reference':args.ref,'layout':manifests['SettingsDataStruct'],'serialization':traces['new'],'version':new_version}
 if args.output: args.output.write_text(json.dumps(result,indent=2)+'\n')
 print('PASS EEPROM '+new_version+':',result['layout']['size'],'bytes;',len(result['layout']['members']),'fields;',len(traces['new']),'serialization operations match',args.ref)
