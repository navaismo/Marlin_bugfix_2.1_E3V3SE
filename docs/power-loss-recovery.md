# SD power-loss recovery

**Enhanced PLR is off by default in every branch to save flash and RAM.** Uncomment both `POWER_LOSS_RECOVERY` and `DWIN_PLR_MENU` in `Configuration_adv.h`, or select the single **POWER_LOSS_RECOVERY + DWIN_PLR_MENU** workflow option (default: off). The workflow toggles both flags together. With the feature compiled in, the LCD submenu is **Control → Power-loss recovery** (`DWIN_PLR_MENU`). Disabling recovery deletes its checkpoint. This feature recovers SD jobs, not jobs streamed from OctoPrint.

| LCD item | Range / effect |
| --- | --- |
| Enabled | Same recovery switch as `M413 S1` / `M413 S0`. |
| Heat bed on boot | Heat the bed when a valid interrupted job is detected. |
| Heat nozzle on boot | Heat the nozzle to its saved target while awaiting confirmation. |
| Bed extra C | 0–20°C added to the saved bed target while awaiting confirmation; capped at the bed limit. |
| Auto C (0=off) | 0 disables automatic resume; 1–`BED_MAX_TARGET`°C resumes without confirmation if the current bed temperature is at or above the threshold. Same threshold as `M413 B`. |
| Z lift mm | 0.0–20.0 mm clearance before homing XY during recovery. |
| Purge mm | 0.0–50.0 mm extra filament to extrude before returning to the saved XY. |
| Save Z step mm | 0.01–1.00 mm change in Z between checkpoints. Smaller values write the SD card more often. |
| Store settings | Saves all options, equivalent to `M500`. |

Editing a value or toggle does not start heating, move an axis or start a print. Changes take effect for recovery and new checkpoints. The saved checkpoint retains the clearance recorded when it was written, including any lift already performed by a UPS. Use **Store settings** in the submenu, **Control → Store Settings**, or `M500` to persist the options. `M501` reloads the saved options; `M502` restores the compile-time defaults without saving them until `M500`.

The extra options use a versioned, checksummed 16-byte block at BL24CXX addresses `0x20–0x2F`, separate from the wizard/PID bytes and Marlin's settings at offset 100. No EEPROM version bump or calibration reset is needed. An absent, corrupt or partially written extension falls back to defaults. Recovery enabled and the automatic-resume threshold continue to use Marlin's existing EEPROM fields. The single **POWER_LOSS_RECOVERY + DWIN_PLR_MENU** build option includes recovery and the advanced menu together. Leaving it off compiles out both. For manual builds, base recovery can still be compiled without the optional submenu; `DWIN_PLR_MENU` requires `POWER_LOSS_RECOVERY`. Neither the LCD switch nor `M413` can activate recovery in firmware compiled without it.

## Startup and One Click Print

On the first media mount after startup, `CardReader::manage_media()` checks the `/PLR` checkpoint before looking for the newest file. A valid checkpoint injects `M1000 S` and skips One Click Print. `M1000 S` sets `recovery.ui_flag_resume`; the DWIN UI consumes that same flag and displays Cancel / Continue. One Click Print also refuses to open a preview while recovery is pending or its dialog is visible.

The dialog is a normal UI state. It returns to Marlin's main loop between encoder events, allowing temperature management, media detection and watchdog servicing to continue. It resolves the saved absolute filename, including nested folders, without opening a new print or parsing its thumbnail. Continue resumes that saved file and byte offset through `M1000`; Cancel turns off the selected reboot heaters and deletes the checkpoint.

Recovery uses the standard print screen without a thumbnail. The screen is initialized for both confirmation-based recovery and automatic recovery using the optional bed threshold. Old completion/abort UI flags are cleared before starting recovery.

## Checkpoint and restoration

With the current C13 SD profile there is no configured power-loss detection pin or UPS. During extrusion moves, Marlin periodically writes the checkpoint when Z has changed by the LCD's **Save Z step mm** value (default 0.05 mm). This is a saved checkpoint, not a recording of the exact instant power disappeared. The planner and FT_Motion supply the recovery position and SD command offset.

The checkpoint interval is measured against the Z of the last successfully written record, independently of the live Stepper/FT_Motion position. Tiny continuous-Z moves accumulate toward that interval. Downward returns from Z-hops are tracked too. XYZ/E and the matching SD offset are copied with interrupts briefly disabled; interrupts are enabled again before writing the immutable snapshot to the card. Failed/short writes do not advance the saved-Z baseline, and truncated recovery records are rejected.

