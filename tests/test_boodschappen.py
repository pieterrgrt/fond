from fond.boodschappen import CHECK_THUIS, maak_lijst


def test_lijst_samenvoegen_en_sorteren(cat):
    lijst = maak_lijst(cat, [(cat.lessen["a"], 2), (cat.lessen["b"], 6)])
    afdelingen = [g.afdeling.id for g in lijst.groepen]
    # Looproute uit winkel.yaml, basisvoorraad als laatste.
    assert afdelingen == ["groente", "droog", CHECK_THUIS.id]

    regels = {r.ingredient.id: r for g in lijst.groepen for r in g.regels}
    assert regels["rijst"].tekst == "800 g"  # 200 + 600
    assert regels["rijst"].verpakkingen == 1
    assert regels["rijst"].verpakking_tekst == "1× 1 kg"
    assert regels["ui"].hoeveelheid == 4  # 1 + 3
    assert regels["ui"].lessen == ["Les a", "Les b"]
    assert regels["olie"].hoeveelheid == 3  # 1 + 2 (beperkt)
    assert regels["zout"].tekst == "naar smaak"


def test_verpakkingen_en_prijs(cat):
    lijst = maak_lijst(cat, [(cat.lessen["a"], 12)])
    regels = {r.ingredient.id: r for g in lijst.groepen for r in g.regels}
    assert regels["rijst"].verpakkingen == 2  # 1200 g
    assert regels["ui"].verpakkingen == 1  # 6 uien, net van 8
    # Basisvoorraad telt niet mee in de schatting.
    assert lijst.schatting == 2 * 2.00 + 1.20


def test_lege_lijst(cat):
    assert maak_lijst(cat, []).leeg
