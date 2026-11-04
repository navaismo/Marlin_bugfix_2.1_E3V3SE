# Pause, M600 and runout review (2026-11-03)

These follow-up changes are local and uncommitted pending printer validation.
They apply to c13_sd, c13_octoprint, c14_sd and c14_octoprint. Bed Scale and
the OctoPrint plugin are unchanged.

## LCD pause and filament changes

SD pause uses M25 -> M125: retract and park, then wait for the knob. It does
not perform M600's automatic unload. The LCD now says "Print paused" and
"Press knob to resume" at that wait. After confirmation, it checks/reheats the
nozzle as needed, purges automatically once, offers "Purge more / Resume",
and restores the print position when Resume is selected.

The merge initially allowed M125's 2-mm retract recovery to replace the
fork's longer purge. The local correction restores a useful automatic purge
for the Creality LCD, using ADVANCED_PAUSE_PURGE_LENGTH (currently 50 mm).
Other display backends retain upstream's M125 retract-recovery amount.

M600 still retracts, parks, unloads, waits for filament insertion and a click,
loads/purges, and returns to the saved print position. Existing M600 parameters
and the fork's parking implementation are retained. Current default settings
are 100-mm unload, zero separate slow/fast load, 50-mm purge at 3 mm/s, and a
60-second nozzle idle timeout with explicit reheating confirmation.

The old fork forced 40 mm whenever the requested purge length was positive.
The updated implementation honors the configured length: 50 mm automatically
on the first pass, another 50 mm only when Purge more is selected. It waits
for Resume after purging. The initial purge is not on demand. OctoPrint's
ordinary LCD pause/resume buttons still use M9000 pause-job/resume-job; host
pause scripts determine their own filament handling.

## Runout sensor

All four profiles retain PC15, FIL_RUNOUT_STATE HIGH and the internal pull-up.
HIGH means filament absent; LOW means present. FILAMENT_RUNOUT_SCRIPT remains
M600. The enabled core detector owns runout; the legacy LCD M25 detector is
excluded when HAS_FILAMENT_SENSOR is present. This avoids replacing a pending
M600 and respects M412 S0 and, on host-enabled builds, M412 H1.

Runout remains subject to Marlin's active-job/advanced-pause state and its
debounce logic. Marlin also uses its print timer to identify an active job;
manual heating that autostarts that timer can therefore count as an active job.
Runout during an existing filament-change pause does not inject another M600.

The local LCD correction distinguishes the latched runout event from physical
switch presence. Reinsertion clears that event and keeps an enabled sensor
enabled. If material is still absent, the explicit Disable sensor option can
disable it to resume; M412 S1 enables it again. A sensor disabled with M412 S0
is never silently enabled. Motion/combined sensors retain their own detection
semantics instead of using the switch reinsertion shortcut.

## Checks and printer validation

Focused native tests execute the production M125, load/purge, LCD and runout
functions: test_dwin_pause_purge.py, test_dwin_advanced_pause.py and
test_dwin_runout_owner.py. They cover automatic/repeated purge, confirmation,
switch reinsertion while the options are open, explicit disable, host replies,
motion-sensor exclusion and preservation of progress and M412 choices.

On the printer, verify a normal SD pause, a manual M600, and two separate
runouts in the same print after replacing filament. The second runout checks
that detection stayed enabled. Also verify that M412 S0 suppresses the event
and that the explicit Disable sensor choice only disables it when selected.
Compile/native checks cannot establish physical extrusion, parking accuracy
or the actual switch's electrical behavior.

### Local build results

All four default firmware builds and all three focused native suites per
branch passed after these changes. These are compile/simulation results;
physical validation remains pending.

| Branch | RAM (bytes) | Flash (bytes) |
| --- | ---: | ---: |
| c13_sd | 28900 | 239724 |
| c13_octoprint | 29228 | 241812 |
| c14_sd | 28884 | 235064 |
| c14_octoprint | 29212 | 237152 |

## Thumbnail progress follow-up

Pause/resume and cancel-dialog redraws, plus returning from Tune, preserve the
existing progress instead of resetting it to zero. A new print retains its
normal progress reset. `test/test_dwin_thumbnail_progress.py` executes the
actual renderer with the actual navigation-call arguments in SD/host modes,
checks progress/metadata and the image area, and checks new-print entry points.
