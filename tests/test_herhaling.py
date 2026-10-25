from datetime import date, timedelta

from fond.herhaling import INTERVALLEN, te_herhalen, volgende_datum

D = date(2026, 3, 1)


def test_interval_groeit_met_oefening():
    assert volgende_datum(1, D) == D + timedelta(days=INTERVALLEN[0])
    assert volgende_datum(2, D) == D + timedelta(days=INTERVALLEN[1])
    # Na veel oefenen blijft het bij het langste interval.
    assert volgende_datum(99, D) == D + timedelta(days=INTERVALLEN[-1])


def test_nog_niet_toe(cat):
    assert te_herhalen(cat, [("a", D)], D + timedelta(days=1)) == []


def test_toe_aan_herhaling(cat):
    herhalingen = te_herhalen(cat, [("a", D)], D + timedelta(days=INTERVALLEN[0]))
    assert [h.techniek.id for h in herhalingen] == ["snijden"]
    # Les b herhaalt 'snijden' en is nog niet gedaan: die staat vooraan.
    assert [les.id for les in herhalingen[0].lessen] == ["b", "a"]


def test_zelfde_dag_telt_als_een_keer(cat):
    vandaag = D + timedelta(days=INTERVALLEN[0])
    herhalingen = te_herhalen(cat, [("a", D), ("a", D)], vandaag)
    assert herhalingen[0].keer_geoefend == 1


def test_alleen_open_lessen_voorstellen(cat):
    vandaag = D + timedelta(days=30)
    herhalingen = te_herhalen(cat, [("a", D), ("b", D)], vandaag, open_lessen={"c"})
    koken = next(h for h in herhalingen if h.techniek.id == "koken")
    # c is open en nieuw (vooraan), b is al gedaan; a heeft 'koken' niet.
    assert [les.id for les in koken.lessen] == ["c", "b"]
