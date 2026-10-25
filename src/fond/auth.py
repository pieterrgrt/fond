"""Inloggen voor één gebruiker.

Het wachtwoord staat alleen als Argon2-hash in de omgeving (FOND_PASSWORD_HASH).
Na inloggen krijg je een ondertekende sessiecookie die lang geldig blijft, zodat de
app op je telefoon niet steeds opnieuw vraagt. Mislukte pogingen worden beperkt,
zodat niemand vanaf het open internet je wachtwoord kan raden.
"""

import time
from collections import deque
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Paden die zonder inloggen werken: de loginpagina zelf, statische bestanden
# (lettertypen, CSS), en wat de browser nodig heeft om de app te installeren.
OPENBAAR = ("/login", "/static/", "/sw.js", "/manifest.webmanifest", "/gezond", "/favicon.ico")

_hasher = PasswordHasher()


def controleer_wachtwoord(wachtwoord: str, hash_: str) -> bool:
    if not hash_:
        return False
    try:
        return _hasher.verify(hash_, wachtwoord)
    except (VerificationError, InvalidHashError):
        return False


class Pogingen:
    """Telt mislukte pogingen: per IP-adres, en in totaal (tegen veel adressen)."""

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


def is_ingelogd(request: Request) -> bool:
    return request.session.get("ingelogd") is True


class LoginVereist(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        pad = request.url.path
        if is_ingelogd(request) or pad.startswith(OPENBAAR):
            return await call_next(request)
        if request.headers.get("HX-Request"):
            # HTMX volgt geen gewone redirect voor de hele pagina; dit wel.
            return Response(status_code=401, headers={"HX-Redirect": "/login"})
        volgende = quote(pad + (f"?{request.url.query}" if request.url.query else ""))
        return RedirectResponse(f"/login?volgende={volgende}", status_code=303)


def veilige_volgende(volgende: str | None) -> str:
    """Alleen doorsturen naar een pad binnen de app (geen 'open redirect')."""
    if volgende and volgende.startswith("/") and not volgende.startswith("//"):
        return volgende
    return "/"
