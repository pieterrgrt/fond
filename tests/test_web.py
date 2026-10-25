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


@pytest.fixture(scope="module")
def wachtwoord_hash():
    return PasswordHasher().hash(WACHTWOORD)


@pytest.fixture
def client(tmp_path, wachtwoord_hash):
    settings = Settings(
        content_dir=PROJECT_ROOT / "content",
        data_dir=tmp_path,
        password_hash=wachtwoord_hash,
        secret_key="test",
    )
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def ingelogd(client):
    r = client.post(
        "/login", data={"wachtwoord": WACHTWOORD, "volgende": "/"}, follow_redirects=False
    )
    assert r.status_code == 303
    return client


def test_zonder_login_naar_loginpagina(client):
    r = client.get("/les/mise-en-place", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?volgende=/les/mise-en-place"
    assert client.get("/gezond").json() == {"status": "ok"}
    assert client.get("/static/css/fond.css").status_code == 200


def test_htmx_zonder_login(client):
    r = client.post("/les/mise-en-place/vinkje/x", headers={"HX-Request": "true"})
    assert r.status_code == 401 and r.headers["HX-Redirect"] == "/login"


def test_fout_wachtwoord_en_blokkade(client):
    for _ in range(5):
        r = client.post("/login", data={"wachtwoord": "fout"})
        assert "klopt niet" in r.text
    r = client.post("/login", data={"wachtwoord": WACHTWOORD})
    assert "Te veel pogingen" in r.text


def test_geen_open_redirect(client):
    r = client.post(
        "/login",
        data={"wachtwoord": WACHTWOORD, "volgende": "//evil.example"},
        follow_redirects=False,
    )
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


@pytest.fixture
def widget_client(tmp_path, wachtwoord_hash):
    settings = Settings(
        content_dir=PROJECT_ROOT / "content",
        data_dir=tmp_path,
        password_hash=wachtwoord_hash,
        secret_key="test",
        widget_token="sleutel",
    )
    with TestClient(create_app(settings)) as c:
        yield c


def test_widget_uit_zonder_sleutel(client):
    assert client.get("/api/widget", headers={"Authorization": "Bearer x"}).status_code == 404


def test_widget_vraagt_juiste_sleutel(widget_client):
    assert widget_client.get("/api/widget").status_code == 401
    fout = {"Authorization": "Bearer fout"}
    assert widget_client.get("/api/widget", headers=fout).status_code == 401


def test_widget_geeft_volgende_les(widget_client):
    r = widget_client.get("/api/widget", headers={"Authorization": "Bearer sleutel"})
    assert r.status_code == 200
    data = r.json()
    assert data["volgende"]["titel"] and data["volgende"]["url"].startswith("/les/")
    assert data["niveau"]["naam"] == "Commis" and data["niveau"]["af"] == 0
    assert data["totaal"] > 0 and data["herhalingen"] == [] and data["laatst"] is None
