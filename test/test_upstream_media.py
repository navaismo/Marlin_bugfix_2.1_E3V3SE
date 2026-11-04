#!/usr/bin/env python3
"""Exercise the new production SD mount/retry flow and recovery precedence."""
from pathlib import Path
import subprocess
import tempfile
from test_dwin_input_shaping import function

ROOT=Path(__file__).resolve().parents[1]
STUBS=r'''
#include <cassert>
#include <cstdint>
#include <deque>
#include <string>
#include "Marlin/src/core/macros.h"
#define HAS_SD_DETECT 1
#define HAS_USB_FLASH_DRIVE 0
#define HAS_MULTI_VOLUME 0
#define ONE_CLICK_PRINT 1
#define POWER_LOSS_RECOVERY 1
#define NO_SD_AUTOSTART 1
#define SD_SPI_SPEED 4
#define SD_SS_PIN 5
#define PENDING(N,T) (int32_t((N)-(T))<0)
#define DEBUG_SECTION(...)
#define DEBUG_ECHOLNPGM(...)
#define O_READ 0
using millis_t=uint32_t;
uint32_t now=100;
millis_t millis(){return now;}
millis_t next_millis(millis_t n){return n ? n : 1;}
void safe_delay(int ms){now+=ms;}
enum MediaPresence:int8_t {MEDIA_BOOT=-1,INSERT_NONE=0,INSERT_MEDIA=1};
enum MountState:uint8_t {MOUNT_IDLE,MOUNT_SETTLE,MOUNT_INIT,MOUNT_INIT_LCD};
MountState mount_state=MOUNT_IDLE;
millis_t mount_settle_ms=0;
bool mount_alerted=false;
int alerts=0,previews=0,recovery_checks=0,releases=0,starts=0,steps=0,opens=0;
bool inserted=false,boot_mount_ok=true,checkpoint=false;
std::deque<int> results;
struct Driver {
 void initStart(int,int){++starts;}
 int8_t initStep(){++steps;assert(!results.empty());auto r=results.front();results.pop_front();return r;}
} sd;
struct File {
 bool isOpen(){return false;}
 void close(){}
 bool open(File*,const char*,int){++opens;return checkpoint;}
};
struct {
 bool detected(){return true;}
 void reset_alert_level(){}
 void media_changed(MediaPresence,MediaPresence){}
} ui;
struct {
 File file; const char *filename="/PLR";
 bool check(){++recovery_checks;return checkpoint;}
} recovery;
struct CardReader {
 struct {bool mounted=false,workDirIsRoot=true;} flag;
 int nrItems=0;File root;Driver *driver=&sd;
 bool isMounted(){return flag.mounted;}
 bool isInserted(){return inserted;}
 bool isSDCardInserted(){return inserted;}
 void mount(bool alert){flag.mounted=boot_mount_ok;if(alert&&!flag.mounted)++alerts;}
 void mount_finish(bool success,bool alert){flag.mounted=success;if(alert&&!success)++alerts;}
 void release(){flag.mounted=false;++releases;}
 bool one_click_check(){assert(flag.mounted);++previews;return true;}
 bool mount_async(bool);
 void manage_media();
 bool jobRecoverFileExists();
} card;
'''
MAIN=r'''
int main(int argc,char**argv) {
 const std::string scenario=argv[1];
 if(scenario=="boot-recovery") {
   inserted=true;checkpoint=true;card.manage_media();
   assert(card.isMounted() && recovery_checks==1 && previews==0);
 }
 else if(scenario=="boot-failure") {
   inserted=true;boot_mount_ok=false;
   card.manage_media();now+=1001;card.manage_media();now+=1001;card.manage_media();
   assert(!card.isMounted() && previews==0 && recovery_checks==0 && alerts==1);
 }
 else {
   card.manage_media(); // Boot without card.
   inserted=true;results={0,1};
   card.manage_media();assert(starts==0 && previews==0);
   now+=501;card.manage_media();assert(starts==1 && previews==0);
   card.manage_media();assert(!card.isMounted() && previews==0);
   if(scenario=="remove-during-mount") {
     inserted=false;card.manage_media();assert(!card.isMounted() && previews==0);
   }
   else {
     card.manage_media();assert(card.isMounted() && previews==1 && recovery_checks==0);
     card.manage_media();assert(previews==1);
     inserted=false;card.manage_media();assert(!card.isMounted() && releases==1);
   }
 }
 card.flag.mounted=false;checkpoint=true;opens=0;
 assert(!card.jobRecoverFileExists() && opens==0);
 card.flag.mounted=true;assert(card.jobRecoverFileExists() && opens==1);
}
'''
if __name__=='__main__':
    code=(ROOT/'Marlin/src/sd/cardreader.cpp').read_text()
    funcs='\n'.join(function(code,prefix) for prefix in (
        'bool CardReader::mount_async(', 'void CardReader::manage_media()',
        'bool CardReader::jobRecoverFileExists()'))
    with tempfile.TemporaryDirectory() as folder:
        src,exe=Path(folder)/'media.cpp',Path(folder)/'media'
        src.write_text(STUBS+funcs+MAIN)
        subprocess.run(['g++','-std=c++17','-I',str(ROOT),str(src),'-o',str(exe)],check=True)
        for scenario in ('insert','remove-during-mount','boot-recovery','boot-failure'):
            subprocess.run([str(exe),scenario],check=True)
    print('PASS async SD insertion/removal, boot retry failure, One Click Print and mounted-only PLR access')
