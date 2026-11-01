#!/usr/bin/env python3
"""Run the actual PLR submenu, settings storage, and recovery heating code."""
import re
import subprocess
import tempfile
from pathlib import Path
import test_dwin_powerloss as base

ROOT = base.ROOT
SETTINGS = (ROOT/'Marlin/src/e3v3se/PLRSettings.cpp').read_text()
HEADER = (ROOT/'Marlin/src/e3v3se/PLRSettings.h').read_text()

EXTRA = r'''
#include <array>
#include <cmath>
#define PLR_HEAT_NOZZLE_ON_REBOOT 0
#define POWER_LOSS_ZRAISE 5
#define POWER_LOSS_MIN_Z_CHANGE 0.05f
#define _MAX(A,B) std::max(float(A),float(B))
#define LIMIT(V,L,H) do{if((V)<(L))(V)=(L);if((V)>(H))(V)=(H);}while(0)
constexpr int Color_White=65535,Color_Bg_Black=0,VALUERANGE_X=172;
using select_t=Selection;
ENCODER_DiffState Encoder_ReceiveAnalyze(){return get_encoder_state();}
void Draw_Title(const char*){}
void Draw_Control_Menu();
static void Goto_PLRSettings();
template<class...Args> void DWIN_Draw_FloatValue(Args...){}
template<class...Args> void DWIN_Draw_IntValue(Args...){}
struct BL24CXX {
 inline static std::array<uint8_t,2048> bytes;
 inline static int budget=-1;
 static void read(uint16_t addr,uint8_t *out,uint16_t n){memcpy(out,bytes.data()+addr,n);}
 static void writeOneByte(uint16_t addr,uint8_t value){if(budget!=0){bytes[addr]=value;if(budget>0)--budget;}}
 static void write(uint16_t addr,uint8_t *in,uint16_t n){for(uint16_t i=0;i<n;++i)writeOneByte(addr+i,in[i]);}
};
'''

TESTS = r'''
void menu_input(ENCODER_DiffState state){event=state;HMI_PLRSettings();}
void edit_input(ENCODER_DiffState state){event=state;HMI_PLRValue();}
void choose(uint8_t item){
 while(select_plr.now<item)menu_input(ENCODER_DIFF_CW);
 while(select_plr.now>item)menu_input(ENCODER_DIFF_CCW);
 assert(checkkey==PowerLossSettings);
}
int main(){
 BL24CXX::bytes.fill(0xFF);
 // Loading firmware for the first time uses defaults, preserving calibration.
 plrSettings.load();assert(plrSettings.valid());
 assert(plrSettings.heat_bed && !plrSettings.heat_nozzle && plrSettings.zraise_tenths==50);
 assert(plrSettings.save_z_hundredths==5);
 const auto original=BL24CXX::bytes;
 checkkey=Control;select_control.set(CONTROL_CASE_PLR);index_control=CONTROL_CASE_PLR;
 event=ENCODER_DIFF_ENTER;HMI_Control();assert(checkkey==PowerLossSettings);
 choose(PLR_ENABLE);menu_input(ENCODER_DIFF_ENTER);assert(!recovery.enabled);
 menu_input(ENCODER_DIFF_ENTER);assert(recovery.enabled);
 choose(PLR_HEAT_BED);menu_input(ENCODER_DIFF_ENTER);assert(!plrSettings.heat_bed);
 choose(PLR_HEAT_NOZZLE);menu_input(ENCODER_DIFF_ENTER);assert(plrSettings.heat_nozzle);
 // Editing every numeric option bounds accelerated encoder input at both ends.
 for(uint8_t item:{PLR_BED_EXTRA,PLR_AUTO_TEMP,PLR_ZRAISE,PLR_PURGE,PLR_SAVE_STEP}){
  choose(item);menu_input(ENCODER_DIFF_ENTER);assert(checkkey==PowerLossValue && EncoderRate.enabled);
  EncoderRate.encoderMoveValue=100000;
  for(int n=0;n<8;++n)edit_input(ENCODER_DIFF_CW);
  assert(plr_edit_value==PLR_Value_Max(item));
  edit_input(ENCODER_DIFF_ENTER);assert(checkkey==PowerLossSettings && !EncoderRate.enabled);
  assert(PLR_Menu_Value(item)==PLR_Value_Max(item));
  menu_input(ENCODER_DIFF_ENTER);
  for(int n=0;n<8;++n)edit_input(ENCODER_DIFF_CCW);
  edit_input(ENCODER_DIFF_ENTER);
  assert(PLR_Menu_Value(item)==(item==PLR_SAVE_STEP?1:0));
 }
 // Knob edits change settings only, without heating or starting a print.
 assert(thermalManager.target==0 && thermalManager.hotend==0 && recovery.resumes==0);
 assert(queue.command.empty());
 plrSettings.heat_bed=plrSettings.heat_nozzle=1;
 plrSettings.bed_extra=7;plrSettings.zraise_tenths=73;plrSettings.purge_tenths=125;plrSettings.save_z_hundredths=9;
 choose(PLR_SAVE);menu_input(ENCODER_DIFF_ENTER);assert(settings.saves==1);
 const PLRSettings saved=plrSettings;
 plrSettings.reset();plrSettings.load();assert(memcmp(&saved,&plrSettings,sizeof(saved))==0);
 assert(fabs(plrSettings.zraise()-7.3f)<0.001f && fabs(plrSettings.purge()-12.5f)<0.001f && fabs(plrSettings.save_step()-0.09f)<0.001f);
 for(size_t i=0;i<original.size();++i)
  if(i<0x20 || i>=0x30)assert(BL24CXX::bytes[i]==original[i]);
 // Fault injection: partial writes never become a valid new settings record.
 for(int cutoff=0;cutoff<17;++cutoff){
  BL24CXX::budget=-1;plrSettings=saved;assert(plrSettings.save());
  plrSettings.bed_extra=8;BL24CXX::budget=cutoff;
  assert(!plrSettings.save());
  plrSettings.load();assert(plrSettings.valid() && plrSettings.bed_extra!=8);
 }
 BL24CXX::budget=-1;plrSettings=saved;assert(plrSettings.save());
 BL24CXX::bytes[0x26]^=0x80;
 plrSettings.load();assert(plrSettings.valid() && plrSettings.zraise_tenths==50);
 // M1000 S applies the saved heating choices only while recovery is pending.
 plrSettings=saved;recovery.valid_data=true;
 recovery.info.target_temperature_bed=60;recovery.info.target_temperature[0]=205;
 recovery.bed_temp_threshold=0;parser.S=true;GcodeSuite::M1000();
 assert(recovery.ui_flag_resume && thermalManager.target==67 && thermalManager.hotend==205);
 Goto_PowerLossRecovery();event=ENCODER_DIFF_CCW;HMI_PowerLossRecovery();
 event=ENCODER_DIFF_ENTER;HMI_PowerLossRecovery();
 assert(thermalManager.target==0 && thermalManager.hotend==0);
 recovery.info.target_temperature_bed=0;recovery.info.target_temperature[0]=0;
 plrSettings.preheat(true);assert(thermalManager.target==0 && thermalManager.hotend==0);
 recovery.info.target_temperature_bed=130;recovery.info.target_temperature[0]=400;
 plrSettings.preheat(true);assert(thermalManager.target==110 && thermalManager.hotend==260);
 plrSettings.preheat(false);
 // Return from a scrolled submenu to the correct row in Control.
 Goto_PLRSettings();choose(PLR_SAVE);
 choose(PLR_BACK);menu_input(ENCODER_DIFF_ENTER);
 assert(checkkey==Control && select_control.now==CONTROL_CASE_PLR && index_control==CONTROL_CASE_PLR);
 std::cout<<"PASS advanced PLR menu, accelerated edit bounds, no unintended heating, EEPROM reload/CRC/torn writes, calibration preservation, M1000 preheat/cancel\n";
}
'''


