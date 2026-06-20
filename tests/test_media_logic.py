"""
Test della logica che decide quali prezzi entrano nella MEDIA:
stima colazione (≈), staleness, copertura hotel, normalizzazione per-notte.
Funzioni pure: nessuna rete, nessun browser.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper import (normalizza_prezzo, valore_per_media, hotel_in_media,
                     prezzo_stantio, parse_data_vista, lookup_entry,
                     media_competitor, COLAZIONE_STIMA_PERSONA)

OGGI = date(2026, 6, 16)


# ── normalizza_prezzo: per-notte + stima colazione ───────────────────────────

def test_normalizza_solo_camera_aggiunge_colazione():
    # ≈ = solo camera → +€8/persona × 2 adulti = +16/notte
    assert normalizza_prezzo("€ 110≈", 1, 2) == "€ 126≈"

def test_normalizza_bb_invariato():
    assert normalizza_prezzo("€ 140*", 1, 2) == "€ 140*"

def test_normalizza_divide_per_notti():
    # 696 totale / 3 notti = 232; +16 colazione = 248
    assert normalizza_prezzo("€ 696≈", 3, 2) == "€ 248≈"
    assert normalizza_prezzo("€ 600*", 3, 2) == "€ 200*"

def test_normalizza_preserva_minimum_stay():
    assert normalizza_prezzo("€ 600≈", 3, 2) == "€ 216≈"

def test_normalizza_tilde_preservata():
    assert normalizza_prezzo("~€ 300", 3, 2) == "~€ 100"

def test_normalizza_sotto_soglia_none():
    # 60/3 = 20 €/notte < 25 → implausibile per una doppia, scartato
    assert normalizza_prezzo("€ 60*", 3, 2) is None

def test_normalizza_colazione_costante():
    # blinda il numero: cambiarlo è una scelta esplicita
    assert COLAZIONE_STIMA_PERSONA == 8


# ── staleness ─────────────────────────────────────────────────────────────────

def test_parse_data_vista_due_formati():
    assert parse_data_vista("20260601") == date(2026, 6, 1)
    assert parse_data_vista("2026-06-01") == date(2026, 6, 1)
    assert parse_data_vista("") is None
    assert parse_data_vista("xyz") is None

def test_prezzo_stantio():
    assert prezzo_stantio({"prezzo": "€ 120", "data_vista": "2026-06-10"}, OGGI) is False
    assert prezzo_stantio({"prezzo": "€ 120", "data_vista": "2026-04-01"}, OGGI) is True

def test_prezzo_stantio_senza_oggi_non_valuta():
    assert prezzo_stantio({"prezzo": "€ 120", "data_vista": "2026-04-01"}, None) is False


# ── valore_per_media ────────────────────────────────────────────────────────

def test_valore_per_media_doppia_fresca():
    assert valore_per_media({"prezzo": "€ 120*", "data_vista": "2026-06-10"}, OGGI) == 120

def test_valore_per_media_esclude_stantio():
    assert valore_per_media({"prezzo": "€ 120*", "data_vista": "2026-04-01"}, OGGI) is None

def test_valore_per_media_esclude_singola_e_tripla():
    assert valore_per_media({"prezzo": "€ 90S", "data_vista": "2026-06-10"}, OGGI) is None
    assert valore_per_media({"prezzo": "€ 150T", "data_vista": "2026-06-10"}, OGGI) is None

def test_valore_per_media_senza_prezzo():
    assert valore_per_media({"prezzo": None}, OGGI) is None


# ── hotel_in_media: esclusione hotel quasi-cieco ──────────────────────────────

def _giorni(n):
    return [f"2026-08-{d:02d}" for d in range(1, n + 1)]

def test_hotel_con_dati_ammesso():
    g = _giorni(10)
    cal = {"H": {d: {"prezzo": "€ 120*", "data_vista": "2026-06-10"} for d in g}}
    assert hotel_in_media(cal, "H", g, OGGI) is True

def test_hotel_quasi_cieco_escluso():
    # 1 cella pulita su 10 (10%) < COPERTURA_MIN (30%) → fuori
    g = _giorni(10)
    cal = {"H": {g[0]: {"prezzo": "~€ 120", "data_vista": "2026-06-10"},
                 g[1]: {"prezzo": "€ 150T", "data_vista": "2026-06-10"}}}
    assert hotel_in_media(cal, "H", g, OGGI) is False

def test_hotel_senza_giorni():
    assert hotel_in_media({}, "H", [], OGGI) is False


# ── media_competitor: logica unica condivisa app.py / report.py ───────────────

def _entry(prezzo):
    return {"prezzo": prezzo, "data_vista": "2026-06-10"}

def test_media_competitor_media_semplice():
    cal = {"A": {"2026-08-01": _entry("€ 100*")},
           "B": {"2026-08-01": _entry("€ 140*")}}
    assert media_competitor(cal, ["A", "B"], {}, "2026-08-01", oggi=OGGI) == 120

def test_media_competitor_esclude_riferimento_e_manuali():
    cal = {"A": {"2026-08-01": _entry("€ 100*")},
           "REF": {"2026-08-01": _entry("€ 500*")},
           "MAN": {"2026-08-01": _entry("€ 900*")}}
    m = media_competitor(cal, ["A", "REF", "MAN"], {"MAN": "nota"},
                         "2026-08-01", riferimento="REF", oggi=OGGI)
    assert m == 100

def test_media_competitor_rispetta_nomi_in_media():
    cal = {"A": {"2026-08-01": _entry("€ 100*")},
           "B": {"2026-08-01": _entry("€ 200*")}}
    m = media_competitor(cal, ["A", "B"], {}, "2026-08-01",
                         oggi=OGGI, nomi_in_media={"A"})
    assert m == 100

def test_media_competitor_vuoto_none():
    assert media_competitor({}, ["A"], {}, "2026-08-01", oggi=OGGI) is None

def test_media_competitor_scarta_outlier():
    # 4 valori: il 5° a 10× la mediana esce (filtra_prezzi_anomali, ≥4 valori)
    cal = {n: {"2026-08-01": _entry(f"€ {p}*")}
           for n, p in [("A", 100), ("B", 110), ("C", 120), ("D", 130), ("E", 1500)]}
    m = media_competitor(cal, list(cal), {}, "2026-08-01", oggi=OGGI)
    assert m == 115  # (100+110+120+130)/4, l'outlier 1500 è escluso


# ── lookup_entry: declassamento staleness ─────────────────────────────────────

def test_lookup_declassa_stantio_a_storico():
    cal = {"H": {"2026-08-01": {"prezzo": "€ 120*", "notti": 1, "stato": "ok",
                                "data_vista": "2026-04-01"}}}
    cella, notti = lookup_entry(cal, "H", "2026-08-01", OGGI)
    assert cella == "— (€ 120* · 01/04)"
    assert notti == 0

def test_lookup_fresco_resta_prezzo():
    cal = {"H": {"2026-08-01": {"prezzo": "€ 120*", "notti": 1, "stato": "ok",
                                "data_vista": "2026-06-10"}}}
    cella, notti = lookup_entry(cal, "H", "2026-08-01", OGGI)
    assert cella == "€ 120*"
    assert notti == 1

def test_lookup_senza_oggi_ignora_staleness():
    # retro-compatibile: senza oggi non declassa
    cal = {"H": {"2026-08-01": {"prezzo": "€ 120*", "notti": 1, "stato": "ok",
                                "data_vista": "2026-04-01"}}}
    cella, _ = lookup_entry(cal, "H", "2026-08-01")
    assert cella == "€ 120*"
