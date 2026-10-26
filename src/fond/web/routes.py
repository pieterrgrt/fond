"""Alle pagina's van Fond.

Server-rendered: elke route geeft HTML terug. HTMX ververst kleine stukjes (een
vinkje, een portiekeuze) zonder de hele pagina te herladen.
"""

import hashlib
import hmac
import re
import uuid
from collections.abc import Iterator
from datetime import date
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from fond import gebruikers
from fond.auth import NietIngelogd, ingelogd_als, log_in, veilige_volgende
from fond.boodschappen import maak_lijst
from fond.content.loader import Catalogus
from fond.content.models import Les
from fond.db import BeheersteModule, Gebruiker, LijstItem, Reflectie, Vinkje
from fond.gebruikers import AccountFout
from fond.herhaling import te_herhalen
from fond.schalen import schaal_recept
from fond.voortgang import Status, Voortgang, les_status, module_status, ontbrekend, volgende_les
from fond.web.templates import STATIC, static_url, templates

router = APIRouter()

PORTIE_KEUZES = (1, 2, 3, 4, 6)
# Wat de service worker vooraf bewaart, naast de pagina's zelf.
STATISCHE_BESTANDEN = (
    "css/fond.css",
    "js/htmx.min.js",
    "js/app.js",
    "js/thema.js",
    "js/koken.js",
    "js/lijst.js",
    "icons/icon.svg",
    "icons/apple-touch-icon.png",
)
MAX_FOTO = 15 * 1024 * 1024
FOTO_NAAM = re.compile(r"^[0-9a-f]{32}\.jpg$")


# --- Afhankelijkheden -------------------------------------------------------------


def catalogus(request: Request) -> Catalogus:
    return request.app.state.catalogus


def db(request: Request) -> Iterator[Session]:
    with request.app.state.sessies() as sessie:
        yield sessie


Cat = Annotated[Catalogus, Depends(catalogus)]
Db = Annotated[Session, Depends(db)]


def huidige_gebruiker(request: Request, sessie: Db) -> Gebruiker:
    ingelogd = ingelogd_als(request)
    gebruiker = sessie.get(Gebruiker, ingelogd[0]) if ingelogd else None
    # Account verwijderd, of het wachtwoord is intussen veranderd: opnieuw inloggen.
    if gebruiker is None or gebruiker.sessie_versie != ingelogd[1]:
        raise NietIngelogd
    return gebruiker


Ik = Annotated[Gebruiker, Depends(huidige_gebruiker)]


def laad_voortgang(sessie: Session, ik: Gebruiker) -> Voortgang:
    return Voortgang(
        afgeronde_lessen=frozenset(
            sessie.scalars(
                select(Reflectie.les_id).where(Reflectie.gebruiker_id == ik.id).distinct()
            )
        ),
        beheerste_modules=frozenset(
            sessie.scalars(
                select(BeheersteModule.module_id).where(BeheersteModule.gebruiker_id == ik.id)
            )
        ),
    )


def gekookte_lessen(sessie: Session, ik: Gebruiker) -> list:
    return sessie.execute(
        select(Reflectie.les_id, Reflectie.gekookt_op).where(Reflectie.gebruiker_id == ik.id)
    ).all()


def mijn_reflectie(sessie: Session, ik: Gebruiker, reflectie_id: int) -> Reflectie:
    rij = sessie.get(Reflectie, reflectie_id)
    if rij is None or rij.gebruiker_id != ik.id:
        raise HTTPException(404)
    return rij


def vind_les(cat: Catalogus, les_id: str) -> Les:
    les = cat.lessen.get(les_id)
    if les is None:
        raise HTTPException(404, "Deze les bestaat niet.")
    return les


def punt_id(tekst: str) -> str:
    return hashlib.sha1(tekst.encode()).hexdigest()[:12]


def kies_porties(les: Les, porties: int | None) -> int:
    standaard = les.meta.recept.porties if les.meta.recept else 1
    return min(max(porties or standaard, 1), 12)


def render(request: Request, template: str, **context) -> HTMLResponse:
    return templates.TemplateResponse(request, template, context)


