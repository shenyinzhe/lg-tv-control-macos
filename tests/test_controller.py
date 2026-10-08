import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch
import tempfile
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
from controller import execute, validate, wake_on_lan, control, remember_power, observed_standby

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

class WakeRetryTests(unittest.IsolatedAsyncioTestCase):
    def ews(self):
        return ConnectionClosedError(Close(1008, 'Try Again Later (EWS)'), None)

    async def test_ews_then_mac_input_recovers(self):
        first, second = AsyncMock(), AsyncMock()
        first.client_key = second.client_key = 'synthetic-key'
        first.connect.side_effect = self.ews()
        second.get_current_app.return_value = 'com.webos.app.hdmi3'
        second.get_power_state.return_value = {'state': 'Screen Off'}
        with tempfile.TemporaryDirectory() as directory, patch('controller.WebOsClient.create', new=AsyncMock(side_effect=[first, second])), patch('controller.asyncio.sleep', new=AsyncMock()), patch('controller.wake_on_lan') as wol:
            self.assertEqual(await control(Path(directory), 'wake', CONFIG), 'Selected HDMI_3')
        first.disconnect.assert_awaited_once()
        second.turn_screen_on.assert_awaited_once()
        self.assertEqual(second.get_current_app.await_count, 2)
        second.set_input.assert_awaited_once_with('HDMI_3')
        wol.assert_called_once()

    async def test_retry_rechecks_input_after_read_failure(self):
        first, second = AsyncMock(), AsyncMock()
        first.client_key = second.client_key = 'synthetic-key'
        first.get_power_state.return_value = {'state': 'Active'}
        second.get_power_state.return_value = {'state': 'Active'}
        first.get_current_app.side_effect = self.ews()
        second.get_current_app.return_value = 'com.webos.app.hdmi1'
        with tempfile.TemporaryDirectory() as directory, patch('controller.WebOsClient.create', new=AsyncMock(side_effect=[first, second])), patch('controller.asyncio.sleep', new=AsyncMock()):
            self.assertEqual(await control(Path(directory), 'wake', CONFIG), 'Other input: skipped')
        first.turn_screen_on.assert_not_awaited()
        second.turn_screen_on.assert_not_awaited()
        second.set_input.assert_not_awaited()

    async def test_retries_are_bounded(self):
        with patch('controller.control_once', new=AsyncMock(side_effect=self.ews())) as attempt, patch('controller.asyncio.sleep', new=AsyncMock()) as delay:
            with self.assertRaises(ConnectionClosedError):
                await control(Path('/unused'), 'wake', CONFIG)
            self.assertEqual(attempt.await_count, 4)
            self.assertEqual([call.args[0] for call in delay.await_args_list], [2, 4, 8])

    async def test_wifi_timeout_is_retried(self):
        with patch('controller.control_once', new=AsyncMock(side_effect=[OSError('unreachable'), 'ok'])) as attempt, patch('controller.asyncio.sleep', new=AsyncMock()):
            self.assertEqual(await control(Path('/unused'), 'wake', CONFIG), 'ok')
            self.assertEqual(attempt.await_count, 2)

    async def test_pairing_errors_and_other_policy_rejections_not_retried(self):
        for error in [ValueError('not paired'), ConnectionClosedError(Close(1008, 'Unauthorized'), None)]:
            with patch('controller.control_once', new=AsyncMock(side_effect=error)) as attempt:
                with self.assertRaises(type(error)):
                    await control(Path('/unused'), 'wake', CONFIG)
                self.assertEqual(attempt.await_count, 1)

    async def test_sleep_is_not_replayed_later(self):
        with patch('controller.control_once', new=AsyncMock(side_effect=self.ews())) as attempt:
            with self.assertRaises(ConnectionClosedError):
                await control(Path('/unused'), 'sleep', CONFIG)
            self.assertEqual(attempt.await_count, 1)

class StandbyTests(unittest.IsolatedAsyncioTestCase):
    async def test_known_standby_wakes_and_selects_mac_from_other_input(self):
        first, second = AsyncMock(), AsyncMock()
        first.client_key = second.client_key = 'synthetic'
        first.connect.side_effect = ConnectionClosedError(Close(1008, 'Try Again Later (EWS)'), None)
        second.get_power_state.return_value = {'state': 'Active'}
        second.get_current_app.side_effect = ['com.webos.app.hdmi1', 'com.webos.app.hdmi3']
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            remember_power(base, CONFIG, {'state': 'Active Standby'})
            with patch('controller.WebOsClient.create', new=AsyncMock(side_effect=[first, second])), patch('controller.asyncio.sleep', new=AsyncMock()), patch('controller.wake_on_lan') as wol:
                self.assertEqual(await control(base, 'wake', CONFIG), 'Selected HDMI_3')
                wol.assert_called_once()
        second.set_input.assert_awaited_once_with('HDMI_3')

    async def test_active_other_input_overrides_old_standby_observation(self):
        for action in ['wake', 'attach']:
            client = AsyncMock(); client.client_key = 'synthetic'
            client.get_power_state.return_value = {'state': 'Active'}
            client.get_current_app.return_value = 'com.webos.app.hdmi1'
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory); remember_power(base, CONFIG, {'state': 'Active Standby'})
                with patch('controller.WebOsClient.create', new=AsyncMock(return_value=client)), patch('controller.wake_on_lan') as wol:
                    self.assertEqual(await control(base, action, CONFIG), 'Other input: skipped')
                    wol.assert_not_called()
            client.set_input.assert_not_awaited(); client.turn_screen_on.assert_not_awaited()

    async def test_screen_off_other_input_is_protected(self):
        client = AsyncMock(); client.client_key = 'synthetic'
        client.get_power_state.return_value = {'state': 'Screen Off'}
        client.get_current_app.return_value = 'com.webos.app.hdmi1'
        with tempfile.TemporaryDirectory() as directory, patch('controller.WebOsClient.create', new=AsyncMock(return_value=client)), patch('controller.wake_on_lan') as wol:
            await control(Path(directory), 'attach', CONFIG)
            wol.assert_not_called()
        client.set_input.assert_not_awaited(); client.turn_screen_on.assert_not_awaited()

    async def test_unknown_state_wakes_and_claims_input_without_history(self):
        for action in ['wake', 'attach']:
            for error in [ConnectionClosedError(Close(1008, 'Try Again Later (EWS)'), None), OSError('unreachable')]:
                first, second = AsyncMock(), AsyncMock()
                first.client_key = second.client_key = 'synthetic'
                first.connect.side_effect = error
                second.get_power_state.return_value = {'state': 'Active'}
                second.get_current_app.side_effect = ['com.webos.app.hdmi1', 'com.webos.app.hdmi3']
                with tempfile.TemporaryDirectory() as directory, patch('controller.WebOsClient.create', new=AsyncMock(side_effect=[first, second])), patch('controller.asyncio.sleep', new=AsyncMock()), patch('controller.wake_on_lan') as wol:
                    self.assertEqual(await control(Path(directory), action, CONFIG), 'Selected HDMI_3')
                    wol.assert_called_once()
                second.set_input.assert_awaited_once_with('HDMI_3')

    def test_only_explicit_standby_for_same_tv_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.assertFalse(observed_standby(base, CONFIG))
            remember_power(base, CONFIG, {'state': 'Active Standby'})
            self.assertTrue(observed_standby(base, CONFIG))
            self.assertFalse(observed_standby(base, {**CONFIG, 'ip': '192.0.2.11'}))
            remember_power(base, CONFIG, {'state': 'Active'})
            self.assertFalse(observed_standby(base, CONFIG))

if __name__ == '__main__':
    unittest.main()
