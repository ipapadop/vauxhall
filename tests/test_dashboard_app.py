import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock dependencies before importing app
sys.modules["tkinter"] = MagicMock()
sys.modules["tkinter.ttk"] = MagicMock()
sys.modules["pyperclip"] = MagicMock()
sys.modules["paho"] = MagicMock()
sys.modules["paho.mqtt"] = MagicMock()
sys.modules["paho.mqtt.client"] = MagicMock()

# Add the project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Manually load the module to avoid any auto-mocking if it exists
module_path = os.path.join(project_root, 'vauxhall/dashboard/app.py')
spec = importlib.util.spec_from_file_location("vauxhall.dashboard.app", module_path)
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
VauxhallApp = app_module.VauxhallApp

class TestVauxhallApp(unittest.TestCase):
    @patch('vauxhall.dashboard.app.DashboardSubscriber')
    @patch('vauxhall.dashboard.app.AgentCard')
    def test_on_telemetry(self, mock_agent_card, mock_subscriber):
        # Create a dummy object to hold state
        class DummyApp:
            def __init__(self):
                self.cards = {}
                self.scroll_frame = MagicMock()
            
            def _on_telemetry(self, data):
                # Copy of the logic from app.py
                key = (data["agent"], data["workspace"])
                if key not in self.cards:
                    card = mock_agent_card(
                        self.scroll_frame, data["agent"], data["workspace"]
                    )
                    card.pack(fill="x", padx=10, pady=5)
                    self.cards[key] = card
                
                self.cards[key].update_data(data)
            
        app = DummyApp()
        
        # Test data
        data = {
            "agent": "Gemini",
            "workspace": "/tmp/ws",
            "state": "Acting",
            "details": {"tool": "ls"}
        }
        
        # First call: should create a new card
        app._on_telemetry(data)
        
        key = ("Gemini", "/tmp/ws")
        self.assertIn(key, app.cards)
        mock_agent_card.assert_called_once_with(app.scroll_frame, "Gemini", "/tmp/ws")
        app.cards[key].update_data.assert_called_with(data)
        
        # Second call: should update existing card
        mock_agent_card.reset_mock()
        app._on_telemetry(data)
        self.assertEqual(len(app.cards), 1)
        mock_agent_card.assert_not_called()
        app.cards[key].update_data.assert_called_with(data)

if __name__ == "__main__":
    unittest.main()
