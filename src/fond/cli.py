"""Opdrachtregel: `fond check`, `fond sleutel`, `fond gebruikers`,
`fond wachtwoord-herstellen`, `fond hash-wachtwoord`, `fond backup`."""

import argparse
import getpass
import secrets
import sys

from fond.config import get_settings
from fond.content.loader import InhoudFout, laad_catalogus


def check() -> int:
    """Valideert alle inhoud en meldt fouten. Handig vóór een commit."""
    try:
        cat = laad_catalogus(get_settings().content_dir)
    except InhoudFout as fout:
        print(fout, file=sys.stderr)
        return 1
    print(
        f"Inhoud in orde: {len(cat.niveaus)} niveaus, {len(cat.modules)} modules, "
        f"{len(cat.lessen)} lessen, {len(cat.ingredienten)} ingrediënten, "
        f"{len(cat.technieken)} technieken."
    )
    return 0


def sleutel() -> int:
    """Een geheime sleutel voor de sessiecookies (FOND_SECRET_KEY)."""
    print(f"FOND_SECRET_KEY={secrets.token_urlsafe(48)}")
    return 0


def _sessies():
    from fond.db import maak_engine, maak_sessiefabriek
    from fond.migreren import migreer

    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = maak_engine(settings.database_url)
    migreer(settings.database_url, engine)
    return maak_sessiefabriek(engine)


def gebruikers_tonen() -> int:
    from sqlalchemy import select

    from fond.db import Gebruiker

    with _sessies()() as sessie:
        alle = sessie.scalars(select(Gebruiker).order_by(Gebruiker.id)).all()
        for g in alle:
            print(f"{g.id:>4}  {g.email:<40}  {g.naam}  (sinds {g.aangemaakt:%Y-%m-%d})")
        print(f"{len(alle)} account(s)")
    return 0


def wachtwoord_herstellen(email: str) -> int:
    """Voor wie zijn wachtwoord kwijt is: er gaat geen mail uit, dus dit doet de beheerder."""
    from sqlalchemy import select

    from fond.db import Gebruiker
    from fond.gebruikers import AccountFout, keur_wachtwoord, normaliseer_email, zet_wachtwoord

    with _sessies()() as sessie:
        gebruiker = sessie.scalar(
            select(Gebruiker).where(Gebruiker.email == normaliseer_email(email))
        )
        if gebruiker is None:
            print(f"Geen account met {email}.", file=sys.stderr)
            return 1
        try:
            nieuw = getpass.getpass("Nieuw wachtwoord: ")
            keur_wachtwoord(nieuw, getpass.getpass("Nog een keer: "))
        except AccountFout as fout:
            print(fout, file=sys.stderr)
            return 1
        zet_wachtwoord(sessie, gebruiker, nieuw)
    print(f"Wachtwoord van {gebruiker.email} gewijzigd; overal uitgelogd.")
    return 0


def hash_wachtwoord() -> int:
    """Alleen nog nodig voor een Fond van vóór de accounts (FOND_PASSWORD_HASH)."""
    from argon2 import PasswordHasher

    eerste = getpass.getpass("Nieuw wachtwoord: ")
    if len(eerste) < 12:
        print("Kies minstens 12 tekens.", file=sys.stderr)
        return 1
    if getpass.getpass("Nog een keer: ") != eerste:
        print("De wachtwoorden zijn niet gelijk.", file=sys.stderr)
        return 1
    hash_ = PasswordHasher().hash(eerste)
    # In .env moet elk $ verdubbeld worden, anders leest Docker Compose het als variabele.
    print("\nZet dit in je .env:\n")
    print(f"FOND_PASSWORD_HASH={hash_.replace('$', '$$')}")
    print(f"FOND_SECRET_KEY={secrets.token_urlsafe(48)}")
    return 0


def backup(bewaar: int = 14) -> int:
    """Veilige kopie van de database (ook terwijl de app draait), in data/backups/.

    Foto's staan als losse bestanden in data/fotos/ en hoeven niet gekopieerd te
    worden zolang je de hele map data/ meeneemt in je server-back-up.
    """
    import sqlite3
    from datetime import datetime

    settings = get_settings()
    bron = settings.data_dir / "fond.db"
    if not bron.exists():
        print(f"Geen database gevonden op {bron}.", file=sys.stderr)
        return 1
    map_ = settings.data_dir / "backups"
    map_.mkdir(exist_ok=True)
    doel = map_ / f"fond-{datetime.now():%Y-%m-%d-%H%M}.db"
    with sqlite3.connect(bron) as van, sqlite3.connect(doel) as naar:
        van.backup(naar)
    oude = sorted(map_.glob("fond-*.db"))[:-bewaar]
    for pad in oude:
        pad.unlink()
    print(f"Back-up gemaakt: {doel} ({len(oude)} oude verwijderd)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="fond")
    sub = parser.add_subparsers(dest="opdracht", required=True)
    sub.add_parser("check", help="valideer de inhoud in content/")
    sub.add_parser("sleutel", help="maak een geheime sleutel voor de sessiecookies")
    sub.add_parser("gebruikers", help="toon alle accounts")
    herstel = sub.add_parser(
        "wachtwoord-herstellen", help="zet een nieuw wachtwoord voor een account"
    )
    herstel.add_argument("email")
    sub.add_parser("hash-wachtwoord", help="maak een wachtwoord-hash (oude installaties)")
    sub.add_parser("backup", help="maak een kopie van de database in data/backups/")
    args = parser.parse_args()
    if args.opdracht == "wachtwoord-herstellen":
        sys.exit(wachtwoord_herstellen(args.email))
    opdrachten = {
        "check": check,
        "sleutel": sleutel,
        "gebruikers": gebruikers_tonen,
        "hash-wachtwoord": hash_wachtwoord,
        "backup": backup,
    }
    sys.exit(opdrachten[args.opdracht]())
