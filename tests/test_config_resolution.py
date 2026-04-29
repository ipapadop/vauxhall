from pathlib import Path
from unittest.mock import patch
from vauxhall.core.config import find_config_file, get_env

def test_get_env_types():
    with patch.dict("os.environ", {"INT_VAR": "123", "BOOL_VAR": "true"}):
        assert get_env("INT_VAR", 0) == 123
        assert get_env("BOOL_VAR", False) is True
        assert get_env("NONEXISTENT", "default") == "default"

def test_find_config_file_cwd(tmp_path):
    with patch("vauxhall.core.config.Path.cwd", return_value=tmp_path):
        config_file = tmp_path / "test.json"
        config_file.touch()
        assert find_config_file("test.json") == config_file
