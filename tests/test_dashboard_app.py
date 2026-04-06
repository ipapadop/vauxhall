import json
import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock dependencies that might not be available or should be isolated
sys_modules_patch = patch.dict('sys.modules', {
    'pyperclip': MagicMock(),
    'paho': MagicMock(),
    'paho.mqtt': MagicMock(),
    'paho.mqtt.client': MagicMock(),
})
sys_modules_patch.start()

from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.mqtt_client import DashboardSubscriber

class TestDashboardComponents(unittest.TestCase):
    def test_ipc_copy_to_clipboard(self):
        ipc = DashboardIPC()
        with patch('pyperclip.copy') as mock_copy:
            result = ipc.copy_to_clipboard("test text")
            mock_copy.assert_called_once_with("test text")
            self.assertTrue(result)

    def test_ipc_copy_to_clipboard_error(self):
        ipc = DashboardIPC()
        with patch('pyperclip.copy', side_effect=Exception("error")):
            result = ipc.copy_to_clipboard("test text")
            self.assertFalse(result)

    def test_subscriber_on_message(self):
        callback = MagicMock()
        subscriber = DashboardSubscriber(callback)
        
        # Create a mock message
        msg = MagicMock()
        data = {"agent": "Gemini", "workspace": "/tmp", "state": "Running"}
        msg.payload = json.dumps(data).encode()
        
        # Call the private method directly for testing
        subscriber._on_message(None, None, msg)
        
        callback.assert_called_once_with(data)

    def test_subscriber_on_message_invalid_json(self):
        callback = MagicMock()
        subscriber = DashboardSubscriber(callback)
        
        # Create a mock message with invalid JSON
        msg = MagicMock()
        msg.payload = b"invalid json"
        
        # Should not raise exception, but also not call callback
        subscriber._on_message(None, None, msg)
        
        callback.assert_not_called()

if __name__ == "__main__":
    unittest.main()