# --- Inloggen ---------------------------------------------------------------------


def ip_van(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.get("/login")
def login_pagina(request: Request, volgende: str = "/"):
    return render(request, "login.html", volgende=veilige_volgende(volgende), email="", fout=None)


@router.post("/login")
def login(
    request: Request,
    sessie: Db,
    wachtwoord: Annotated[str, Form()],
    email: Annotated[str, Form()] = "",
    volgende: Annotated[str, Form()] = "/",
):
    pogingen = request.app.state.pogingen
    ip = ip_van(request)

    def opnieuw(fout: str):
        return render(request, "login.html", volgende=volgende, email=email, fout=fout)

    if pogingen.geblokkeerd(ip):
        return opnieuw("Te veel pogingen. Probeer het over een kwartier opnieuw.")
    gebruiker = gebruikers.inloggen(sessie, email, wachtwoord)
    if gebruiker is None:
        pogingen.mislukt(ip)
        return opnieuw("Dat e-mailadres of wachtwoord klopt niet.")
    pogingen.gelukt(ip)
    log_in(request, gebruiker.id, gebruiker.sessie_versie)
    return RedirectResponse(veilige_volgende(volgende), status_code=303)


@router.get("/aanmelden")
def aanmelden_pagina(request: Request):
    return render(request, "aanmelden.html", naam="", email="", fout=None)


@router.post("/aanmelden")
def aanmelden(
    request: Request,
    sessie: Db,
    naam: Annotated[str, Form()],
    email: Annotated[str, Form()],
    wachtwoord: Annotated[str, Form()],
    herhaling: Annotated[str, Form()],
):
    def opnieuw(fout: str):
        return render(request, "aanmelden.html", naam=naam, email=email, fout=fout)

    if not request.app.state.settings.registratie:
        raise HTTPException(403, "Aanmelden is gesloten.")
    aanmeldingen = request.app.state.aanmeldingen
    ip = ip_van(request)
    if aanmeldingen.geblokkeerd(ip):
        return opnieuw("Er zijn net te veel accounts gemaakt. Probeer het over een uur opnieuw.")
    try:
        gebruiker = gebruikers.maak_gebruiker(sessie, naam, email, wachtwoord, herhaling)
    except AccountFout as fout:
        return opnieuw(str(fout))
    aanmeldingen.mislukt(ip)  # telt als poging, ook al is hij gelukt
    log_in(request, gebruiker.id, gebruiker.sessie_versie)
    return RedirectResponse("/?melding=welkom", status_code=303)


@router.post("/uitloggen")
def uitloggen(request: Request):
    request.session.clear()
    return RedirectResponse("/login?uitgelogd=1", status_code=303)


@router.get("/gezond")
def gezond():
    return {"status": "ok"}


@router.get("/health")
def health(sessie: Db):
    """Voor de autodeploy: 200 als de app draait en de database antwoordt."""
    try:
        sessie.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "fout", "database": "onbereikbaar"}, status_code=503)
    return {"status": "ok", "database": "ok"}


# --- Widget voor de telefoon -------------------------------------------------------


