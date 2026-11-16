# Host pause and M117 follow-up

Date: 2026-11-09. Firmware branch c13_octoprint_cleanup, starting HEAD
5fa34e8388e400b6852bebe7d4d2238ae06ef683. Plugin branch main_cleanup.
Existing Version.h, DWIN popup-color and plugin working-tree edits were retained.

The LCD pause flag previously changed only through encoder actions. Host resume
left it set, and encoder highlights consulted a different pause source. The
plugin now sends M9000 R1/R0 on PrintPaused/PrintResumed. Marlin synchronizes the
UI flag and restores the appropriate native icon/title when the card is visible.
Tune and safety dialogs stay open. Returning uses the updated state. No S1 or
thumbnail redraw is sent, and firmware/filament pauses are not released.

M117 previously opened a full info window and disabled host UI refresh. With an
active host card it now replaces only the title for 15 seconds, restarting the
expiry on subsequent messages. The existing scrolling-title buffer is reused;
the original job title is untouched. A bounded 30-character window scrolls long
messages. EachMomentUpdate restores the filename without waiting/blocking or
requiring encoder input. Modal screens are not overwritten. MAIN, new-card and
finish paths clear pending messages; idle still uses the native info/Back window.
The Progress caption remains disabled.

M117 title messages now use blue, including scrolling, and restore the yellow
filename after 15 seconds. Complete `Print cancelled/canceled`, `Printing
cancelled/canceled` and `Impresion/Impresión cancelada` notices request host
cancellation through the existing cancel path, abort the print through MarlinUI,
clear paused/render/message state and return to MAIN. Matching ignores ASCII
case, surrounding spaces and trailing periods/exclamation marks. Other messages
remain informational. Repeated notices while idle return to MAIN without sending
another cancellation request.

## Validation

- test_dwin_host_status.py compiles the actual title/pause/M117/encoder functions
  and verifies print/paused messages, exact expiry, replacement, millisecond wrap,
  long text, Tune/safety return, idle info, native icon changes and unchanged
  progress/layers/remaining time. These are native UI checks; physical validation remains below.
- test_c13_cleanup_ui.py covers real M9000 R dispatch and preserves the legacy
  non-v2 controls. Its old caption expectation now matches the disabled call.
- 14 ASan/UBSan protocol tests, 4 sender/executor integration tests, existing
  pause/purge/runout/calibration/thumbnail/navigation/AutoOffset regressions and
  EEPROM/frontend checks pass.
- All 66 plugin cases pass in the local offline OctoPrint container with cached
  Pillow. The two new cases cover event-only R commands, no S1/reset and retention
  of firmware prompt ownership. Nothing was installed on the host or printer.
- Profile check reports Configuration_adv.h out of sync. Both configuration files
  exactly match starting HEAD, so this predates the change. No config/profile
  rewrite was performed.

Current build: STM32F103RET6_creality, firmware-20261109-173239.bin;
23208 bytes static RAM (35.4%), 229268 bytes Flash (46.3% of application space).
This uses today's configuration, not the older 2026-11-08 cleanup snapshot.
Peak runtime stack/heap remains unmeasured.

Modified firmware files: OctoHost.cpp/h (R dispatch and declarations), dwin.cpp
(native pause state, title lifecycle and M117 routing), two native UI tests and
the validation runner, plus documentation. Plugin changes: __init__.py (events),
test_print_lifecycle.py (regressions), docs/host-only-rendering.md (protocol use).

On hardware, pause on the LCD and resume in OctoPrint; confirm the Pause icon,
encoder selection, filename and progress. Repeat host pause/LCD resume. Send
M117 during printing, while paused and in Tune/M600, then verify 15-second title
restoration and an unchanged image/progress. Send repeated/long messages and
check idle info/Back. No flash, installation, commit or push was performed.
