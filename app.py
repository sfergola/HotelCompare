"""
app.py — visualizzazione calendario prezzi competitor.

Uso:
    streamlit run app.py

Mostra una tabella interattiva per mese con:
  - righe = hotel competitor
  - colonne = giorni
  - celle colorate per prezzo relativo (verde=più economico, rosso=più caro)
  - suffisso ×N per minimum stay > 1
  - riga Hotel Nuovo Tirreno (riferimento) separata dalla media
"""

import json
from pathlib import Path
from datetime import date

import pandas as pd
import streamlit as st

from scraper import parse_valore, is_extra_letti, lookup_entry

OUTPUT_DIR = Path(__file__).parent / "output"

COLORE_ESAURITO    = "#f8d7da"
COLORE_NON_TROVATO = "#f0f0f0"
COLORE_MEDIA       = "#e8e8ff"
COLORE_RIFERIMENTO = "#fef9e7"


def colore_prezzo_relativo(valore: int, min_val: int, max_val: int) -> str:
    if min_val == max_val:
        return "hsl(120, 55%, 88%)"
    ratio = (valore - min_val) / (max_val - min_val)
    hue = int(120 * (1 - ratio))
    return f"hsl({hue}, 55%, 88%)"


GIORNI_IT = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]

def fmt_giorno(d: str) -> str:
    giorno = date.fromisoformat(d)
    sigla  = GIORNI_IT[giorno.weekday()]
    return f"{sigla} {d[8:10]}-{d[5:7]}"


def mese_label(m: str) -> str:
    mesi = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
            "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    anno, mm = m.split("-")
    return f"{mesi[int(mm)]} {anno}"


lookup = lookup_entry


def media_giorno(calendario: dict, nomi: list, manuali: dict, riferimento: str,
                 giorno: str) -> str:
    valori = []
    for nome in nomi:
        if nome in manuali or nome == riferimento:
            continue
        entry = calendario.get(nome, {}).get(giorno)
        if not entry or not entry.get("prezzo"):
            continue
        p = parse_valore(entry["prezzo"])
        if p and not is_extra_letti(entry["prezzo"]):
            valori.append(p)
    if not valori:
        return "—"
    return f"€ {int(sum(valori) / len(valori))}"


def prezzi_giorno(calendario: dict, nomi: list, manuali: dict, riferimento: str,
                  giorno: str) -> dict[str, int]:
    """Ritorna {nome: valore_intero} per tutti i competitor con prezzo valido."""
    result = {}
    for nome in nomi:
        if nome in manuali or nome == riferimento:
            continue
        cella, _ = lookup(calendario, nome, giorno)
        p = parse_valore(cella)
        if p and not is_extra_letti(cella):
            result[nome] = p
    return result


