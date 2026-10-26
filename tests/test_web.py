"""De app van buitenaf: inloggen, lessen, reflecties, kookmodus en boodschappen."""

import io
from datetime import date

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from PIL import Image

from fond.config import PROJECT_ROOT, Settings
from fond.main import create_app

WACHTWOORD = "een-lang-test-wachtwoord"
EMAIL = "kok@example.com"


@pytest.fixture(scope="module")
def wachtwoord_hash():
    return PasswordHasher().hash(WACHTWOORD)


def maak_settings(tmp_path, **extra) -> Settings:
    return Settings(
        content_dir=PROJECT_ROOT / "content", data_dir=tmp_path, secret_key="test", **extra
    )


@pytest.fixture
def app(tmp_path):
    return create_app(maak_settings(tmp_path))


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def aanmelden(c: TestClient, email: str = EMAIL, naam: str = "Kok", **velden):
    data = {"naam": naam, "email": email, "wachtwoord": WACHTWOORD, "herhaling": WACHTWOORD}
    return c.post("/aanmelden", data=data | velden, follow_redirects=False)


@pytest.fixture
def ingelogd(client):
    r = aanmelden(client)
    assert r.status_code == 303 and r.headers["location"] == "/?melding=welkom"
    return client


@pytest.fixture
def tweede(app, ingelogd):
    """Een tweede gebruiker in dezelfde app, met een eigen cookie."""
    with TestClient(app) as c:
        assert aanmelden(c, "ander@example.com", "Ander").status_code == 303
        yield c


def inloggen(c: TestClient, email: str = EMAIL, wachtwoord: str = WACHTWOORD, **extra):
    data = {"email": email, "wachtwoord": wachtwoord} | extra
    return c.post("/login", data=data, follow_redirects=False)


def test_zonder_login_naar_loginpagina(client):
    r = client.get("/les/mise-en-place", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?volgende=/les/mise-en-place"
    assert client.get("/gezond").json() == {"status": "ok"}
    assert client.get("/static/css/fond.css").status_code == 200


def test_htmx_zonder_login(client):
    r = client.post("/les/mise-en-place/vinkje/x", headers={"HX-Request": "true"})
    assert r.status_code == 401 and r.headers["HX-Redirect"] == "/login"


def test_fout_wachtwoord_en_blokkade(ingelogd):
    ingelogd.post("/uitloggen")
    for _ in range(5):
        r = inloggen(ingelogd, wachtwoord="fout")
        assert "klopt niet" in r.text
    assert "Te veel pogingen" in inloggen(ingelogd).text


def test_onbekend_adres_zelfde_melding(client):
    r = inloggen(client, "niemand@example.com")
    assert "Dat e-mailadres of wachtwoord klopt niet" in r.text


def test_inloggen_met_hoofdletters(ingelogd):
    ingelogd.post("/uitloggen")
    assert inloggen(ingelogd, " Kok@Example.COM ").status_code == 303


def test_geen_open_redirect(ingelogd):
    ingelogd.post("/uitloggen")
    r = inloggen(ingelogd, volgende="//evil.example")
    assert r.headers["location"] == "/"


def test_overzicht(ingelogd):
    r = ingelogd.get("/")
    assert r.status_code == 200
    assert "Begin hier" in r.text and "Mise en place" in r.text
    assert "Chef de partie" in r.text and "binnenkort" in r.text


def test_lespagina_met_porties(ingelogd):
    r = ingelogd.get("/les/mise-en-place")
    assert "500 g" in r.text  # gehakt, 3 porties (basis)
    assert "Rinderhackfleisch" in r.text
    r = ingelogd.get("/les/mise-en-place?porties=6")
    assert "1 kg" in r.text  # 2× gehakt
    assert "Aan tafel" in r.text and "Meal prep" in r.text


def test_onbekende_les(ingelogd):
    r = ingelogd.get("/les/bestaat-niet")
    assert r.status_code == 404 and "Niet gevonden" in r.text


def test_vinkje_aan_en_uit(ingelogd):
    pagina = ingelogd.get("/les/mise-en-place").text
    punt = pagina.split('id="punt-')[1].split('"')[0]
    r = ingelogd.post(f"/les/mise-en-place/vinkje/{punt}")
    assert 'aria-checked="true"' in r.text
    r = ingelogd.post(f"/les/mise-en-place/vinkje/{punt}")
    assert 'aria-checked="false"' in r.text


def foto_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (3000, 2000), "orange").save(buf, "JPEG")
    return buf.getvalue()


