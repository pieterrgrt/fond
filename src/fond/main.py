"""De FastAPI-app: hier komt alles samen."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from fond.auth import LoginVereist, Pogingen
from fond.config import Settings, get_settings
from fond.content.loader import laad_catalogus
from fond.db import maak_engine, maak_sessiefabriek
from fond.migreren import migreer
from fond.web import routes
from fond.web.templates import templates

STATIC = Path(__file__).parent / "static"


# Alleen eigen bestanden laden: geen externe scripts, lettertypen of trackers.
# Stijlattributen (bv. de breedte van een voortgangsbalk) zijn wel toegestaan.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
    "manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
    "form-action 'self'"
)


class Beveiligingskoppen(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=()")
        if request.url.path.startswith("/static/") and "v=" in request.url.query:
            # Bestanden met een versie-hash veranderen nooit: lang bewaren.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Bij het opstarten: inhoud valideren (een fout stopt de app met een duidelijke
        # melding), en de database bijwerken naar het nieuwste schema.
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.foto_dir.mkdir(parents=True, exist_ok=True)
        engine = maak_engine(settings.database_url)
        migreer(settings.database_url, engine)
        app.state.catalogus = laad_catalogus(settings.content_dir)
        app.state.sessies = maak_sessiefabriek(engine)
        yield
        engine.dispose()

    app = FastAPI(title="Fond", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.pogingen = Pogingen()

    # Volgorde telt: de laatst toegevoegde middleware draait als eerste. De sessie moet
    # er zijn voordat de loginvereiste kijkt of je bent ingelogd.
    app.add_middleware(LoginVereist)
    app.add_middleware(Beveiligingskoppen)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="fond_sessie",
        max_age=settings.session_days * 24 * 3600,
        same_site="lax",
        https_only=settings.secure_cookies,
    )

    @app.exception_handler(StarletteHTTPException)
    async def foutpagina(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/static/") or request.headers.get("HX-Request"):
            return PlainTextResponse(str(exc.detail), status_code=exc.status_code)
        titels = {404: "Niet gevonden", 403: "Niet toegestaan", 413: "Te groot"}
        return templates.TemplateResponse(
            request,
            "fout.html",
            {
                "code": exc.status_code,
                "titel": titels.get(exc.status_code, "Er ging iets mis"),
                "uitleg": exc.detail
                if exc.status_code != 404 or exc.detail != "Not Found"
                else "Deze pagina bestaat niet (meer).",
            },
            status_code=exc.status_code,
        )

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.include_router(routes.router)
    templates.env.globals["settings"] = settings
    return app