Each record keeps two positions: the current planner segment (`current_position`) and the beginning of its whole SD command (`command_start_position`). Standard stepping and FT_Motion capture the command start when the block's SD offset changes, while updating the live segment position for every block. Recovery establishes its initial Z and clearance from the live segment, then returns to the command start and replays the command. This preserves relative extrusion amounts on segmented `G1` moves and the original IJ center on segmented `G2/G3` moves. Replaying an arc from an intermediate segment would relocate its center even with `G90`, because IJ are relative to the starting point.

Adding the command-start position changes the `/PLR` file format (C13 record: 196 → 212 bytes). Checkpoints from the preceding format are rejected as short records; use a new print to test this build rather than upgrading with an interrupted job pending. EEPROM settings and their version are unchanged.

Resuming preserves the saved file offset when preparing the first SD command. Recovery moves explicitly use absolute coordinates and extrusion, then restore the interrupted file's saved relative/absolute modes. The optional purge runs at 3 mm/s of filament (180 mm/min), including with an `M83` file. The serial console reports `PLR resume: SD=... X=... Y=... Z=... E=...` for the command-start position, followed by `PLR saved block: X=... Y=... Z=... E=...` for the live segment. The two positions can differ when the interrupted command was segmented.

Saved home offsets are restored before homing, so a runtime home offset that differs from EEPROM is used to establish the same physical origin. Saved logical XYZ are converted to native coordinates, and recovery moves run with workspace offsets cleared; the saved workspace is restored before SD execution resumes. This avoids an offset-sized shift after `G28` clears the XY workspace. It does not compensate for an endstop that triggers at a different physical point or a part that moved.

Planner checkpoints contain machine coordinates with leveling already applied, rather than the nominal Z in the G-code. The initial Z reference and clearance use that machine height while leveling is disabled. After homing, `M420` restores the saved leveling switch and fade while preserving physical position; recovery does not issue another `G92.9 Z` at the homing point, which would shift the Z reference by its mesh correction. Before returning to the checkpoint, the saved position is converted back through the restored modifiers. The next G-code command therefore starts from the nominal position with the bed correction applied once. This also respects a checkpoint saved with leveling off: `M420` must receive `S0`, not an integer character code such as `S48`.

After the return moves finish and before restarting SD execution, the serial console prints `PLR restored (commanded):` and `PLR restored (step counters):`, each followed by XYZ/E and step counts. Compare the X/Y in these two reports with the initial `PLR resume` report. A difference between commanded and counter-derived XY exposes an internal position discrepancy; agreement does not prove that the motors, endstop or part kept their physical reference, because the machine has no position feedback. With the current bilinear profile, leveling affects Z, so compare XY first. The initial `PLR resume` Z includes the bed correction; the restored reports show nominal Z with that correction removed, so those Z values can legitimately differ. Capture these lines across recovery to investigate a repeatable lateral shift. To verify the saved point against the file as well, preserve a copy of the SD card's `/PLR` before recovery (continuing the print overwrites it; cancelling deletes it), together with the matching G-code and firmware ELF. Do not remove the card while the powered printer is using it.

On Continue, Marlin restores the saved bed target and waits, heats the nozzle to at least 180°C to soften the material, raises Z, homes XY, restores leveling and the saved nozzle target, restores fans and extrusion state, returns to the saved command-start XYZ/E, and resumes reading the saved file offset. It also restores elapsed time, feedrate and flow percentages. Z is not homed to the bed by default. Recovery can retrace an already printed portion of the first command; the checkpoint does not identify the exact instant the motors lost power.

## Initial defaults in `Configuration_adv.h`

With `DWIN_PLR_MENU`, the following values initialize the LCD options. Saved settings override them. Heating and purge code is available at runtime even when its default is disabled.

| Option | Behavior | Current default |
| --- | --- | --- |
| `PLR_ENABLED_DEFAULT` | Initial runtime setting only when PLR is compiled in; EEPROM can override it. It does not include PLR in the build. | `true` |
| `PLR_HEAT_BED_ON_REBOOT` | Starts bed heating while the recovery dialog waits. It does not wait for the bed before showing the dialog. Cancel turns that heating off. | Off |
| `PLR_HEAT_NOZZLE_ON_REBOOT` | Initial value for the LCD nozzle-on-boot toggle. | Off |
| `PLR_HEAT_BED_EXTRA` | Extra bed temperature while awaiting confirmation, capped at `BED_MAX_TARGET`. An omitted value means 0°C extra; a saved zero target stays off. The normal saved target returns on Continue. | 0°C |
| `PLR_BED_THRESHOLD` | Allows `M1000 S` to resume automatically if the bed remains at or above this temperature. With 0, confirmation is always required. | Off |
| `POWER_LOSS_ZRAISE` | Clearance above the saved Z before homing XY; capped at `Z_MAX_POS`. Without UPS this move happens after reboot and confirmation. | 5 mm |
| `POWER_LOSS_PURGE_LEN` | Additional filament to extrude during recovery, before returning to the saved XY. | Off |
| `POWER_LOSS_MIN_Z_CHANGE` | Minimum absolute change in Z before writing another checkpoint. | 0.05 mm |
| `BACKUP_POWER_SUPPLY` / `POWER_LOSS_RETRACT_LEN` | Retraction and lift at the outage require backup power and a real detection pin. They do not provide those capabilities through configuration alone. | Off |
| `POWER_LOSS_RECOVER_ZHOME` / `POWER_LOSS_ZHOME_POS` | Rehomes Z at an explicitly chosen XY position. The position must avoid the object and allow probing. | Off |