def test_reflectie_rondt_les_af_en_opent_volgende(ingelogd, tmp_path):
    r = ingelogd.post(
        "/les/mise-en-place/reflectie",
        data={
            "cijfer": "8",
            "gekookt_op": date.today().isoformat(),
            "porties": "3",
            "wat_lukte": "Alles stond klaar",
            "wat_niet": "Te weinig zout",
        },
        files={"foto": ("chili.jpg", foto_bytes(), "image/jpeg")},
    )
    assert r.status_code == 200 and "Deze les is af" in r.text
    assert "Volgende: Het koksmes" in r.text
    fotos = list((tmp_path / "fotos").glob("*.jpg"))
    assert len(fotos) == 1
    assert max(Image.open(fotos[0]).size) == 1600  # verkleind
    logboek = ingelogd.get("/logboek").text
    assert "Te weinig zout" in logboek and "/foto/" in logboek
    assert ingelogd.get(f"/foto/{fotos[0].name}").status_code == 200
    assert ingelogd.get("/foto/..%2Ffond.db").status_code == 404


def test_reflectie_op_les_op_slot(ingelogd):
    r = ingelogd.post(
        "/les/bestaat-niet/reflectie", data={"cijfer": "8", "gekookt_op": "2026-01-01"}
    )
    assert r.status_code in (403, 404)


def test_ongeldige_foto(ingelogd):
    r = ingelogd.post(
        "/les/mise-en-place/reflectie",
        data={"cijfer": "5", "gekookt_op": "2026-01-01"},
        files={"foto": ("x.jpg", b"geen foto", "image/jpeg")},
    )
    assert r.status_code == 400


def test_zelftoets(ingelogd):
    r = ingelogd.post(
        "/module/werkplek/beheerst", data={"uitspraak": ["1"]}, follow_redirects=False
    )
    assert "zelftoets" in r.headers["location"]
    ingelogd.post("/module/werkplek/beheerst", data={"uitspraak": ["1", "2", "3"]})
    assert "badge-beheerst" in ingelogd.get("/").text
    ingelogd.post("/module/werkplek/intrekken")
    assert "badge-beheerst" not in ingelogd.get("/").text


def test_kookmodus(ingelogd):
    r = ingelogd.get("/les/mise-en-place/koken?porties=2")
    assert r.status_code == 200
    assert 'data-timer="1800"' in r.text  # 30 min sudderen
    assert "2 porties" in r.text


def test_boodschappenlijst(ingelogd):
    assert "Je lijst is leeg" in ingelogd.get("/boodschappen").text
    ingelogd.post("/boodschappen/toevoegen", data={"les_id": "mise-en-place", "porties": "3"})
    ingelogd.post("/boodschappen/toevoegen", data={"les_id": "het-koksmes", "porties": "3"})
    r = ingelogd.get("/boodschappen").text
    # Paprika komt in beide recepten voor: opgeteld.
    assert "Paprika rot" in r and "<strong>2</strong>" in r
    # Looproute: groente vóór vlees, basisvoorraad als laatste.
    assert r.index("Obst &amp; Gemüse") < r.index("Fleisch") < r.index("Check thuis")
    ingelogd.post("/boodschappen/leegmaken")
    assert "Je lijst is leeg" in ingelogd.get("/boodschappen").text


def test_boodschappen_per_les(ingelogd):
    r = ingelogd.get("/les/mise-en-place/boodschappen?porties=6").text
    assert "1 kg" in r and "2× 500 g" in r


