"""
Unit test per le funzioni pure di app.py che non dipendono da Streamlit.
"""

import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import colore_prezzo_relativo, media_giorno, prezzi_giorno, _fmt_data_agg, fmt_giorno


# ── colore_prezzo_relativo ────────────────────────────────────────────────────

def test_colore_minimo():
    # il minimo deve dare verde (hue 120)
    c = colore_prezzo_relativo(100, 100, 200)
    assert c == "hsl(120, 55%, 88%)"

def test_colore_massimo():
    # il massimo deve dare rosso (hue 0)
    c = colore_prezzo_relativo(200, 100, 200)
    assert c == "hsl(0, 55%, 88%)"

def test_colore_unico_valore():
    # min==max → tutti verdi (nessuna varianza)
    c = colore_prezzo_relativo(150, 150, 150)
    assert c == "hsl(120, 55%, 88%)"

def test_colore_meta():
    c = colore_prezzo_relativo(150, 100, 200)
    assert c == "hsl(60, 55%, 88%)"


# ── media_giorno ──────────────────────────────────────────────────────────────

def test_media_giorno_base():
    calendario = {
        "Hotel A": {"2026-07-01": {"prezzo": "€ 100", "notti": 1, "stato": "ok"}},
        "Hotel B": {"2026-07-01": {"prezzo": "€ 200", "notti": 1, "stato": "ok"}},
    }
    m = media_giorno(calendario, ["Hotel A", "Hotel B"], {}, "", "2026-07-01")
    assert m == "€ 150"

def test_media_giorno_esclude_riferimento():
    calendario = {
        "Hotel A": {"2026-07-01": {"prezzo": "€ 100", "notti": 1, "stato": "ok"}},
        "Hotel Ref": {"2026-07-01": {"prezzo": "€ 50", "notti": 1, "stato": "ok"}},
    }
    m = media_giorno(calendario, ["Hotel A", "Hotel Ref"], {}, "Hotel Ref", "2026-07-01")
    assert m == "€ 100"

def test_media_giorno_esclude_extra_letti():
    calendario = {
        "Hotel A": {"2026-07-01": {"prezzo": "€ 100", "notti": 1, "stato": "ok"}},
        "Hotel B": {"2026-07-01": {"prezzo": "€ 200T", "notti": 1, "stato": "ok"}},
    }
    m = media_giorno(calendario, ["Hotel A", "Hotel B"], {}, "", "2026-07-01")
    assert m == "€ 100"

def test_media_giorno_nessun_dato():
    m = media_giorno({}, [], {}, "", "2026-07-01")
    assert m == "—"


# ── prezzi_giorno ─────────────────────────────────────────────────────────────

def test_prezzi_giorno_esclude_storico():
    # cella senza prezzo corrente ma con storico: "— (€ 120* · 30/04)"
    # il € storico non deve entrare nella scala colori
    calendario = {
        "Hotel A": {"2026-07-01": {"prezzo": "€ 100", "notti": 1, "stato": "ok"}},
        "Hotel B": {"2026-07-01": {
            "prezzo": None, "notti": None, "stato": "non_trovato",
            "storico_prezzo": "€ 120*", "storico_notti": 1, "storico_data": "2026-04-30",
        }},
    }
    p = prezzi_giorno(calendario, ["Hotel A", "Hotel B"], {}, "", "2026-07-01")
    assert p == {"Hotel A": 100.0}

def test_prezzi_giorno_esclude_esaurito_con_storico():
    calendario = {
        "Hotel A": {"2026-07-01": {"prezzo": "€ 100", "notti": 1, "stato": "ok"}},
        "Hotel B": {"2026-07-01": {
            "prezzo": None, "notti": None, "stato": "esaurito",
            "storico_prezzo": "€ 90", "storico_notti": 1, "storico_data": "2026-04-30",
        }},
    }
    p = prezzi_giorno(calendario, ["Hotel A", "Hotel B"], {}, "", "2026-07-01")
    assert p == {"Hotel A": 100.0}

def test_prezzi_giorno_esclude_tripla_con_minimum_stay():
    calendario = {
        "Hotel A": {"2026-07-01": {"prezzo": "€ 100", "notti": 1, "stato": "ok"}},
        "Hotel B": {"2026-07-01": {"prezzo": "€ 80T", "notti": 3, "stato": "ok"}},
    }
    p = prezzi_giorno(calendario, ["Hotel A", "Hotel B"], {}, "", "2026-07-01")
    assert p == {"Hotel A": 100.0}


# ── _fmt_data_agg ─────────────────────────────────────────────────────────────

def test_fmt_data_agg_oggi():
    s = _fmt_data_agg(date.today())
    assert "oggi" in s

def test_fmt_data_agg_ieri():
    from datetime import timedelta
    s = _fmt_data_agg(date.today() - timedelta(days=1))
    assert "ieri" in s

def test_fmt_data_agg_giorni_fa():
    from datetime import timedelta
    s = _fmt_data_agg(date.today() - timedelta(days=5))
    assert "5 giorni fa" in s


# ── fmt_giorno ────────────────────────────────────────────────────────────────

def test_fmt_giorno_formato():
    s = fmt_giorno("2026-07-06")  # lunedì
    assert s == "Lun 06"

def test_fmt_giorno_domenica():
    s = fmt_giorno("2026-07-05")  # domenica
    assert s == "Dom 05"