The hardware-dependent UPS, power-loss pin and safe Z-homing options remain compile-time settings; the submenu does not turn a stock board into a UPS-equipped machine.

## Build memory cost

Measured with the committed branch profiles on 2026-10-17; values are bytes. Enabled includes recovery and the advanced LCD menu. These are linked flash/static RAM sizes, not runtime stack measurements.

| Branch | Flash off | Flash on | Added flash | RAM off | RAM on | Added RAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `c13_sd` | 230036 | 237116 | +7080 | 28384 | 29048 | +664 |
| `c13_octoprint` | 232300 | 239308 | +7008 | 28708 | 29380 | +672 |
| `c14_sd` | 226640 | 233904 | +7264 | 28388 | 29052 | +664 |
| `c14_octoprint` | 228856 | 236072 | +7216 | 28712 | 29384 | +672 |

The C13 profiles already exceed the project's 40% of 64 KiB RAM guideline. Leaving PLR disabled reduces their static RAM; enabling it adds the amounts shown above. Both C13 enabled builds remain below 46% of 512 KiB flash.

## Hardware validation

Native regression tests exercise the production recovery handlers and submenu with simulated media, queue, thermal and EEPROM interfaces, including encoder bounds, no heating during edits, settings reload, checksum failure, interrupted writes and preservation of the surrounding EEPROM. Firmware builds check both C13 and C14 targets, with SD and OctoPrint profiles, and with recovery plus its menu enabled and disabled. These build checks do not replace power-cut testing on each hardware variant. The checkpoint regression runs the production save/write/resume functions against continuous 0.002 mm Z moves, Z-hop returns, partial writes, concurrent live-position changes, resumed SD offsets and both relative/absolute extrusion. It also checks the simulated physical XY return point and the first resumed move with home and workspace offsets independently enabled/disabled, including nonzero saved offsets and different reboot offsets. The position reports must follow motion synchronization and precede SD restart. These checks do not simulate physical loss of power or prove that the part remains attached.

Run the native checks with:

```sh
python3 test/test_plr_build_option.py
python3 test/test_dwin_powerloss.py
python3 test/test_plr_settings.py
python3 test/test_plr_checkpoint.py
python3 test/test_plr_leveling.py
python3 test/test_plr_arc_replay.py
```

The leveling regression executes the production PLR resume, leveling transforms and leveling enable/disable helper against an independently tracked physical Z. It checks flat and sloped meshes with positive, negative and zero corrections, fade on/off, differing saved/boot leveling states, automatic leveling after `G28` on/off, and saved home/workspace offsets. Both the return point and the first following G-code layer must reach the expected physical height without changing the Z reference.

The arc regression uses the production `plan_arc`, recovery and leveling code with the spiral hop from `Cube_PETG_8m42s.gcode`: `G3 Z2.8 I-2.24 J.951 P1 F12000`. An intermediate checkpoint must return to that command's original start while preserving its Z reference. All 15 replayed segments must match the original XYZ/E coordinates. This verifies replay geometry, not the physical position at an actual power cut or the exact checkpoint selected by FT_Motion timing. That file uses `G90`, `M83`, `M420 S1 Z0`, 0.2 mm layers and 0.8 mm hops; there is no mid-model XY origin change. Its 62 helical travel commands make segmented-command replay relevant to this test.

For an on-printer check, use a small disposable SD print, keep the axes and object untouched during the outage, and test both One Click Print on and off. After a checkpoint has been written, interrupt power and restore it. Verify that the recovery dialog names the interrupted file even if a newer G-code exists, idle temperatures stay controlled, Cancel never starts another job, and Continue heats, lifts Z, homes only XY and resumes the interrupted job. Repeat with a file in nested folders. With reboot bed heating enabled, verify that the dialog remains responsive while heating and Cancel sets the bed target to zero.

Without UPS, the printer cannot retract or lift when power is already gone. Recovery also cannot detect manual axis movement, Z drift or a detached part; these affect whether a checkpoint can be resumed successfully.