def test_woordenlijst(ingelogd):
    r = ingelogd.get("/woordenlijst").text
    assert 'id="brunoise"' in r and "Aangeleerd in: Het koksmes" in r


def test_uitloggen(ingelogd):
    ingelogd.post("/uitloggen")
    assert ingelogd.get("/", follow_redirects=False).status_code == 303
    assert inloggen(ingelogd).status_code == 303
    assert ingelogd.get("/").status_code == 200


# --- Aanmelden en accounts --------------------------------------------------------


def test_aanmelden_logt_meteen_in(ingelogd):
    r = ingelogd.get("/?melding=welkom")
    assert "Welkom bij Fond, Kok" in r.text
    assert "Kok" in ingelogd.get("/account").text


@pytest.mark.parametrize(
    ("velden", "fout"),
    [
        ({"wachtwoord": "kort", "herhaling": "kort"}, "minstens 12 tekens"),
        ({"herhaling": "iets-heel-anders-dan"}, "niet gelijk"),
        ({"email": "geen-adres"}, "geen e-mailadres"),
        ({"naam": "  "}, "Vul een naam in"),
    ],
)
def test_aanmelden_controleert_formulier(client, velden, fout):
    r = aanmelden(client, **velden)
    assert r.status_code == 200 and fout in r.text
    assert client.get("/", follow_redirects=False).status_code == 303


def test_aanmelden_dubbel_adres(ingelogd):
    ingelogd.post("/uitloggen")
    r = aanmelden(ingelogd, email="KOK@example.com")
    assert "al een account" in r.text


def test_aanmelden_beperkt_per_ip(client):
    for i in range(3):
        assert aanmelden(client, f"kok{i}@example.com").status_code == 303
    assert "te veel accounts" in aanmelden(client, "kok9@example.com").text


def test_aanmelden_gesloten(tmp_path):
    with TestClient(create_app(maak_settings(tmp_path, registratie=False))) as c:
        assert "gesloten" in c.get("/aanmelden").text
        assert "Meld je aan" not in c.get("/login").text
        assert aanmelden(c).status_code == 403


def test_gebruikers_zien_elkaars_gegevens_niet(ingelogd, tweede, tmp_path):
    ingelogd.post(
        "/les/mise-en-place/reflectie",
        data={"cijfer": "7", "gekookt_op": "2026-10-01", "wat_niet": "Geheim van kok"},
        files={"foto": ("chili.jpg", foto_bytes(), "image/jpeg")},
    )
    ingelogd.post("/boodschappen/toevoegen", data={"les_id": "mise-en-place", "porties": "3"})
    ingelogd.post("/module/werkplek/beheerst", data={"uitspraak": ["1", "2", "3"]})
    foto = next((tmp_path / "fotos").glob("*.jpg")).name

    assert "Geheim van kok" in ingelogd.get("/logboek").text
    assert "Geheim van kok" not in tweede.get("/logboek").text
    assert "Je lijst is leeg" in tweede.get("/boodschappen").text
    assert "badge-beheerst" not in tweede.get("/").text
    assert "Begin hier" in tweede.get("/").text
    assert tweede.get(f"/foto/{foto}").status_code == 404
    assert ingelogd.get(f"/foto/{foto}").status_code == 200
    reflectie_id = ingelogd.get("/logboek").text.split("/reflectie/")[1].split("/")[0]
    assert tweede.post(f"/reflectie/{reflectie_id}/verwijderen").status_code == 404
    assert "Geheim van kok" in ingelogd.get("/logboek").text


def test_vinkjes_per_gebruiker(ingelogd, tweede):
    pagina = ingelogd.get("/les/mise-en-place").text
    punt = pagina.split('id="punt-')[1].split('"')[0]
    ingelogd.post(f"/les/mise-en-place/vinkje/{punt}")
    assert 'aria-checked="true"' not in tweede.get("/les/mise-en-place").text
    assert 'aria-checked="true"' in tweede.post(f"/les/mise-en-place/vinkje/{punt}").text


