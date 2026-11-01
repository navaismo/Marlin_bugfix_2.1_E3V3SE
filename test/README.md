# Testing Marlin

Marlin included two types of automated tests:

- [Build Tests](../buildroot/tests) to catch syntax and code build errors.
- Unit Tests (this folder) to catch implementation errors.

This document focuses on Unit tests.

## Unit tests

### Creality DWIN bed mesh renderer (host)

Run `python3 test/test_bed_level_visualizer.py` from the repository root. It compiles the production renderer with a recorded LCD transport and sample bed meshes, then checks filled surfaces, color scales, coordinate bounds, incomplete meshes, immutable snapshots, all five original assessment thresholds and labels, QR pixels and quiet zone, and return to Leveling during header, QR and surface rendering. It checks that XYZ axes are drawn behind the surface and their labels do not overlap it. It also checks the centered yellow title and replays replacement of a longer leveling label by Bed Level Map in every menu row, ensuring no trailing text remains. It exercises the actual Leveling menu drawing and encoder handlers, checks the selected row after returning, rejects calibration actions while opening the viewer, and compiles the menu with the feature disabled to verify the original three-option limit. It rejects floating-point printf conversions, checks numeric statistics and legend labels, and replays surface coverage with both inclusive and exclusive rectangle endpoints to detect gaps. A simulated clock verifies 10/20 ms command spacing, repeated calls before a deadline and timer rollover. The test also reads the fixed QR's byte payload to verify the exact help URL. It needs a host C++17 compiler, without PlatformIO, a QR library, or a connected printer.

Add `--preview-dir /tmp/bed-level-preview` to export LCD command previews as SVG. If ImageMagick is available, it also writes a PNG. Use `--sanitize` to enable UBSan when the host has its runtime installed.

### Marlin native unit tests

Unit testing allows for functional testing of Marlin logic on a local machine. This strategy is available to all developers, and will be able to be used on generic GitHub workers to automate testing. While PlatformIO does support the execution of unit tests on target controllers, that is not yet implemented and not really practical. This would require dedicated testing labs, and would be less broadly usable than testing directly on the development or build machine.

Unit tests verify the behavior of small discrete sections of Marlin code. By thoroughly unit testing important parts of Marlin code, we effectively provide "guard rails" which will prevent major regressions in behavior. As long as all submissions go through the Pull Request process and execute automated checks, it is possible to catch most major issues prior to completion of a PR.

## What unit tests can and can't do

Unit tests can be used to validate the logic of single functions or whole features, as long as that function or feature doesn't depend on real hardware. So, for example, we can test whether a G-code command is parsed correctly and produces all the expected state changes, but we can't test whether a G-code triggered an endstop or the filament runout sensor without adding a new layer to simulate pins.

Generally speaking, the types of errors caught by unit tests are most often caught in the initial process of writing the tests, and thereafter they shore up the codebase against regressions, especially in core classes and types, which can be very useful for refactoring.

### Unit test FAQ

#### Q: Isn't writing unit tests a lot of work?

A: Yes, and it can be especially difficult with existing code that wasn't designed for unit testing. Some common sense should be used to decide where to employ unit testing, and at what level to perform it. While unit testing takes effort, it pays dividends in preventing regressions, and helping to pinpoint the source of failures when they do occur.

#### Q: Will this make refactoring harder?

A: Yes and No. Of course if you refactor code that unit tests use directly, it will have to be reworked as well. It actually can make refactoring more efficient, by providing assurance that the mechanism still works as intended.

#### Q: How can I debug one of these failing unit tests?

A: That's a great question, without a known immediate answer. It is likely possible to debug them interactively through PlatformIO, but that can at times take some creativity to configure. Unit tests are generally extremely small, so even without interactive debugging it can get you fairly close to the cause of the problem.

### Unit test architecture

We are currently using [PlatformIO unit tests](https://docs.platformio.org/en/latest/plus/unit-testing.html).

Since Marlin only compiles code required by the configuration, a separate test binary must be generated for any configuration change. The following process is used to unit test a variety of configurations:

1. This folder contains a set of INI configuration files (See `config.ini`), each containing a distinct set of configuration options for unit testing. All applicable unit tests will be run for each of these configurations.
2. The `Marlin/tests` folder contains the CPP code for all Unit Tests. Marlin macros (`ENABLED(feature)`, `TERN(FEATURE, A, B)`, etc.) are used to determine which tests should be registered and to alter test behavior.
3. The `linux_native_test` PlatformIO environment specifies a script to collect all the tests from this folder and add them to PlatformIO's list of test targets.
4. Tests are built and executed by the `Makefile` commands `unit-test-all-local` or `unit-test-all-local-docker`.
