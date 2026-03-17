import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(autouse=True)
def test_database(tmp_path, monkeypatch):
    test_db = tmp_path / "test_guide_os.db"
    monkeypatch.setenv("DATABASE_PATH", str(test_db))

    import database.db as db_module
    db_module.DB_PATH = str(test_db)
    db_module.init_db()

    yield
