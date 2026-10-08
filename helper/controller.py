"""LG webOS control helper. Runtime configuration and credentials never live in the repo."""
import argparse
import asyncio
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
import time

from bscpylgtv import WebOsClient
from websockets.exceptions import ConnectionClosed

DEFAULTS = {
    "ip": "", "mac_input": 3, "mac_address": "", "broadcast": "255.255.255.255",
    "screen_names": ["LG TV", "LG TV SSCR2"],
    "input_labels": {"1": "HDMI 1", "2": "HDMI 2", "3": "HDMI 3", "4": "HDMI 4"},
}
MANIFEST = {"manifestVersion": 1, "appVersion": "1.0", "permissions": [
    "CONTROL_INPUT_TV", "CONTROL_POWER", "CONTROL_TV_SCREEN", "READ_INPUT_DEVICE_LIST",
    "READ_RUNNING_APPS", "READ_POWER_STATE", "LAUNCH",
]}


def validate(config):
    result = {**DEFAULTS, **config}
    ipaddress.IPv4Address(result["ip"])
    ipaddress.IPv4Address(result["broadcast"])
    if type(result["mac_input"]) is not int or result["mac_input"] not in range(1, 5):
        raise ValueError("mac_input must be an integer from 1 to 4")
    if result["mac_address"] and not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", result["mac_address"]):
        raise ValueError("mac_address must have format AA:BB:CC:DD:EE:FF")
    if not isinstance(result["screen_names"], list) or not all(isinstance(x, str) and x for x in result["screen_names"]):
        raise ValueError("screen_names must be a list of nonempty strings")
    if not isinstance(result["input_labels"], dict) or not all(k in ("1", "2", "3", "4") and isinstance(v, str) for k, v in result["input_labels"].items()):
        raise ValueError("input_labels must map HDMI port numbers to strings")
    return result


def load_config(base):
    path = base / "config.json"
    if not path.exists():
        raise ValueError("Missing config.json. Run configure --ip TV_IP --mac-input PORT first (see README).")
    return validate(json.loads(path.read_text()))


def wake_on_lan(config):
    if not config["mac_address"]:
        raise ValueError("TV unavailable; configure mac_address to enable Wake-on-LAN")
    packet = b"\xff" * 6 + bytes.fromhex(config["mac_address"].replace(":", "")) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (config["broadcast"], 9))


STANDBY_STATES = {"Active Standby", "Suspend", "Power Off"}


def remember_power(base, config, payload):
    state = payload.get("state")
    if not state:
        return
    path = base / "power-observation.json"
    temp = base / "power-observation.json.tmp"
    temp.write_text(json.dumps({"ip": config["ip"], "state": state,
                                "processing": payload.get("processing"), "observed_at": time.time()}))
    temp.chmod(0o600)
    temp.replace(path)


def observed_standby(base, config):
    try:
        data = json.loads((base / "power-observation.json").read_text())
        return data.get("ip") == config["ip"] and data.get("state") in STANDBY_STATES
    except (OSError, ValueError):
        return False


async def monitor(base, config):
    # A disconnect/EWS is never stored as standby. Only explicit TV reports are evidence.
    while True:
        client = await WebOsClient.create(config["ip"], key_file_path=str(base / "pairing.sqlite"),
                                         states=[], connect_retry_attempts=1)
        client.manifest = MANIFEST
        try:
            if not client.client_key:
                raise ValueError("Pair TV before starting the monitor")
            await asyncio.wait_for(client.connect(), 5)
            async def update(payload):
                remember_power(base, config, payload)
            await client.subscribe_power(update)
            while True:
                await asyncio.sleep(15)
                await asyncio.wait_for(client.get_power_state(), 5)
        except (OSError, asyncio.TimeoutError, ConnectionClosed):
            pass
        finally:
            await client.disconnect()
        await asyncio.sleep(5)


async def execute(client, action, config):
    """Check current input immediately before automatic panel changes; fail closed."""
    app = await client.get_current_app()
    if action == "status":
        return {"app": app, "power": await client.get_power_state(), "inputs": await client.get_inputs()}
    if action.startswith("hdmi") or action == "attach":
        port = int(action[-1]) if action.startswith("hdmi") else config["mac_input"]
        await client.set_input(f"HDMI_{port}")
        if (await client.get_power_state()).get("state") != "Active":
            await client.turn_screen_on()
        for _ in range(8):
            if await client.get_current_app() == f"com.webos.app.hdmi{port}":
                return f"Selected HDMI_{port}"
            await asyncio.sleep(0.25)
        raise RuntimeError("TV did not confirm the requested HDMI input")
    if app != f"com.webos.app.hdmi{config['mac_input']}":
        return "Other input: skipped"
    state = (await client.get_power_state()).get("state")
    if action == "sleep":
        if state == "Active":
            await client.turn_screen_off()
        return "Mac input: panel off"
    if action == "wake":
        if state != "Active":
            await client.turn_screen_on()
        return "Mac input: panel on"
    raise ValueError("Unknown action")