@router.get("/api/widget")
def widget(request: Request, cat: Cat, sessie: Db):
    """Klein overzicht voor de Scriptable-widget.

    Toegang: Authorization: Bearer <widgetsleutel van je account, zie /account>.
    """
    gegeven = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    ik = gebruikers.gebruiker_bij_sleutel(sessie, gegeven)
    oud = request.app.state.settings.widget_token.strip()
    if ik is None and oud and hmac.compare_digest(gegeven.encode(), oud.encode()):
        ik = sessie.scalar(select(Gebruiker).order_by(Gebruiker.id).limit(1))
    if ik is None:
        return JSONResponse({"fout": "Onbekende sleutel"}, status_code=401)

    vg = laad_voortgang(sessie, ik)
    gekookt = gekookte_lessen(sessie, ik)
    open_lessen = {les.id for les in cat.alle_lessen() if les_status(cat, vg, les) == Status.open}
    volgende = volgende_les(cat, vg)

    def les_info(les: Les | None) -> dict | None:
        if les is None:
            return None
        module = cat.modules[les.meta.module]
        return {
            "id": les.id,
            "titel": les.meta.titel,
            "module": module.titel,
            "niveau": cat.module_niveau[module.id].naam,
            "duur": les.meta.duur,
            "url": f"/les/{les.id}",
        }

    # Het niveau waar je nu in zit: dat van de volgende les, anders het laatste.
    huidig = cat.module_niveau[volgende.meta.module] if volgende else cat.niveaus[-1]
    lessen_niveau = [les for m in huidig.modules for les in cat.lessen_per_module.get(m.id, [])]
    laatst = sessie.execute(
        select(Reflectie.les_id, Reflectie.gekookt_op, Reflectie.cijfer)
        .where(Reflectie.gebruiker_id == ik.id)
        .order_by(Reflectie.gekookt_op.desc(), Reflectie.id.desc())
        .limit(1)
    ).first()
    return JSONResponse(
        {
            "volgende": les_info(volgende),
            "niveau": {
                "naam": huidig.naam,
                "ondertitel": huidig.ondertitel,
                "af": sum(1 for les in lessen_niveau if les.id in vg.afgeronde_lessen),
                "totaal": len(lessen_niveau),
            },
            "niveaus": [n.naam for n in cat.niveaus],
            "af": len(vg.afgeronde_lessen),
            "totaal": len(cat.alle_lessen()),
            "herhalingen": [
                {"techniek": h.techniek.naam, "dagen_over": h.dagen_over_tijd(date.today())}
                for h in te_herhalen(cat, gekookt, date.today(), open_lessen)[:3]
            ],
            "laatst": (
                {
                    "titel": cat.lessen[laatst.les_id].meta.titel,
                    "op": laatst.gekookt_op.isoformat(),
                    "cijfer": laatst.cijfer,
                }
                if laatst and laatst.les_id in cat.lessen
                else None
            ),
            "boodschappen": len(
                sessie.scalars(
                    select(LijstItem.les_id).where(LijstItem.gebruiker_id == ik.id)
                ).all()
            ),
        },
        headers={"Cache-Control": "no-store"},
    )


# --- Cursusoverzicht --------------------------------------------------------------


@router.get("/")
def overzicht(request: Request, cat: Cat, sessie: Db, ik: Ik, melding: str | None = None):
    vg = laad_voortgang(sessie, ik)
    gekookt = gekookte_lessen(sessie, ik)
    open_lessen = {les.id for les in cat.alle_lessen() if les_status(cat, vg, les) == Status.open}
    niveaus = []
    for niveau in cat.niveaus:
        modules = []
        for module in niveau.modules:
            lessen = [
                (les, les_status(cat, vg, les)) for les in cat.lessen_per_module.get(module.id, [])
            ]
            modules.append((module, module_status(cat, vg, module), lessen))
        totaal = sum(len(m[2]) for m in modules)
        klaar = sum(1 for m in modules for _, s in m[2] if s == Status.af)
        niveaus.append((niveau, modules, klaar, totaal))
    return render(
        request,
        "overzicht.html",
        niveaus=niveaus,
        volgende=volgende_les(cat, vg),
        herhalingen=te_herhalen(cat, gekookt, date.today(), open_lessen)[:3],
        aantal_af=len(vg.afgeronde_lessen),
        melding=melding,
        ik=ik,
        Status=Status,
    )


@router.post("/module/{module_id}/beheerst")
def module_beheerst(
    cat: Cat,
    sessie: Db,
    ik: Ik,
    module_id: str,
    uitspraak: Annotated[list[str] | None, Form()] = None,
):
    module = cat.modules.get(module_id)
    if module is None:
        raise HTTPException(404)
    if not module.zelftoets or len(set(uitspraak or [])) < len(module.zelftoets):
        return RedirectResponse(f"/?melding=zelftoets#module-{module_id}", status_code=303)
    if sessie.get(BeheersteModule, (ik.id, module_id)) is None:
        sessie.add(BeheersteModule(gebruiker_id=ik.id, module_id=module_id))
        sessie.commit()
    return RedirectResponse(f"/#module-{module_id}", status_code=303)