def main():
    stubs=base.STUBS.replace('#define DWIN_PLR_MENU 0','#define DWIN_PLR_MENU 1')
    stubs=stubs.replace('PowerLossResume,PrintProcess','PowerLossResume,PowerLossSettings,PowerLossValue,PrintProcess')
    stubs=stubs.replace('struct {bool enabled=false;} EncoderRate;', 'struct {bool enabled=false;int encoderMoveValue=1;} EncoderRate;')
    stubs=stubs.replace('struct {bool save(){return true;} bool load(){return true;}} settings;', 'struct SettingsStub {int saves=0;bool save();bool load(){return true;}} settings;')
    stubs=stubs.replace('int target=0,current=20;', 'int target=0,current=20,hotend=0;\n void setTargetHotend(int v,int){hotend=v;}\n int hotend_max_target(int){return 260;}')
    stubs=stubs.replace('celsius_t target_temperature_bed=60;', 'celsius_t target_temperature_bed=60,target_temperature[1]={205};')
    struct=HEADER[HEADER.index('  struct PLRSettings'):HEADER.rindex('#endif')]
    settings='\n'.join(line for line in SETTINGS.splitlines() if not line.startswith('#include'))
    controls=base.DWIN[base.DWIN.index('#define CONTROL_CASE_TEMP'):base.DWIN.index('#define LEVEL_CASE_BEDVIS')]
    start=base.DWIN.index('#if ENABLED(DWIN_PLR_MENU)\n  enum PLRMenuItem')
    end=base.DWIN.index('#if ENABLED(POWER_LOSS_RECOVERY)\n  static void Draw_PLR_Selection',start)
    menu=base.DWIN[start:end]
    drawing=base.function(base.DWIN,'void Draw_Control_Menu()')
    handler=base.function(base.DWIN,'void HMI_Control()')
    icons=sorted(set(re.findall(r'\b(?:ICON_|LANGUAGE_)\w+',drawing+handler+menu)))
    helpers='\n'.join(base.function(base.DWIN,p) for p in (
        'void Item_Control_PLR(', 'static void Draw_PLR_Selection(',
        'static void Goto_PowerLossRecovery()', 'static void HMI_PowerLossRecovery()',
        'void DWIN_PowerLossResume()', 'void one_click_print()',))
    core='\n'.join(base.function(base.PLR,p) for p in (
        'void PrintJobRecovery::enable(', 'void PrintJobRecovery::changed()',
        'bool PrintJobRecovery::check()', 'void PrintJobRecovery::cancel()',))
    # Verify that M500/M501/M502 and checkpoint/purge use the editable values.
    storage=(ROOT/'Marlin/src/module/settings.cpp').read_text()
    for call in ('plrSettings.save()', 'plrSettings.load()', 'plrSettings.reset()'):
        assert call in storage
    assert 'plrSettings.save_step()' in base.PLR and 'plrSettings.zraise()' in base.PLR and 'plrSettings.purge()' in base.PLR
    cpp='enum {'+','.join(icons)+'};\n'+stubs+EXTRA+struct+settings
    cpp+='\nbool SettingsStub::save(){++saves;return plrSettings.save();}\n'
    cpp+=controls+helpers+drawing+handler+menu+core+base.function(base.M1000,'void GcodeSuite::M1000()')+TESTS
    with tempfile.TemporaryDirectory(prefix='plr-settings-') as folder:
        source,binary=Path(folder)/'test.cpp',Path(folder)/'test'
        source.write_text(cpp)
        subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)


if __name__=='__main__':
    main()