async def control_once(base, action, config, context=None):
    context = context if context is not None else {}
    client = await WebOsClient.create(config["ip"], key_file_path=str(base / "pairing.sqlite"),
                                     states=[], connect_retry_attempts=2)
    client.manifest = MANIFEST
    try:
        if action != "pair" and not client.client_key:
            raise ValueError("TV is not paired. Run pair and accept the TV prompt first.")
        try:
            await asyncio.wait_for(client.connect(), 90 if action == "pair" else 5)
        except (OSError, asyncio.TimeoutError, ConnectionClosed) as error:
            if action in ("wake", "attach"):
                if transient_wake_error(error) and not context.get("claimed_standby") and observed_standby(base, config):
                    context["claimed_standby"] = True
                    wake_on_lan(config)
                    print("Confirmed standby: sent Wake-on-LAN; will select Mac HDMI after startup", file=sys.stderr)
                elif transient_wake_error(error) and context.get("claimed_standby"):
                    wake_on_lan(config)
                raise
            if not action.startswith("hdmi"):
                raise
            await client.disconnect()
            wake_on_lan(config)
            await asyncio.sleep(3)
            await asyncio.wait_for(client.connect(), 8)
        if action == "pair":
            return "Paired successfully"
        if action in ("wake", "attach"):
            power = await client.get_power_state()
            if power.get("state") in STANDBY_STATES:
                context["claimed_standby"] = True
                wake_on_lan(config)
                raise OSError("TV reports standby; waiting for network wake")
            if power.get("processing"):
                raise OSError("TV power transition in progress")
            if power.get("state") not in ("Active", "Screen Off", "Screen Saver"):
                raise ValueError("Unknown TV power state; automatic action skipped")
            if context.get("claimed_standby"):
                return await execute(client, "hdmi" + str(config["mac_input"]), config)
            # Attachment to an already running TV uses the same input guard as wake.
            return await execute(client, "wake", config)
        return await execute(client, action, config)
    finally:
        await client.disconnect()
        key_file = base / "pairing.sqlite"
        if key_file.exists():
            key_file.chmod(0o600)


WAKE_RETRY_DELAYS = (2, 4, 8)


def transient_wake_error(error):
    if isinstance(error, (OSError, asyncio.TimeoutError)):
        return True
    if isinstance(error, ConnectionClosed) and error.rcvd is not None:
        return (error.rcvd.code == 1008 and "Try Again Later (EWS)" in error.rcvd.reason)
    return False


async def control(base, action, config):
    # Retry the entire wake transaction with a fresh connection and input query.
    # Do not replay sleep commands late. Only confirmed standby grants input ownership.
    delays = WAKE_RETRY_DELAYS if action in ("wake", "attach") else ()
    context = {}
    for attempt in range(len(delays) + 1):
        try:
            return await control_once(base, action, config, context)
        except Exception as error:
            if attempt == len(delays) or not transient_wake_error(error):
                raise
            delay = delays[attempt]
            print(f"Wake attempt {attempt + 1} temporarily failed ({type(error).__name__}); retrying in {delay}s", file=sys.stderr)
            await asyncio.sleep(delay)


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path.home() / "Library/Application Support/LGTVControl")
    sub = parser.add_subparsers(dest="action", required=True)
    setup = sub.add_parser("configure", help="Create/update local config; does not contact the TV")
    setup.add_argument("--ip", required=True)
    setup.add_argument("--mac-input", type=int, required=True)
    setup.add_argument("--mac-address")
    setup.add_argument("--broadcast")
    for action in ["monitor", "pair", "status", "hdmi1", "hdmi2", "hdmi3", "hdmi4", "sleep", "wake", "attach"]:
        sub.add_parser(action)
    args = parser.parse_args()
    os.umask(0o077)
    base = args.data_dir.expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with (base / ("monitor.lock" if args.action == "monitor" else "controller.lock")).open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.action == "configure":
                path = base / "config.json"
                config = json.loads(path.read_text()) if path.exists() else dict(DEFAULTS)
                config.update(ip=args.ip, mac_input=args.mac_input)
                for key in ("mac_address", "broadcast"):
                    if getattr(args, key) is not None:
                        config[key] = getattr(args, key)
                config = validate(config)
                temp = base / "config.json.tmp"
                temp.write_text(json.dumps(config, indent=2) + "\n")
                temp.chmod(0o600)
                temp.replace(path)
                print("Configuration saved. Run pair next; restart the app after editing configuration.")
                return 0
            config = load_config(base)
            if args.action == "monitor":
                asyncio.run(monitor(base, config))
                return 0
            result = asyncio.run(asyncio.wait_for(control(base, args.action, config), 100 if args.action == "pair" else (50 if args.action in ("wake", "attach") else 25)))
            print(json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else result)
            return 0
    except BlockingIOError:
        print("Controller busy; retry shortly", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(cli())