@router.post("/module/{module_id}/intrekken")
def module_intrekken(sessie: Db, ik: Ik, module_id: str):
    if (rij := sessie.get(BeheersteModule, (ik.id, module_id))) is not None:
        sessie.delete(rij)
        sessie.commit()
    return RedirectResponse(f"/#module-{module_id}", status_code=303)


# --- Lessen -----------------------------------------------------------------------


def les_context(cat: Catalogus, sessie: Session, ik: Gebruiker, les: Les, porties: int) -> dict:
    vg = laad_voortgang(sessie, ik)
    recept = les.meta.recept
    geschaald = schaal_recept(recept, cat.ingredienten, porties) if recept else []
    groepen: dict[str | None, list] = {}
    for regel in geschaald:
        groepen.setdefault(regel.bron.groep, []).append(regel)
    vinkjes = set(
        sessie.scalars(
            select(Vinkje.punt).where(Vinkje.gebruiker_id == ik.id, Vinkje.les_id == les.id)
        )
    )
    alle = cat.alle_lessen()
    index = alle.index(les)
    return {
        "les": les,
        "module": cat.module_van(les),
        "niveau": cat.niveau_van(les),
        "status": les_status(cat, vg, les),
        "ontbrekend": ontbrekend(cat, vg, les),
        "porties": porties,
        "portie_keuzes": sorted({*PORTIE_KEUZES, porties}),
        "ingredient_groepen": groepen,
        "opdracht": [(punt_id(t), t, punt_id(t) in vinkjes) for t in les.meta.opdracht],
        "technieken": [cat.technieken[t] for t in les.meta.technieken],
        "herhaalt": [
            (cat.technieken[t], cat.lessen[cat.techniek_bron[t]]) for t in les.meta.herhaalt
        ],
        "reflecties": sessie.scalars(
            select(Reflectie)
            .where(Reflectie.gebruiker_id == ik.id, Reflectie.les_id == les.id)
            .order_by(Reflectie.gekookt_op.desc())
        ).all(),
        "op_lijst": sessie.get(LijstItem, (ik.id, les.id)),
        "vorige": alle[index - 1] if index > 0 else None,
        "volgende": alle[index + 1] if index + 1 < len(alle) else None,
        "Status": Status,
        "vandaag": date.today(),
    }


@router.get("/les/{les_id}")
def les_pagina(
    request: Request,
    cat: Cat,
    sessie: Db,
    ik: Ik,
    les_id: str,
    porties: Annotated[int | None, Query()] = None,
    afgerond: bool = False,
):
    les = vind_les(cat, les_id)
    context = les_context(cat, sessie, ik, les, kies_porties(les, porties))
    vg = laad_voortgang(sessie, ik)
    context["afgerond"] = afgerond
    context["daarna"] = volgende_les(cat, vg) if afgerond else None
    return render(request, "les.html", **context)


@router.post("/les/{les_id}/vinkje/{punt}")
def vinkje(request: Request, cat: Cat, sessie: Db, ik: Ik, les_id: str, punt: str):
    les = vind_les(cat, les_id)
    teksten = {punt_id(t): t for t in les.meta.opdracht}
    if punt not in teksten:
        raise HTTPException(404)
    bestaand = sessie.get(Vinkje, (ik.id, les_id, punt))
    if bestaand:
        sessie.delete(bestaand)
    else:
        sessie.add(Vinkje(gebruiker_id=ik.id, les_id=les_id, punt=punt))
    sessie.commit()
    return render(
        request,
        "partials/vinkje.html",
        les=les,
        punt=punt,
        tekst=teksten[punt],
        aan=bestaand is None,
    )


@router.get("/les/{les_id}/koken")
def kookmodus(
    request: Request,
    cat: Cat,
    sessie: Db,
    ik: Ik,
    les_id: str,
    porties: Annotated[int | None, Query()] = None,
):
    les = vind_les(cat, les_id)
    if les.meta.recept is None:
        return RedirectResponse(f"/les/{les_id}", status_code=303)
    return render(
        request, "koken.html", **les_context(cat, sessie, ik, les, kies_porties(les, porties))
    )


