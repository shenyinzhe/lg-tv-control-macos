# LG TV Control for macOS

A native menu-bar app that switches LG webOS TV HDMI inputs using **⌘⌃1–4** and follows Mac display sleep/wake events over the local network. No HDMI-CEC, Hammerspoon, or external Python runtime is required by the built app.

[中文说明](README.zh-CN.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md)

## Features

- Native menu-bar HDMI selection and Command + Control + number hotkeys.
- Automatic panel off/on only when the TV reports the configured Mac HDMI input.
- Detect a newly connected LG display; respect an already running TV’s input.
- Automatic Wake-on-LAN and Mac HDMI selection when the TV cannot be reached, without requiring prior standby history.
- Standard TV pairing prompt, with credentials stored outside the app and repository.
- No changes to macOS sleep settings, TV labels, picture settings, or CEC.

This is an early release. The predecessor app's HDMI 1–3 switching and panel commands were verified on an LG C3, M1 Pro and macOS 26.5.1. The configurable build has 20 mocked tests and a local bundle build. A hardware test confirmed that an active HDMI 1 is protected, and an explicitly observed full standby can be woken by WOL and switched to HDMI 3. A complete Mac system-sleep cycle and cable reattachment still need hardware testing. Intel Macs and other TV models have not been tested.

## Requirements

- Runtime: macOS 26 or later; a webOS TV reachable from the same trusted LAN.
- Build: Xcode/Command Line Tools, `swiftc`, [uv](https://docs.astral.sh/uv/), Python 3.13 (uv can provision it).
- Build on the architecture you intend to run. This is not a universal binary.
- Enable the TV's network-control/mobile wake option for network wake. Names vary by TV firmware. Reserve its IP in your router.

## Build and install

```sh
./scripts/build.sh
./scripts/install.sh
```

The build runs tests, embeds Python and its dependencies, creates `dist/LG TV Control.app` and a ZIP, and applies a local ad-hoc signature. It does **not** notarize or upload the app. The installer refuses to overwrite an existing app. To replace one, quit it and move the old app to Trash first; your configuration is separate.

## First-time setup

Run the installed helper, using your TV's actual IP and the HDMI port connected to your Mac:

```sh
helper="$HOME/Applications/LG TV Control.app/Contents/Resources/lgtv-helper/lgtv-helper"
"$helper" configure --ip 192.0.2.10 --mac-input 3
"$helper" pair
```

`192.0.2.10` is a documentation example, not a discoverable TV. During `pair`, use the TV remote to accept the connection request. Then:

```sh
"$helper" status
open "$HOME/Applications/LG TV Control.app"
```

Allow the app's Local Network prompt if macOS shows it. Carbon global hotkeys do not require Accessibility access. The app's menu also provides a pairing command after configuration exists.

Optional Wake-on-LAN (substitute your TV MAC and subnet broadcast):

```sh
"$helper" configure --ip 192.0.2.10 --mac-input 3 \
  --mac-address 02:00:00:00:00:01 --broadcast 192.0.2.255
```

Edit `~/Library/Application Support/LGTVControl/config.json` to customize `screen_names` and `input_labels`; see [config.example.json](config.example.json). Restart the app after changes. No network traffic is sent by `configure`.

## Login startup and removal

```sh
./scripts/login-item.sh enable
./scripts/login-item.sh disable
```

Startup is opt-in. This installs a user LaunchAgent that uses `open` to launch the app at login. To uninstall, disable startup, quit the app from its menu, and move it from `~/Applications` to Trash. The data folder is preserved; remove it separately only if you want to erase pairing and configuration.

## Data and privacy

All runtime files are in `~/Library/Application Support/LGTVControl/`: `config.json`, `pairing.sqlite`, `controller.lock`, `monitor.lock`, `power-observation.json`, and `app.log`. These are excluded from Git. Pairing credentials are local files, not Keychain items, and are restricted to the current user. Never upload that directory or raw TV status output in an issue. The app has no analytics or cloud service.

The upstream webOS client accepts the TV's self-signed TLS certificate without authenticating its identity. Use only a trusted LAN; see [SECURITY.md](SECURITY.md). Runtime controls use the local TV and optional LAN broadcast only.

## Behavior and limitations

- Automatic sleep/wake checks the TV's current app; failed queries cause no panel action. Another controller can still change input between that check and the command: this is not an atomic lock across computers.
- Wake retries temporary network errors and the TV’s `1008 Try Again Later (EWS)` response after 2, 4, and 8 seconds (four attempts, 50-second total deadline). Each attempt reconnects and rechecks the input. Pairing errors and other policy rejections are not retried.
- On startup, wake, or display attachment, first try to read the TV. If the connection fails temporarily (network error/timeout or EWS), send Wake-on-LAN and select the Mac HDMI after reconnecting, even without a recorded standby transition. This intentionally favors taking control: a temporary TV service/network failure can therefore switch away from an input that was in use.
- A reachable TV reporting active or screen-off state still gets the current-input guard. Explicit standby also enables WOL and Mac input selection. The background power-state monitor is diagnostic, not a prerequisite for wake.
- `Screen Off` remains an operating TV, and automatic wake/attachment never takes another input in that state.
- A fully sleeping TV may not advertise its display to macOS. Cable reattachment then cannot be detected reliably without CEC.
- The Mac may suspend before an asynchronous sleep command finishes. This app does not delay system sleep or override power policy.
- Other computers' power automation still needs its own current-input guard.
- The controller permits one command at a time. A concurrent CLI invocation may report `Controller busy`.
- Port hotkeys use physical ANSI number-row key codes; keyboard layout/remapping tools may affect their interpretation.
- TV IP discovery, a graphical settings editor, Keychain storage, notarized releases, and automatic updates are not implemented.

## Development

```sh
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python helper/controller.py --data-dir /tmp/lgtv-test configure --ip 192.0.2.10 --mac-input 3
```

Tests mock the TV; they do not contact hardware. The Swift app invokes the bundled helper with fixed argument arrays, never shell-interpolated input. CI runs unit tests and Swift type checking; a local release build should also be tested on real hardware.

## License and acknowledgments

MIT for this project's code. Inspired by the event-driven workflow of [cmer/lg-tv-control-macos](https://github.com/cmer/lg-tv-control-macos). Uses [bscpylgtv](https://github.com/chros73/bscpylgtv) for the webOS protocol and [PyInstaller](https://pyinstaller.org/) for bundling. Dependency license texts are copied into the app during builds; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This project is not affiliated with LG or Apple.