def render_tabella_mese(calendario: dict, nomi: list, manuali: dict,
                         riferimento: str, giorni_mese: list[str]):
    header_giorni = [fmt_giorno(g) for g in giorni_mese]

    minmax = {}
    for g in giorni_mese:
        prezzi = prezzi_giorno(calendario, nomi, manuali, riferimento, g)
        if prezzi:
            minmax[g] = (min(prezzi.values()), max(prezzi.values()))

    rows_data   = []
    rows_colori = []

    for nome in nomi:
        if nome == riferimento:
            continue

        if nome in manuali:
            rows_data.append([nome] + ["verifica manuale"] + [""] * (len(giorni_mese) - 1))
            rows_colori.append([""] * (len(giorni_mese) + 1))
            continue

        row = [nome]; row_colori = [""]
        for g in giorni_mese:
            cella, _ = lookup(calendario, nome, g)
            p        = parse_valore(cella)
            if cella == "✕":
                colore = COLORE_ESAURITO
            elif cella == "—" or not cella:
                colore = COLORE_NON_TROVATO
            elif p and not is_extra_letti(cella) and g in minmax:
                mn, mx = minmax[g]
                colore = colore_prezzo_relativo(p, mn, mx)
            else:
                colore = COLORE_NON_TROVATO
            row.append(cella)
            row_colori.append(colore)
        rows_data.append(row)
        rows_colori.append(row_colori)

    # riga MEDIA
    row_media = ["MEDIA"]; row_media_colori = [COLORE_MEDIA]
    for g in giorni_mese:
        row_media.append(media_giorno(calendario, nomi, manuali, riferimento, g))
        row_media_colori.append(COLORE_MEDIA)
    rows_data.append(row_media)
    rows_colori.append(row_media_colori)

    # riga Hotel Nuovo Tirreno (riferimento)
    if riferimento:
        row_rif = [f"▶ {riferimento}"]; row_rif_colori = [COLORE_RIFERIMENTO]
        for g in giorni_mese:
            cella, _ = lookup(calendario, riferimento, g)
            p        = parse_valore(cella)
            if cella == "✕":
                colore = COLORE_ESAURITO
            elif cella == "—" or not cella:
                colore = COLORE_NON_TROVATO
            elif p and not is_extra_letti(cella) and g in minmax:
                mn, mx = minmax[g]
                colore = colore_prezzo_relativo(p, mn, mx)
            else:
                colore = COLORE_RIFERIMENTO
            row_rif.append(cella)
            row_rif_colori.append(colore)
        rows_data.append(row_rif)
        rows_colori.append(row_rif_colori)

    df = pd.DataFrame(rows_data, columns=["Hotel"] + header_giorni)

    def style_fn(row):
        idx  = df.index.get_loc(row.name)
        cols = rows_colori[idx]
        return [f"background-color: {c}; font-size: 0.8rem" if c else "" for c in cols]

    sticky_css = [
        {"selector": "th:nth-child(1)", "props": [
            ("position", "sticky"), ("left", "0"), ("z-index", "2"),
            ("background-color", "#f0f2f6"), ("min-width", "150px"),
            ("border-right", "2px solid #dee2e6"),
        ]},
        {"selector": "td:nth-child(1)", "props": [
            ("position", "sticky"), ("left", "0"), ("z-index", "1"),
            ("background-color", "white"), ("min-width", "150px"),
            ("border-right", "2px solid #dee2e6"), ("font-weight", "500"),
        ]},
        {"selector": "th, td", "props": [
            ("padding", "4px 8px"), ("white-space", "nowrap"),
            ("border", "1px solid #dee2e6"),
        ]},
    ]
    styled = df.style.apply(style_fn, axis=1).set_table_styles(sticky_css).hide(axis="index")
    html = styled.to_html()
    st.markdown(f'<div style="overflow-x:auto;width:100%">{html}</div>', unsafe_allow_html=True)


# ── UI principale ────────────────────────────────────────────────────────────

st.set_page_config(page_title="HotelCompare", layout="wide")
st.title("HotelCompare — Prezzi competitor")

# Selezione file
merged_path = OUTPUT_DIR / "calendar_merged.json"
json_files  = sorted(OUTPUT_DIR.glob("calendar_from*_computed*.json"), reverse=True)

OPZIONE_MERGED = "📊 Unificato (tutti i run)"

if not merged_path.exists() and not json_files:
    st.warning("Nessun file di dati trovato in output/. Esegui prima: `python run.py`")
    st.stop()

opzioni   = ([OPZIONE_MERGED] if merged_path.exists() else []) + [f.name for f in json_files]
scelta    = st.sidebar.selectbox("File dati", opzioni)

if scelta == OPZIONE_MERGED:
    dati  = json.loads(merged_path.read_text(encoding="utf-8"))
    meta  = {}
else:
    dati  = json.loads((OUTPUT_DIR / scelta).read_text(encoding="utf-8"))
    meta  = dati.get("meta", {})

calendario = dati.get("calendario", {})

