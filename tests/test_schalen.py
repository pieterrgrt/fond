import pytest

from fond.content.models import Eenheid, Schaal
from fond.schalen import factor_voor, getal, rond_af, schaal_recept, toon


@pytest.mark.parametrize(
    "schaal,factor,verwacht",
    [
        (Schaal.lineair, 3, 3),
        (Schaal.beperkt, 3, 2),
        (Schaal.beperkt, 2, 1.5),
        (Schaal.beperkt, 0.5, 0.75),
        (Schaal.vast, 6, 1),
    ],
)
def test_factor_voor(schaal, factor, verwacht):
    assert factor_voor(schaal, factor) == verwacht


@pytest.mark.parametrize(
    "hoeveelheid,eenheid,heel,verwacht",
    [
        (12.4, Eenheid.g, False, 12),  # klein: op de gram
        (167, Eenheid.g, False, 170),  # middel: op 10 g
        (1520, Eenheid.g, False, 1500),  # groot: op 50 g
        (1.2, Eenheid.kg, False, 1200),  # kg wordt g
        (0.4, Eenheid.tl, False, 0.5),  # lepels: kwarten onder de 1
        (1.3, Eenheid.el, False, 1.5),  # daarboven halven
        (1.5, Eenheid.stuk, True, 2),  # hele uien: naar boven
        (2.0000001, Eenheid.stuk, True, 2),
        (0.5, Eenheid.stuk, False, 0.5),  # halve citroen mag
        (0.1, Eenheid.blik, False, 0.5),  # nooit nul
    ],
)
def test_rond_af(hoeveelheid, eenheid, heel, verwacht):
    assert rond_af(hoeveelheid, eenheid, heel) == verwacht


@pytest.mark.parametrize(
    "waarde,tekst", [(1.5, "1½"), (0.25, "¼"), (2.0, "2"), (1.2, "1,2"), (3.75, "3¾")]
)
def test_getal(waarde, tekst):
    assert getal(waarde) == tekst


@pytest.mark.parametrize(
    "h,e,tekst",
    [
        (1500, Eenheid.g, "1½ kg"),
        (250, Eenheid.g, "250 g"),
        (2, Eenheid.teen, "2 tenen"),
        (1, Eenheid.teen, "1 teen"),
        (3, Eenheid.stuk, "3"),
        (None, None, "naar smaak"),
        (1.25, Eenheid.l, "1¼ l"),
        (1.2, Eenheid.kg, "1,2 kg"),
    ],
)
def test_toon(h, e, tekst):
    assert toon(h, e) == tekst


def test_schaal_recept_van_2_naar_6(cat):
    recept = cat.lessen["a"].meta.recept
    regels = {r.ingredient.id: r for r in schaal_recept(recept, cat.ingredienten, 6)}
    assert regels["rijst"].tekst == "600 g"
    assert regels["ui"].hoeveelheid == 3
    assert regels["olie"].hoeveelheid == 2  # beperkt: ×3 wordt ×2
    assert regels["zout"].tekst == "naar smaak"


def test_schaal_recept_halveren_heel(cat):
    recept = cat.lessen["a"].meta.recept
    regels = {r.ingredient.id: r for r in schaal_recept(recept, cat.ingredienten, 1)}
    assert regels["ui"].hoeveelheid == 1  # een halve ui wordt een hele
    assert regels["rijst"].tekst == "100 g"
