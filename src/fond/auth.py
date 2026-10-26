"""Ingelogd blijven, en wie er is ingelogd.

Na inloggen krijg je een ondertekende sessiecookie met je account-id, die lang
geldig blijft, zodat de app op je telefoon niet steeds opnieuw vraagt. Mislukte
pogingen worden beperkt, zodat niemand vanaf het open internet wachtwoorden kan
raden. De wachtwoorden zelf staan in gebruikers.py.
"""

import time
from collections import deque
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Paden die zonder inloggen werken: inloggen en aanmelden, statische bestanden
# (lettertypen, CSS), en wat de browser nodig heeft om de app te installeren.
# /api/widget regelt zelf de toegang, met een vaste sleutel (zie routes.widget).
OPENBAAR = {
    "/login",
    "/aanmelden",
    "/sw.js",
    "/manifest.webmanifest",
    "/gezond",
    "/health",
    "/offline",
    "/api/widget",
}
OPENBAAR_MAP = "/static/"


class Pogingen:
    """Telt pogingen binnen een tijdvenster: per IP-adres, en in totaal (tegen veel
    adressen). Voor mislukte logins, en voor nieuwe accounts."""

    def __init__(self, per_ip: int = 5, totaal: int = 30, venster: int = 15 * 60):
        self.per_ip, self.totaal, self.venster = per_ip, totaal, venster
        self._ip: dict[str, deque[float]] = {}
        self._alle: deque[float] = deque()

    def _opschonen(self, rij: deque[float], nu: float) -> None:
        while rij and rij[0] < nu - self.venster:
            rij.popleft()

    def geblokkeerd(self, ip: str, nu: float | None = None) -> bool:
        nu = time.monotonic() if nu is None else nu
        rij = self._ip.get(ip, deque())
        self._opschonen(rij, nu)
        self._opschonen(self._alle, nu)
        return len(rij) >= self.per_ip or len(self._alle) >= self.totaal

    def mislukt(self, ip: str, nu: float | None = None) -> None:
        nu = time.monotonic() if nu is None else nu
        self._ip.setdefault(ip, deque()).append(nu)
        self._alle.append(nu)

    def gelukt(self, ip: str) -> None:
        self._ip.pop(ip, None)


def log_in(request: Request, gebruiker_id: int, versie: int) -> None:
    request.session.clear()
    request.session["gebruiker"] = gebruiker_id
    request.session["versie"] = versie


def ingelogd_als(request: Request) -> tuple[int, int] | None:
    """(account-id, sessieversie) uit de cookie. Of het account nog bestaat en de
    versie klopt, controleert routes.huidige_gebruiker."""
    gebruiker, versie = request.session.get("gebruiker"), request.session.get("versie")
    if isinstance(gebruiker, int) and isinstance(versie, int):
        return gebruiker, versie
    return None


class NietIngelogd(Exception):
    """De cookie hoort bij geen (geldig) account meer: opnieuw inloggen."""


def naar_login(request: Request) -> Response:
    if request.headers.get("HX-Request"):
        # HTMX volgt geen gewone redirect voor de hele pagina; dit wel.
        return Response(status_code=401, headers={"HX-Redirect": "/login"})
    pad = request.url.path
    volgende = quote(pad + (f"?{request.url.query}" if request.url.query else ""))
    return RedirectResponse(f"/login?volgende={volgende}", status_code=303)


class LoginVereist(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        pad = request.url.path
        if ingelogd_als(request) or pad in OPENBAAR or pad.startswith(OPENBAAR_MAP):
            return await call_next(request)
        return naar_login(request)


def veilige_volgende(volgende: str | None) -> str:
    """Alleen doorsturen naar een pad binnen de app (geen 'open redirect')."""
    if volgende and volgende.startswith("/") and not volgende.startswith("//"):
        return volgende
    return "/"