# --- Reflectie (proeven) en logboek -----------------------------------------------


def bewaar_foto(foto: UploadFile, map_) -> str | None:
    """Verkleint de foto, draait hem rechtop en verwijdert de EXIF-gegevens
    (daarin staat vaak je GPS-locatie)."""
    inhoud = foto.file.read(MAX_FOTO + 1)
    if not inhoud:
        return None
    if len(inhoud) > MAX_FOTO:
        raise HTTPException(413, "Die foto is te groot (maximaal 15 MB).")
    try:
        beeld = ImageOps.exif_transpose(Image.open(BytesIO(inhoud)))
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(400, "Dat bestand is geen foto die ik kan lezen.") from exc
    beeld = beeld.convert("RGB")
    beeld.thumbnail((1600, 1600))
    naam = f"{uuid.uuid4().hex}.jpg"
    beeld.save(map_ / naam, "JPEG", quality=82, optimize=True)
    return naam


@router.post("/les/{les_id}/reflectie")
def reflectie(
    request: Request,
    cat: Cat,
    sessie: Db,
    ik: Ik,
    les_id: str,
    cijfer: Annotated[int, Form(ge=1, le=10)],
    gekookt_op: Annotated[date, Form()],
    porties: Annotated[int, Form(ge=1, le=12)] = 1,
    wat_lukte: Annotated[str, Form()] = "",
    wat_niet: Annotated[str, Form()] = "",
    volgende_keer: Annotated[str, Form()] = "",
    foto: Annotated[UploadFile | None, File()] = None,
):
    les = vind_les(cat, les_id)
    if les_status(cat, laad_voortgang(sessie, ik), les) == Status.op_slot:
        raise HTTPException(403, "Deze les zit nog op slot.")
    naam = (
        bewaar_foto(foto, request.app.state.settings.foto_dir) if foto and foto.filename else None
    )
    sessie.add(
        Reflectie(
            gebruiker_id=ik.id,
            les_id=les_id,
            cijfer=cijfer,
            gekookt_op=gekookt_op,
            porties=porties,
            wat_lukte=wat_lukte.strip(),
            wat_niet=wat_niet.strip(),
            volgende_keer=volgende_keer.strip(),
            foto=naam,
        )
    )
    sessie.commit()
    return RedirectResponse(f"/les/{les_id}?afgerond=1#proeven", status_code=303)


@router.post("/reflectie/{reflectie_id}/verwijderen")
def reflectie_verwijderen(request: Request, sessie: Db, ik: Ik, reflectie_id: int):
    rij = mijn_reflectie(sessie, ik, reflectie_id)
    if rij.foto:
        (request.app.state.settings.foto_dir / rij.foto).unlink(missing_ok=True)
    sessie.delete(rij)
    sessie.commit()
    return RedirectResponse("/logboek", status_code=303)


@router.get("/logboek")
def logboek(request: Request, cat: Cat, sessie: Db, ik: Ik):
    reflecties = sessie.scalars(
        select(Reflectie)
        .where(Reflectie.gebruiker_id == ik.id)
        .order_by(Reflectie.gekookt_op.desc(), Reflectie.id.desc())
    ).all()
    cijfers = [r.cijfer for r in reflecties]
    return render(
        request,
        "logboek.html",
        reflecties=[(r, cat.lessen.get(r.les_id)) for r in reflecties],
        gemiddeld=round(sum(cijfers) / len(cijfers), 1) if cijfers else None,
    )


