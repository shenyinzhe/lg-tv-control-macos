import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
from controller import execute, validate, wake_on_lan

CONFIG = {'ip': '192.0.2.10', 'mac_input': 3}

class ValidationTests(unittest.TestCase):
    def test_invalid_addresses_and_ports(self):
        for update in [{'ip': 'not-a-host'}, {'mac_input': 0}, {'mac_input': True},
                       {'mac_input': 5}, {'mac_address': 'bad'}, {'broadcast': '300.1.1.1'}]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate({**CONFIG, **update})

    def test_wol_requires_explicit_mac(self):
        with patch('controller.socket.socket') as sock, self.assertRaises(ValueError):
            wake_on_lan(validate(CONFIG))
        sock.assert_not_called()

    def test_magic_packet(self):
        with patch('controller.socket.socket') as sock:
            wake_on_lan(validate({**CONFIG, 'mac_address': '02:00:00:00:00:01'}))
            packet, address = sock.return_value.__enter__.return_value.sendto.call_args.args
            self.assertEqual(packet, b'\xff' * 6 + bytes.fromhex('020000000001') * 16)
            self.assertEqual(address, ('255.255.255.255', 9))

class ControlTests(unittest.IsolatedAsyncioTestCase):
    def client(self, app='com.webos.app.hdmi3', state='Active'):
        c = AsyncMock()
        c.get_current_app.return_value = app
        c.get_power_state.return_value = {'state': state}
        return c

    async def test_other_input_never_changes_panel(self):
        for action in ['sleep', 'wake']:
            c = self.client('com.webos.app.hdmi1')
            self.assertEqual(await execute(c, action, CONFIG), 'Other input: skipped')
            c.turn_screen_off.assert_not_awaited()
            c.turn_screen_on.assert_not_awaited()
            c.set_input.assert_not_awaited()

    async def test_unknown_input_fails_closed(self):
        c = self.client(None)
        await execute(c, 'sleep', CONFIG)
        c.turn_screen_off.assert_not_awaited()
        c.get_current_app.side_effect = RuntimeError('unavailable')
        with self.assertRaises(RuntimeError):
            await execute(c, 'sleep', CONFIG)
        c.turn_screen_off.assert_not_awaited()

    async def test_active_wake_does_not_repeat_screen_on(self):
        c = self.client()
        await execute(c, 'wake', CONFIG)
        c.turn_screen_on.assert_not_awaited()

    async def test_sleep_and_wake_own_input(self):
        c = self.client()
        await execute(c, 'sleep', CONFIG)
        c.turn_screen_off.assert_awaited_once()
        c.get_power_state.return_value = {'state': 'Screen Off'}
        await execute(c, 'wake', CONFIG)
        c.turn_screen_on.assert_awaited_once()

    async def test_configured_mac_port(self):
        c = self.client('com.webos.app.hdmi4')
        await execute(c, 'attach', {**CONFIG, 'mac_input': 4})
        c.set_input.assert_awaited_once_with('HDMI_4')

    async def test_switch_requires_readback(self):
        c = self.client('com.webos.app.hdmi1')
        with patch('controller.asyncio.sleep', new=AsyncMock()), self.assertRaises(RuntimeError):
            await execute(c, 'hdmi2', CONFIG)

if __name__ == '__main__':
    unittest.main()
