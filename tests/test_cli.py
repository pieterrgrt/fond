from fond import cli
from fond.config import Settings, get_settings
from fond.db import maak_engine
from fond.migreren import migreer


def test_check_echte_inhoud(capsys):
    assert cli.check() == 0
    assert "Inhoud in orde" in capsys.readouterr().out


def test_backup(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path)
    migreer(settings.database_url, maak_engine(settings.database_url))
    get_settings.cache_clear()
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    assert cli.backup() == 0
    assert len(list((tmp_path / "backups").glob("fond-*.db"))) == 1


def test_hash_met_dubbele_dollars_uit_compose_env():
    assert Settings(password_hash="$$argon2id$$v=19$$x").password_hash == "$argon2id$v=19$x"
