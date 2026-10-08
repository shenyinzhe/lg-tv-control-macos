# Third-party notices

This project's original source is MIT licensed. Dependencies retain their own licenses:

| Component | License | Source |
| --- | --- | --- |
| bscpylgtv 0.5.5 | MIT (Dennis Karpienski, Josh Bendavid) | https://github.com/chros73/bscpylgtv |
| websockets 17.2 | BSD-3-Clause | https://github.com/python-websockets/websockets |
| sqlitedict 2.1.0 | Apache-2.0 | https://github.com/piskvorky/sqlitedict |
| CPython 3.13 | PSF license and included notices | https://www.python.org/ |
| PyInstaller 6.22.3 | GPL-2.0-or-later with bootloader exception; some Apache-2.0 files | https://pyinstaller.org/en/stable/license.html |

The build copies installed dependency license texts and CPython's license into `Contents/Resources/Licenses`. PyInstaller's bootloader exception permits distributing bundled applications under their own licenses while retaining dependency obligations. No PyInstaller source modifications are made here.

A frozen Python runtime may also bundle OpenSSL, SQLite, libffi and other platform/runtime libraries. Before distributing public binaries, audit the specific runtime produced by your Python distribution and include all applicable notices. The source repository does not vendor that runtime. A local ad-hoc build is not a notarized public release.

The initial behavior was inspired by cmer/lg-tv-control-macos; the native Swift application and configurable wrapper are independently maintained here. No upstream installer or prebuilt TV-control binary is vendored.

The v1.1.1 Apple Silicon release uses uv-provisioned python-build-standalone CPython 3.13.15. Runtime dependency notices are included under `licenses/python-build-standalone` and copied into the App. Its Mach-O dependencies were checked for external Homebrew/Conda paths.