def test_gegevens_wijzigen(ingelogd, tweede):
    r = ingelogd.post("/account/gegevens", data={"naam": "Chef", "email": "chef@example.com"})
    assert "Je gegevens zijn bewaard" in r.text and "Ingelogd als Chef" in r.text
    r = ingelogd.post("/account/gegevens", data={"naam": "Chef", "email": "ander@example.com"})
    assert r.status_code == 400 and "al een account" in r.text
    ingelogd.post("/uitloggen")
    assert inloggen(ingelogd, "chef@example.com").status_code == 303


def test_wachtwoord_wijzigen_logt_andere_toestellen_uit(app, ingelogd):
    with TestClient(app) as telefoon:
        assert inloggen(telefoon).status_code == 303
        nieuw = "een-ander-lang-wachtwoord"
        r = ingelogd.post(
            "/account/wachtwoord", data={"huidig": "fout", "wachtwoord": nieuw, "herhaling": nieuw}
        )
        assert r.status_code == 400 and "huidige wachtwoord klopt niet" in r.text
        r = ingelogd.post(
            "/account/wachtwoord",
            data={"huidig": WACHTWOORD, "wachtwoord": nieuw, "herhaling": nieuw},
        )
        assert "wachtwoord is gewijzigd" in r.text
        assert ingelogd.get("/").status_code == 200  # dit toestel blijft ingelogd
        assert telefoon.get("/", follow_redirects=False).status_code == 303
        assert inloggen(telefoon).status_code == 200  # oud wachtwoord
        assert inloggen(telefoon, wachtwoord=nieuw).status_code == 303


def test_account_verwijderen(ingelogd, tweede, tmp_path):
    ingelogd.post(
        "/les/mise-en-place/reflectie",
        data={"cijfer": "7", "gekookt_op": "2026-10-01"},
        files={"foto": ("chili.jpg", foto_bytes(), "image/jpeg")},
    )
    tweede.post(
        "/les/mise-en-place/reflectie",
        data={"cijfer": "9", "gekookt_op": "2026-10-02"},
        files={"foto": ("chili.jpg", foto_bytes(), "image/jpeg")},
    )
    assert len(list((tmp_path / "fotos").glob("*.jpg"))) == 2
    r = ingelogd.post("/account/verwijderen", data={"wachtwoord": "fout"})
    assert r.status_code == 400 and "staat er nog" in r.text
    r = ingelogd.post("/account/verwijderen", data={"wachtwoord": WACHTWOORD})
    assert "account en alles wat erbij hoorde zijn verwijderd" in r.text
    assert len(list((tmp_path / "fotos").glob("*.jpg"))) == 1
    assert inloggen(ingelogd).status_code == 200
    assert "9" in tweede.get("/logboek").text and "keer gekookt" in tweede.get("/logboek").text
    # Het adres is weer vrij.
    assert aanmelden(ingelogd).status_code == 303
    assert "Nog niets gekookt" in ingelogd.get("/logboek").text