if scelta == OPZIONE_MERGED:
    tutti_i_giorni = sorted(g for h in calendario.values() for g in h)
    periodo = f"{tutti_i_giorni[0]} → {tutti_i_giorni[-1]}" if tutti_i_giorni else "—"

    # Data più recente tra tutti i data_vista
    data_vista_vals = []
    for hotel_cal in calendario.values():
        for entry in hotel_cal.values():
            dv = entry.get("data_vista", "")
            if len(dv) == 8:   # "20260506"
                data_vista_vals.append(date(int(dv[:4]), int(dv[4:6]), int(dv[6:8])))
            elif len(dv) == 10:  # "2026-05-06"
                try:
                    data_vista_vals.append(date.fromisoformat(dv))
                except ValueError:
                    pass
    if data_vista_vals:
        ultima = max(data_vista_vals)
        giorni_fa = (date.today() - ultima).days
        if giorni_fa == 0:
            giorni_fa_str = "oggi"
        elif giorni_fa == 1:
            giorni_fa_str = "ieri"
        else:
            giorni_fa_str = f"{giorni_fa} giorni fa"
        data_agg = f"{ultima.day:02d}/{ultima.month:02d}/{ultima.year} ({giorni_fa_str})"
    else:
        data_agg = "—"

    st.sidebar.markdown(f"""
**Periodo:** {periodo}
**Hotel:** {len(calendario)}
**Aggiornato il:** {data_agg}
""")
else:
    computed = scelta.split("_computed")[-1].replace(".json", "")
    if len(computed) == 8:
        data_agg_date = date(int(computed[:4]), int(computed[4:6]), int(computed[6:8]))
        giorni_fa     = (date.today() - data_agg_date).days
        if giorni_fa == 0:
            giorni_fa_str = "oggi"
        elif giorni_fa == 1:
            giorni_fa_str = "ieri"
        else:
            giorni_fa_str = f"{giorni_fa} giorni fa"
        data_agg = f"{computed[6:8]}/{computed[4:6]}/{computed[:4]} ({giorni_fa_str})"
    else:
        data_agg = "—"
    st.sidebar.markdown(f"""
**Periodo:** {meta.get('data_inizio')} → {meta.get('data_fine')}
**Adulti:** {meta.get('adulti', 2)}
**Hotel:** {len(calendario)}
**Aggiornato il:** {data_agg}
""")

# Legenda colori
st.sidebar.markdown("### Colori prezzi")
st.sidebar.markdown(
    "<span style='background:hsl(120,55%,88%);padding:2px 8px;border-radius:3px'>più economico</span>"
    " → "
    "<span style='background:hsl(0,55%,88%);padding:2px 8px;border-radius:3px'>più caro</span>",
    unsafe_allow_html=True
)
st.sidebar.markdown(
    f"<span style='background:{COLORE_ESAURITO};padding:2px 8px;border-radius:3px'>✕ esaurito</span>",
    unsafe_allow_html=True
)
st.sidebar.markdown(
    f"<span style='background:{COLORE_NON_TROVATO};padding:2px 8px;border-radius:3px'>— non trovato</span>",
    unsafe_allow_html=True
)
st.sidebar.markdown(
    f"<span style='background:{COLORE_RIFERIMENTO};padding:2px 8px;border-radius:3px'>▶ Hotel Nuovo Tirreno</span>",
    unsafe_allow_html=True
)

# Tutti i giorni
tutti_giorni = sorted(set(
    g for hotel_cal in calendario.values() for g in hotel_cal
))

if not tutti_giorni:
    st.warning("Nessun dato nel file selezionato.")
    st.stop()

# Nomi hotel e riferimento
cfg_raw    = json.loads((Path(__file__).parent / "competitors.json").read_text())
manuali    = {c["nome"]: c["nota"] for c in cfg_raw["competitor"] if "nota" in c}
riferimento = next((c["nome"] for c in cfg_raw["competitor"] if c.get("riferimento")), "")
nomi       = list(calendario.keys())

# Navigazione mese
mesi_disponibili = sorted(set(g[:7] for g in tutti_giorni))

if "mese_idx" not in st.session_state:
    st.session_state.mese_idx = 0

idx = st.session_state.mese_idx
idx = max(0, min(idx, len(mesi_disponibili) - 1))

col_prev, col_titolo, col_next = st.columns([1, 6, 1])
with col_prev:
    if st.button("←", disabled=(idx == 0)):
        st.session_state.mese_idx = idx - 1
        st.rerun()
with col_titolo:
    st.subheader(mese_label(mesi_disponibili[idx]))
with col_next:
    if st.button("→", disabled=(idx == len(mesi_disponibili) - 1)):
        st.session_state.mese_idx = idx + 1
        st.rerun()

giorni_mese = [g for g in tutti_giorni if g.startswith(mesi_disponibili[idx])]
render_tabella_mese(calendario, nomi, manuali, riferimento, giorni_mese)

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
| `€ 120A` | appartamento (fallback — escluso dalle medie) |
| `✕` | esaurito (indicativo) |
| `—` | non disponibile / non trovato |
""")