@router.get("/foto/{naam}")
def foto(request: Request, sessie: Db, ik: Ik, naam: str):
    if not FOTO_NAAM.match(naam):
        raise HTTPException(404)
    # Alleen je eigen foto's, ook als iemand de (willekeurige) naam van een ander kent.
    van_mij = sessie.scalar(
        select(Reflectie.id).where(Reflectie.gebruiker_id == ik.id, Reflectie.foto == naam)
    )
    if van_mij is None:
        raise HTTPException(404)
    pad = request.app.state.settings.foto_dir / naam
    if not pad.exists():
        raise HTTPException(404)
    return FileResponse(
        pad,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


# --- Boodschappen -----------------------------------------------------------------


@router.get("/boodschappen")
def boodschappen(request: Request, cat: Cat, sessie: Db, ik: Ik):
    items = sessie.scalars(
        select(LijstItem).where(LijstItem.gebruiker_id == ik.id).order_by(LijstItem.toegevoegd)
    ).all()
    keuze = [(cat.lessen[i.les_id], i.porties) for i in items if i.les_id in cat.lessen]
    return render(
        request,
        "boodschappen.html",
        lijst=maak_lijst(cat, keuze),
        eigen=True,
        sleutel=lijst_sleutel(keuze),
    )


@router.get("/les/{les_id}/boodschappen")
def les_boodschappen(
    request: Request, cat: Cat, les_id: str, porties: Annotated[int | None, Query()] = None
):
    les = vind_les(cat, les_id)
    keuze = [(les, kies_porties(les, porties))]
    return render(
        request,
        "boodschappen.html",
        lijst=maak_lijst(cat, keuze),
        eigen=False,
        les=les,
        porties=keuze[0][1],
        sleutel=lijst_sleutel(keuze),
    )


def lijst_sleutel(keuze: list[tuple[Les, int]]) -> str:
    """Verandert als de lijst verandert, zodat afvinken op je telefoon opnieuw begint."""
    tekst = "|".join(f"{les.id}:{p}" for les, p in sorted(keuze, key=lambda x: x[0].id))
    return hashlib.sha1(tekst.encode()).hexdigest()[:10]


@router.post("/boodschappen/toevoegen")
def lijst_toevoegen(
    cat: Cat,
    sessie: Db,
    ik: Ik,
    les_id: Annotated[str, Form()],
    porties: Annotated[int, Form(ge=1, le=12)],
    terug: Annotated[str, Form()] = "/boodschappen",
):
    vind_les(cat, les_id)
    item = sessie.get(LijstItem, (ik.id, les_id))
    if item:
        item.porties = porties
    else:
        sessie.add(LijstItem(gebruiker_id=ik.id, les_id=les_id, porties=porties))
    sessie.commit()
    return RedirectResponse(veilige_volgende(terug), status_code=303)


@router.post("/boodschappen/verwijderen")
def lijst_verwijderen(sessie: Db, ik: Ik, les_id: Annotated[str, Form()]):
    if (item := sessie.get(LijstItem, (ik.id, les_id))) is not None:
        sessie.delete(item)
        sessie.commit()
    return RedirectResponse("/boodschappen", status_code=303)


@router.post("/boodschappen/leegmaken")
def lijst_leegmaken(sessie: Db, ik: Ik):
    for item in sessie.scalars(select(LijstItem).where(LijstItem.gebruiker_id == ik.id)).all():
        sessie.delete(item)
    sessie.commit()
    return RedirectResponse("/boodschappen", status_code=303)


# --- Woordenlijst -----------------------------------------------------------------


@router.get("/woordenlijst")
def woordenlijst(request: Request, cat: Cat):
    termen = sorted(cat.technieken.values(), key=lambda t: (t.frans or t.naam).lower())
    return render(
        request,
        "woordenlijst.html",
        termen=termen,
        bron={t: cat.lessen[les_id] for t, les_id in cat.techniek_bron.items()},
    )


# --- Account ----------------------------------------------------------------------


def account_pagina(request: Request, ik: Gebruiker, status_code: int = 200, **context):
    context = {"ik": ik, "melding": None, "fout": None, "sleutel": None, **context}
    return templates.TemplateResponse(request, "account.html", context, status_code=status_code)


@router.get("/account")
def account(request: Request, ik: Ik, melding: str | None = None):
    return account_pagina(request, ik, melding=melding)


@router.post("/account/gegevens")
def account_gegevens(
    request: Request,
    sessie: Db,
    ik: Ik,
    naam: Annotated[str, Form()],
    email: Annotated[str, Form()],
):
    try:
        gebruikers.wijzig_gegevens(sessie, ik, naam, email)
    except AccountFout as fout:
        sessie.rollback()
        return account_pagina(request, ik, fout=str(fout), status_code=400)
    return RedirectResponse("/account?melding=gegevens", status_code=303)


@router.post("/account/wachtwoord")
def account_wachtwoord(
    request: Request,
    sessie: Db,
    ik: Ik,
    huidig: Annotated[str, Form()],
    wachtwoord: Annotated[str, Form()],
    herhaling: Annotated[str, Form()],
):
    try:
        if not gebruikers.controleer_wachtwoord(huidig, ik.wachtwoord_hash):
            raise AccountFout("Je huidige wachtwoord klopt niet.")
        gebruikers.keur_wachtwoord(wachtwoord, herhaling)
    except AccountFout as fout:
        return account_pagina(request, ik, fout=str(fout), status_code=400)
    gebruikers.zet_wachtwoord(sessie, ik, wachtwoord)
    # Andere toestellen zijn nu uitgelogd; dit toestel blijft ingelogd.
    log_in(request, ik.id, ik.sessie_versie)
    return RedirectResponse("/account?melding=wachtwoord", status_code=303)


@router.post("/account/widget")
def account_widget(request: Request, sessie: Db, ik: Ik):
    sleutel = gebruikers.nieuwe_widgetsleutel(sessie, ik)
    response = account_pagina(request, ik, sleutel=sleutel)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/account/widget/intrekken")
def account_widget_intrekken(sessie: Db, ik: Ik):
    ik.widget_sleutel = None
    sessie.commit()
    return RedirectResponse("/account?melding=widget", status_code=303)


@router.post("/account/verwijderen")
def account_verwijderen(request: Request, sessie: Db, ik: Ik, wachtwoord: Annotated[str, Form()]):
    if not gebruikers.controleer_wachtwoord(wachtwoord, ik.wachtwoord_hash):
        return account_pagina(
            request, ik, fout="Dat wachtwoord klopt niet; je account staat er nog.", status_code=400
        )
    for naam in gebruikers.fotos_van(sessie, ik.id):
        (request.app.state.settings.foto_dir / naam).unlink(missing_ok=True)
    # De rest (reflecties, vinkjes, lijst) verdwijnt mee via ON DELETE CASCADE.
    sessie.delete(ik)
    sessie.commit()
    request.session.clear()
    return RedirectResponse("/login?verwijderd=1", status_code=303)


# --- PWA --------------------------------------------------------------------------


@router.get("/sw.js")
def service_worker():
    # Vanaf de root geserveerd, zodat de service worker de hele app mag beheren.
    return FileResponse(
        STATIC / "js" / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"}
    )


@router.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@router.get("/offline.json")
def offline_lijst(cat: Cat, sessie: Db, ik: Ik):
    """Alle pagina's die de service worker vooraf bewaart, zodat ze offline werken:
    elke les die open of af is, met de kookmodus voor 1, 2 en 3 porties."""
    vg = laad_voortgang(sessie, ik)
    urls = ["/", "/boodschappen", "/logboek", "/woordenlijst", "/account"]
    for les in cat.alle_lessen():
        if les_status(cat, vg, les) == Status.op_slot:
            continue
        urls.append(f"/les/{les.id}")
        if les.meta.recept:
            standaard = les.meta.recept.porties
            for p in sorted({1, 2, 3, standaard}):
                urls.append(f"/les/{les.id}/koken?porties={p}")
            urls.append(f"/les/{les.id}/boodschappen")
    statisch = [static_url(p) for p in STATISCHE_BESTANDEN]
    statisch += [f"/static/fonts/{f.name}" for f in sorted((STATIC / "fonts").glob("*.woff2"))]
    return JSONResponse({"urls": urls, "statisch": statisch})


@router.get("/offline")
def offline(request: Request):
    return render(request, "offline.html")
