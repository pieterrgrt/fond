"""Accounts: aanmelden, inloggen, wachtwoorden en widgetsleutels.

Wachtwoorden staan alleen als Argon2-hash in de database. Widgetsleutels alleen als
SHA-256: ze zijn lang en willekeurig, dus een trage hash is daar niet nodig.
"""

import hashlib
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from fond.db import Gebruiker, Reflectie

MIN_WACHTWOORD = 12
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_hasher = PasswordHasher()
# Om tegen te vergelijken als het e-mailadres niet bestaat: dan duurt een mislukte
# poging even lang, en verraadt de tijd niet welke adressen een account hebben.
_NEP_HASH = _hasher.hash(secrets.token_urlsafe(16))


class AccountFout(ValueError):
    """Iets in een formulier klopt niet; de tekst is voor de gebruiker bedoeld."""


def maak_hash(wachtwoord: str) -> str:
    return _hasher.hash(wachtwoord)


def controleer_wachtwoord(wachtwoord: str, hash_: str) -> bool:
    if not hash_:
        return False
    try:
        return _hasher.verify(hash_, wachtwoord)
    except (VerificationError, InvalidHashError):
        return False


def normaliseer_email(email: str) -> str:
    return email.strip().lower()


def keur_wachtwoord(wachtwoord: str, herhaling: str) -> None:
    if len(wachtwoord) < MIN_WACHTWOORD:
        raise AccountFout(f"Kies een wachtwoord van minstens {MIN_WACHTWOORD} tekens.")
    if wachtwoord != herhaling:
        raise AccountFout("De twee wachtwoorden zijn niet gelijk.")


def keur_gegevens(sessie: Session, naam: str, email: str, zelf: int | None = None) -> None:
    if not naam or len(naam) > 100:
        raise AccountFout("Vul een naam in (hooguit 100 tekens).")
    if len(email) > 254 or not EMAIL.match(email):
        raise AccountFout("Dat lijkt geen e-mailadres.")
    bestaand = sessie.scalar(select(Gebruiker.id).where(Gebruiker.email == email))
    if bestaand is not None and bestaand != zelf:
        raise AccountFout("Er is al een account met dit e-mailadres.")


def maak_gebruiker(
    sessie: Session, naam: str, email: str, wachtwoord: str, herhaling: str
) -> Gebruiker:
    naam, email = naam.strip(), normaliseer_email(email)
    keur_gegevens(sessie, naam, email)
    keur_wachtwoord(wachtwoord, herhaling)
    gebruiker = Gebruiker(naam=naam, email=email, wachtwoord_hash=maak_hash(wachtwoord))
    sessie.add(gebruiker)
    sessie.commit()
    return gebruiker


def wijzig_gegevens(sessie: Session, gebruiker: Gebruiker, naam: str, email: str) -> None:
    naam, email = naam.strip(), normaliseer_email(email)
    keur_gegevens(sessie, naam, email, zelf=gebruiker.id)
    gebruiker.naam, gebruiker.email = naam, email
    sessie.commit()


def zet_wachtwoord(sessie: Session, gebruiker: Gebruiker, wachtwoord: str) -> None:
    """Nieuw wachtwoord; alle bestaande sessies (andere toestellen) vervallen."""
    gebruiker.wachtwoord_hash = maak_hash(wachtwoord)
    gebruiker.sessie_versie += 1
    sessie.commit()


def inloggen(sessie: Session, email: str, wachtwoord: str) -> Gebruiker | None:
    gebruiker = sessie.scalar(select(Gebruiker).where(Gebruiker.email == normaliseer_email(email)))
    if gebruiker is None:
        controleer_wachtwoord(wachtwoord, _NEP_HASH)
        return None
    if not controleer_wachtwoord(wachtwoord, gebruiker.wachtwoord_hash):
        return None
    if _hasher.check_needs_rehash(gebruiker.wachtwoord_hash):
        gebruiker.wachtwoord_hash = maak_hash(wachtwoord)
        sessie.commit()
    return gebruiker


def sleutel_hash(sleutel: str) -> str:
    return hashlib.sha256(sleutel.encode()).hexdigest()


def nieuwe_widgetsleutel(sessie: Session, gebruiker: Gebruiker) -> str:
    """Maakt een nieuwe sleutel (de oude werkt dan niet meer) en geeft hem één keer terug."""
    sleutel = secrets.token_urlsafe(32)
    gebruiker.widget_sleutel = sleutel_hash(sleutel)
    sessie.commit()
    return sleutel


def gebruiker_bij_sleutel(sessie: Session, sleutel: str) -> Gebruiker | None:
    if not sleutel:
        return None
    return sessie.scalar(select(Gebruiker).where(Gebruiker.widget_sleutel == sleutel_hash(sleutel)))


def fotos_van(sessie: Session, gebruiker_id: int) -> list[str]:
    return [
        f
        for f in sessie.scalars(
            select(Reflectie.foto).where(Reflectie.gebruiker_id == gebruiker_id)
        )
        if f
    ]


def koppel_eigenaar(fabriek: sessionmaker[Session], wachtwoord_hash: str) -> None:
    """Het account uit de migratie (gegevens van vóór de accounts) krijgt het oude
    wachtwoord uit FOND_PASSWORD_HASH, zodat je daarmee kunt inloggen."""
    if not wachtwoord_hash:
        return
    with fabriek() as sessie:
        sessie.execute(
            update(Gebruiker)
            .where(Gebruiker.wachtwoord_hash == "")
            .values(wachtwoord_hash=wachtwoord_hash)
        )
        sessie.commit()
