# Repository agent instructions

Read [`MEMORY.md`](./MEMORY.md) for the repository's branch map, custom-feature history, and cross-component relationships. Read [`.github/copilot-instructions.md`](./.github/copilot-instructions.md) for target, build, test, architecture, and memory-limit guidance. These files complement one another.

## Before changing code

- Run `git status --short --branch` and establish the active branch, `HEAD`, and existing user changes. Do not assume the current branch from the branch map or switch branches without an explicit request.
- Check the active branch's configuration and source layout before making machine-specific changes. C13/C14 and SD/serial-host branches have different configurations, display paths, and histories; do not copy a change between them without verifying compatibility.
- Trace a custom feature end-to-end: configuration macro and sanity checks, build/source guards, implementation, G-code entry point, DWIN/UI call sites, and persistence or host interactions as applicable.

## Repository-specific rules

- Keep configuration changes in `Marlin/Configuration.h` and `Marlin/Configuration_adv.h`; confirm whether any generated/exported configuration artifacts must be regenerated instead of editing them by hand.
- Use Marlin feature guards (`ENABLED`, `DISABLED`, `TERN`, etc.) consistent with surrounding code. Preserve portable Marlin behavior unless a change is intentionally target-specific and guarded.
- Treat C13/C14 pin mappings, EEPROM setup, serial settings, bootloader offsets, probe/load-cell wiring, and DWIN display paths as hardware-specific. Verify pin definitions and the matching PlatformIO environment together.
- This firmware has tight memory budgets. Check the resulting target's flash and RAM after feature or renderer changes; static buffers and display/protocol changes can materially affect memory and responsiveness.
- Preserve the distinction between SD-only and serial-host firmware. Host actions, MeatPack, host G-code commands, and FT_Motion settings are not automatically shared across all branches.
- Keep experimental work such as `Bed_Scale_test` isolated unless the task explicitly requests integration into a release branch.
- Do not edit prebuilt `.bin` files or `.pio/` build output as a substitute for changing source/configuration.
- Never run Make targets with `GIT_RESET_HARD=true` unless the user explicitly requests it and has approved discarding tracked work. The test runner can invoke `git reset --hard HEAD` in that mode.

## Verification

- Prefer a focused PlatformIO build for the active target plus the relevant native/build test. The exact commands and single-test selectors are in [`.github/copilot-instructions.md`](./.github/copilot-instructions.md).
- Pin edits should be checked with `make validate-pins PINSPATH=<pin-family>`; broader board or formatting changes may also need `make validate-boards` or `make validate-lines`.
- Report which board environment and branch/configuration were verified. A passing build for one variant does not validate the other MCU or the host-support variant.

## Upstream-merge architecture (branch `architecture/e3v3se-upstream-seams`)

- Fork-only code lives in `Marlin/src/e3v3se/` (auto Z-offset: `AutoOffset.*`, `M8015.cpp`, `G212.cpp`) and `Marlin/src/lcd/dwin/creality/`. Never put fork-only files in upstream folders.
- Upstream-owned files (everything else) should stay as close to upstream as possible. Prefer a hook in a fork-owned file over editing upstream code. One-click print is an upstream feature: `sd/cardreader.*` and `menu_one_click_print.cpp` follow upstream plus the `selectNewestFile()` depth-sync fix.
- `Configuration.h` / `Configuration_adv.h` are derived: pristine upstream + `buildroot/share/e3v3se/profiles/c13_sd/` (`overrides.txt` for define states, `residual.*.patch` for fork-only options/blocks).
  - Edited the config files by hand? Run `python3 buildroot/share/e3v3se/config_profile.py derive`.
  - After merging upstream: take upstream's config files, then run `config_profile.py apply` (fails loudly if the residual patch no longer applies), then `config_profile.py stale` to review upstream options the profile disables.
- Guardrails (commit first, they diff `HEAD`): `check_profile.py boundary | config | build`. Use `--update` only after a reviewed change.
