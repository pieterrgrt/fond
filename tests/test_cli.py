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


def test_gebruikers_en_wachtwoord_herstellen(tmp_path, monkeypatch, capsys):
    from fond.db import maak_sessiefabriek
    from fond.gebruikers import inloggen, maak_gebruiker

    settings = Settings(data_dir=tmp_path)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    fabriek = maak_sessiefabriek(maak_engine(settings.database_url))
    migreer(settings.database_url, maak_engine(settings.database_url))
    with fabriek() as sessie:
        maak_gebruiker(sessie, "Kok", "kok@example.com", "oud-en-lang-genoeg", "oud-en-lang-genoeg")

    assert cli.gebruikers_tonen() == 0
    assert "kok@example.com" in capsys.readouterr().out
    assert cli.wachtwoord_herstellen("niemand@example.com") == 1

    antwoorden = iter(["nieuw-en-lang-genoeg", "nieuw-en-lang-genoeg"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(antwoorden))
    assert cli.wachtwoord_herstellen("KOK@example.com") == 0
    with fabriek() as sessie:
        assert inloggen(sessie, "kok@example.com", "oud-en-lang-genoeg") is None
        gebruiker = inloggen(sessie, "kok@example.com", "nieuw-en-lang-genoeg")
        assert gebruiker is not None and gebruiker.sessie_versie == 2
