"""Instellingen, gelezen uit omgevingsvariabelen (prefix FOND_) of een .env-bestand.

Geheimen staan nooit in de code: alleen in de omgeving van de server.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOND_", env_file=".env", extra="ignore")

    content_dir: Path = PROJECT_ROOT / "content"
    data_dir: Path = PROJECT_ROOT / "data"

    # Alleen voor gegevens van vóór de accounts: het oude wachtwoord (Argon2-hash)
    # wordt bij het opstarten het wachtwoord van het account "eigenaar".
    password_hash: str = ""
    # Sleutel waarmee de sessiecookie wordt ondertekend. Lang en willekeurig.
    secret_key: str = "dev-only-verander-mij"
    # Op de server altijd True (alleen via HTTPS); lokaal False.
    secure_cookies: bool = False
    # Hoe lang je ingelogd blijft (dagen). Lang, want het is een app op je telefoon.
    session_days: int = 90
    # Mag iedereen zelf een account maken via /aanmelden? Zet op false om dat te sluiten.
    registratie: bool = True
    # Oude, vaste widgetsleutel (van vóór de accounts): geeft het eerste account.
    # Nieuwe sleutels maak je per account op /account. Leeg = uit.
    widget_token: str = ""

    @field_validator("password_hash")
    @classmethod
    def _enkele_dollars(cls, waarde: str) -> str:
        # Docker Compose wil $$ in .env; de app leest .env lokaal zelf. Een
        # Argon2-hash bevat nooit $$, dus beide schrijfwijzen mogen.
        return waarde.replace("$$", "$")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'fond.db'}"

    @property
    def foto_dir(self) -> Path:
        return self.data_dir / "fotos"


@lru_cache
def get_settings() -> Settings:
    return Settings()
