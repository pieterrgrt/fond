"""Jinja2-templates en de filters die ze gebruiken (Nederlandse datums, euro's)."""

import hashlib
from datetime import date
from functools import cache
from pathlib import Path

from fastapi.templating import Jinja2Templates

from fond.schalen import getal

TEMPLATES = Path(__file__).parent.parent / "templates"
STATIC = Path(__file__).parent.parent / "static"

MAANDEN = (
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)
DAGEN = ("maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag")

templates = Jinja2Templates(directory=TEMPLATES)


def datum(d: date, met_dag: bool = False) -> str:
    tekst = f"{d.day} {MAANDEN[d.month - 1]} {d.year}"
    return f"{DAGEN[d.weekday()]} {tekst}" if met_dag else tekst


def duur(minuten: int) -> str:
    uren, rest = divmod(minuten, 60)
    if not uren:
        return f"{rest} min"
    return f"{uren} u {rest} min" if rest else f"{uren} u"


def tijd(seconden: int) -> str:
    """Timerduur: 45 -> '45 s', 600 -> '10 min', 5400 -> '1 u 30 min'."""
    if seconden < 60:
        return f"{seconden} s"
    minuten, rest = divmod(seconden, 60)
    return duur(minuten) + (f" {rest} s" if rest else "")


def euro(bedrag: float) -> str:
    return f"€ {bedrag:.2f}".replace(".", ",")


@cache
def static_url(pad: str) -> str:
    """URL met een versie-hash, zodat de browser (en de service worker) een nieuwe
    versie ophaalt zodra het bestand verandert."""
    inhoud = (STATIC / pad).read_bytes()
    return f"/static/{pad}?v={hashlib.sha256(inhoud).hexdigest()[:10]}"


templates.env.filters.update(datum=datum, duur=duur, tijd=tijd, euro=euro, getal=getal)
templates.env.globals.update(static_url=static_url)
