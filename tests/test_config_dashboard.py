import json
from pathlib import Path
from vauxhall.dashboard.config import DashboardConfig

def test_dashboard_config_loading(tmp_path):
    config_file = tmp_path / "vauxhall_dashboard.json"
    config_file.write_text(json.dumps({"dashboard": {"width": 1200}}))
    
    config = DashboardConfig.load(config_file)
    assert config.dashboard.width == 1200
    assert config.dashboard.height == 800 # Default
