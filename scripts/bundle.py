"""Assemble a local ad-hoc-signed bundle; build.sh performs signing."""
import importlib.metadata
from pathlib import Path
import plistlib
import shutil
import sys

contents = Path("dist/LG TV Control.app/Contents")
helper = contents / "Resources/lgtv-helper"
if helper.exists():
    shutil.rmtree(helper)
shutil.copytree(".build/helper-dist/lgtv-helper", helper, symlinks=True)
info = {
    "CFBundleIdentifier": "org.lgtvcontrol.macos", "CFBundleName": "LG TV Control",
    "CFBundleDisplayName": "LG TV Control", "CFBundleExecutable": "LGTVControl",
    "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "1.1.1", "CFBundleVersion": "4",
    "LSUIElement": True, "LSMinimumSystemVersion": "26.0",
    "NSLocalNetworkUsageDescription": "Connect to your LG TV to switch HDMI inputs and control its panel over your LAN.",
}
(contents / "Info.plist").write_bytes(plistlib.dumps(info))
licenses = contents / "Resources/Licenses"
licenses.mkdir(exist_ok=True)
shutil.copytree("licenses", licenses / "runtime", dirs_exist_ok=True)
shutil.copy2("LICENSE", licenses / "LGTVControl-MIT.txt")
shutil.copy2("THIRD_PARTY_NOTICES.md", licenses / "THIRD_PARTY_NOTICES.md")
for name in ["bscpylgtv", "websockets", "sqlitedict", "pyinstaller"]:
    distribution = importlib.metadata.distribution(name)
    found = False
    for file in distribution.files or []:
        if any(word in str(file).lower() for word in ("license", "copying")) and distribution.locate_file(file).is_file():
            target = licenses / name / str(file)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(distribution.locate_file(file), target)
            found = True
    if not found:
        raise RuntimeError(f"No license text found for {name}; inspect package before distributing")
for candidate in [Path(sys.base_prefix) / "lib/python3.13/LICENSE.txt", Path(sys.base_prefix) / "LICENSE.txt"]:
    if candidate.exists():
        shutil.copy2(candidate, licenses / "Python-LICENSE.txt")
        break
else:
    raise RuntimeError("Python license not found; copy it into the runtime before distributing")
