"""
app.py — visualizzazione calendario prezzi competitor.

Uso:
    streamlit run app.py

Mostra una tabella interattiva per mese con:
  - righe = hotel competitor
  - colonne = giorni
  - celle colorate per durata soggiorno minimo (notti)
  - suffisso ×N per minimum stay > 1
"""

import json
from pathlib import Path
from datetime import datetime
from itertools import groupby

import pandas as pd
import streamlit as st

from scraper import parse_valore, is_extra_letti

OUTPUT_DIR = Path(__file__).parent / "output"

# ── colori per minimum stay ──────────────────────────────────────────────────
# 1n = verde (flessibile), 7n = arancio (solo settimanale)
COLORI_NOTTI = {
    1: "#d4edda",
    2: "#d4edda",
    3: "#fff3cd",
    4: "#fff3cd",
    5: "#fde8c8",
    6: "#fde8c8",
    7: "#fcd5a0",
}

COLORE_ESAURITO    = "#f8d7da"
COLORE_NON_TROVATO = "#f0f0f0"
COLORE_MEDIA       = "#e8e8ff"


def colore_cella(cella: str, notti: int) -> str:
    if cella == "✕":
        return COLORE_ESAURITO
    if cella == "—" or not cella:
        return COLORE_NON_TROVATO
    return COLORI_NOTTI.get(notti, COLORE_NON_TROVATO)


def fmt_giorno(d: str) -> str:
    return d[8:10] + "-" + d[5:7]


def mese_label(m: str) -> str:
    mesi = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
            "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    anno, mm = m.split("-")
    return f"{mesi[int(mm)]} {anno}"


def lookup(calendario: dict, nome: str, giorno: str) -> tuple[str, int]:
    entry = calendario.get(nome, {}).get(giorno)
    if not entry:
        return "—", 0
    prezzo = entry.get("prezzo")
    notti  = entry.get("notti") or 1
    stato  = entry.get("stato", "non_trovato")
    if prezzo:
        sfx = f"×{notti}" if notti > 1 else ""
        return f"{prezzo}{sfx}", notti
    if stato == "esaurito":
        return "✕", 0
    return "—", 0


def media_giorno(calendario: dict, nomi: list, manuali: dict, giorno: str) -> str:
    valori = []
    for nome in nomi:
        if nome in manuali:
            continue
        cella, _ = lookup(calendario, nome, giorno)
        p = parse_valore(cella)
        if p and not is_extra_letti(cella):
            valori.append(p)
    if not valori:
        return "—"
    return f"€ {int(sum(valori) / len(valori))}"


def carica_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_tabella_mese(calendario: dict, nomi: list, manuali: dict,
                         giorni_mese: list[str]):
    header_giorni = [fmt_giorno(g) for g in giorni_mese]
    tutti_nomi    = nomi

    rows_data   = []
    rows_colori = []

    for nome in tutti_nomi:
        if nome in manuali:
            row        = [nome] + ["verifica manuale"] + [""] * (len(giorni_mese) - 1)
            row_colori = [""] * (len(giorni_mese) + 1)
            rows_data.append(row)
            rows_colori.append(row_colori)
            continue

        row        = [nome]
        row_colori = [""]
        for g in giorni_mese:
            cella, notti = lookup(calendario, nome, g)
            row.append(cella)
            row_colori.append(colore_cella(cella, notti))
        rows_data.append(row)
        rows_colori.append(row_colori)

    # riga MEDIA
    row_media        = ["MEDIA"]
    row_media_colori = [COLORE_MEDIA]
    for g in giorni_mese:
        m = media_giorno(calendario, tutti_nomi, manuali, g)
        row_media.append(m)
        row_media_colori.append(COLORE_MEDIA)
    rows_data.append(row_media)
    rows_colori.append(row_media_colori)

    df = pd.DataFrame(rows_data, columns=["Hotel"] + header_giorni)

    def style_fn(row):
        idx  = df.index.get_loc(row.name)
        cols = rows_colori[idx]
        return [f"background-color: {c}; font-size: 0.8rem" if c else "" for c in cols]

    styled = df.style.apply(style_fn, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ── UI principale ────────────────────────────────────────────────────────────

st.set_page_config(page_title="HotelCompare", layout="wide")
st.title("HotelCompare — Prezzi competitor")

# Selezione file
json_files = sorted(OUTPUT_DIR.glob("calendar_from*_computed*.json"), reverse=True)
if not json_files:
    st.warning("Nessun file di dati trovato in output/. Esegui prima: `python run.py`")
    st.stop()

nomi_file = [f.name for f in json_files]
scelta    = st.sidebar.selectbox("File dati", nomi_file)
dati      = carica_file(OUTPUT_DIR / scelta)

meta       = dati.get("meta", {})
calendario = dati.get("calendario", {})

st.sidebar.markdown(f"""
**Periodo:** {meta.get('data_inizio')} → {meta.get('data_fine')}
**Adulti:** {meta.get('adulti', 2)}
**Hotel:** {len(calendario)}
""")

# Legenda colori
st.sidebar.markdown("### Minimum stay")
for notti, colore in COLORI_NOTTI.items():
    st.sidebar.markdown(
        f"<span style='background:{colore};padding:2px 8px;border-radius:3px'>"
        f"{'1-2' if notti == 1 else '3-4' if notti == 3 else '5-6' if notti == 5 else '7'} notti"
        f"</span>",
        unsafe_allow_html=True
    )
    if notti in (2, 4, 6, 7):
        continue
st.sidebar.markdown(
    f"<span style='background:{COLORE_ESAURITO};padding:2px 8px;border-radius:3px'>✕ esaurito</span>",
    unsafe_allow_html=True
)
st.sidebar.markdown(
    f"<span style='background:{COLORE_NON_TROVATO};padding:2px 8px;border-radius:3px'>— non trovato</span>",
    unsafe_allow_html=True
)

# Tutti i giorni
tutti_giorni = sorted(set(
    g for hotel_cal in calendario.values() for g in hotel_cal
))

if not tutti_giorni:
    st.warning("Nessun dato nel file selezionato.")
    st.stop()

# Nomi hotel
nomi    = list(calendario.keys())
cfg_raw = json.loads((Path(__file__).parent / "competitors.json").read_text())
manuali = {c["nome"]: c["nota"] for c in cfg_raw["competitor"] if "nota" in c}

# Filtro mese
mesi_disponibili = sorted(set(g[:7] for g in tutti_giorni))
mese_scelto      = st.sidebar.selectbox(
    "Mese",
    mesi_disponibili,
    format_func=mese_label
)

giorni_mese = [g for g in tutti_giorni if g.startswith(mese_scelto)]

st.subheader(mese_label(mese_scelto))
render_tabella_mese(calendario, nomi, manuali, giorni_mese)

# Legenda prezzi
with st.expander("Legenda prezzi"):
    st.markdown("""
| Simbolo | Significato |
|---|---|
| `€ 120` | solo camera, matrimoniale standard |
| `€ 120*` | B&B, matrimoniale standard |
| `€ 120×7` | prezzo da soggiorno minimo 7 notti |
| `€ 120#` | solo camera, economy double |
| `€ 120S` | singola (nessuna doppia trovata) |
| `~€ 120` | matrimoniale trovata, tipo pensione non identificabile |
| `€ 120T` | tripla (fallback — esclusa dalle medie) |
| `€ 120Q` | quadrupla (fallback estremo — esclusa dalle medie) |
| `✕` | esaurito (indicativo) |
| `—` | non disponibile / non trovato |
""")