def test_oude_cookie_van_verwijderd_account(app, ingelogd):
    """Een cookie op een ander toestel van een verwijderd account werkt niet meer,
    ook niet als er daarna een nieuw account bij komt."""
    with TestClient(app) as telefoon:
        assert inloggen(telefoon).status_code == 303
        ingelogd.post("/account/verwijderen", data={"wachtwoord": WACHTWOORD})
        with TestClient(app) as nieuw:
            aanmelden(nieuw, "nieuw@example.com", "Nieuw")
        r = telefoon.get("/account", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_eigenaar_van_voor_de_accounts(tmp_path, wachtwoord_hash):
    """Gegevens van vóór de accounts gaan naar 'eigenaar', met het oude wachtwoord."""
    import sqlite3

    from alembic import command

    from fond.db import maak_engine
    from fond.migreren import alembic_config

    settings = maak_settings(tmp_path, password_hash=wachtwoord_hash)
    command.upgrade(
        alembic_config(settings.database_url, maak_engine(settings.database_url)), "0001"
    )
    with sqlite3.connect(tmp_path / "fond.db") as con:
        con.execute(
            "INSERT INTO reflectie (les_id, gekookt_op, porties, cijfer, wat_lukte, wat_niet,"
            " volgende_keer) VALUES ('mise-en-place', '2026-10-01', 3, 8, 'Oud', '', '')"
        )
        con.execute("INSERT INTO lijst_item (les_id, porties) VALUES ('het-koksmes', 2)")
    with TestClient(create_app(settings)) as c:
        assert inloggen(c, "eigenaar").status_code == 303
        assert "Oud" in c.get("/logboek").text
        assert "Het koksmes" in c.get("/boodschappen").text
        assert "Vul hier je eigen e-mailadres in" in c.get("/account").text
        # Een nieuw account begint leeg.
        c.post("/uitloggen")
        aanmelden(c)
        assert "Nog niets gekookt" in c.get("/logboek").text


def test_pwa_bestanden_openbaar(client):
    assert client.get("/sw.js").status_code == 200
    assert client.get("/manifest.webmanifest").json()["short_name"] == "Fond"
    assert client.get("/offline").status_code == 200
    # Maar de lijst met lessen niet.
    assert client.get("/offline.json", follow_redirects=False).status_code == 303


def test_offline_lijst(ingelogd):
    data = ingelogd.get("/offline.json").json()
    assert "/les/mise-en-place" in data["urls"]
    assert "/les/mise-en-place/koken?porties=3" in data["urls"]
    assert any(u.startswith("/static/css/fond.css?v=") for u in data["statisch"])


def test_beveiligingskoppen(client):
    r = client.get("/login")
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "<script>" not in r.text  # geen inline scripts (CSP)


# --- Widget -----------------------------------------------------------------------


def widgetsleutel(c: TestClient) -> str:
    r = c.post("/account/widget")
    assert r.headers["Cache-Control"] == "no-store"
    return r.text.split('class="sleutel" type="text" value="')[1].split('"')[0]


def test_widget_vraagt_juiste_sleutel(ingelogd):
    assert ingelogd.get("/api/widget").status_code == 401
    fout = {"Authorization": "Bearer fout"}
    assert ingelogd.get("/api/widget", headers=fout).status_code == 401
    assert ingelogd.get("/api/widget", headers={"Authorization": "Bearer "}).status_code == 401


def test_widget_per_account(ingelogd, tweede):
    ingelogd.post("/boodschappen/toevoegen", data={"les_id": "mise-en-place", "porties": "3"})
    mijn, andere = widgetsleutel(ingelogd), widgetsleutel(tweede)
    assert mijn != andere
    get = lambda s: ingelogd.get("/api/widget", headers={"Authorization": f"Bearer {s}"})  # noqa: E731
    assert get(mijn).json()["boodschappen"] == 1
    assert get(andere).json()["boodschappen"] == 0
    nieuw = widgetsleutel(ingelogd)
    assert get(mijn).status_code == 401 and get(nieuw).status_code == 200
    ingelogd.post("/account/widget/intrekken")
    assert get(nieuw).status_code == 401


def test_oude_widgetsleutel_geeft_eerste_account(tmp_path):
    with TestClient(create_app(maak_settings(tmp_path, widget_token="sleutel"))) as c:
        assert c.get("/api/widget", headers={"Authorization": "Bearer sleutel"}).status_code == 401
        aanmelden(c)
        r = c.get("/api/widget", headers={"Authorization": "Bearer sleutel"})
        assert r.status_code == 200


def test_widget_geeft_volgende_les(ingelogd):
    sleutel = widgetsleutel(ingelogd)
    r = ingelogd.get("/api/widget", headers={"Authorization": f"Bearer {sleutel}"})
    assert r.status_code == 200
    data = r.json()
    assert data["volgende"]["titel"] and data["volgende"]["url"].startswith("/les/")
    assert data["niveau"]["naam"] == "Commis" and data["niveau"]["af"] == 0
    assert data["totaal"] > 0 and data["herhalingen"] == [] and data["laatst"] is None
