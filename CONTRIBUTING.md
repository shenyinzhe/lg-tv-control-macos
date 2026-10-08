# Contributing

Use Python 3.13 and run `python -m unittest discover -s tests -v` after installing requirements. Build with `scripts/build.sh` before proposing packaging changes.

For controller changes, preserve the current-input guard and fail closed on unreadable TV state. Do not introduce background HDMI switching or changes to macOS power settings. Add tests covering action-changing behavior, especially shared-TV interactions.

Keep real addresses, pairing databases, logs, and build artifacts out of commits. Use documentation addresses (192.0.2.0/24) and synthetic locally administered MACs in examples. Never run hardware tests from CI.

Report macOS, CPU architecture, TV model/firmware, expected behavior and sanitized error messages. Reproduce with a temporary `--data-dir` where possible. Contributions are under this repository's MIT license.
