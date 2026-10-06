import pytest

from africa_extension_agent import config
from africa_extension_agent.db.seed import seed


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "t.sqlite"
    seed(path)
    monkeypatch.setattr(config, "DB_PATH", path)
    return path
