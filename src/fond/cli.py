"""Opdrachtregel: `fond check`, `fond hash-wachtwoord`, `fond backup`."""

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


def hash_wachtwoord() -> int:
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
    sub.add_parser("hash-wachtwoord", help="maak een wachtwoord-hash en geheime sleutel")
    sub.add_parser("backup", help="maak een kopie van de database in data/backups/")
    args = parser.parse_args()
    sys.exit(
        {"check": check, "hash-wachtwoord": hash_wachtwoord, "backup": backup}[args.opdracht]()
    )
