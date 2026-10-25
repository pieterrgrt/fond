"""Opdrachtregel: `uv run fond check`, `uv run fond hash-wachtwoord`."""

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


def main() -> None:
    parser = argparse.ArgumentParser(prog="fond")
    sub = parser.add_subparsers(dest="opdracht", required=True)
    sub.add_parser("check", help="valideer de inhoud in content/")
    sub.add_parser("hash-wachtwoord", help="maak een wachtwoord-hash en geheime sleutel")
    args = parser.parse_args()
    sys.exit({"check": check, "hash-wachtwoord": hash_wachtwoord}[args.opdracht]())
