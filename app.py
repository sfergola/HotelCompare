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
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from scraper import (parse_valore, is_extra_letti, lookup_entry,
                     hotel_in_media, valori_media, DISPONIBILITA_MIN_MEDIA)

CSS_GLOBALE = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
.block-container {padding-top: 1.2rem; padding-bottom: 1rem;}
h1 {font-size: 1.5rem !important; font-weight: 700 !important; margin-bottom: 0.2rem !important;}
h2 {font-size: 1.15rem !important; font-weight: 600 !important; margin: 0.4rem 0 0.6rem 0 !important;}
[data-testid="stSidebar"] {min-width: 220px; max-width: 260px;}
[data-testid="stSidebar"] .stSelectbox label {font-size: 0.85rem;}
.stButton > button {
    border-radius: 6px;
    font-size: 1.1rem;
    padding: 2px 14px;
    line-height: 1.8;
    border: 1px solid #ccd0d6;
    background: #f8f9fa;
    color: #333;
}
.stButton > button:hover {background: #e9ecef;}
.stButton > button:disabled {opacity: 0.35;}
</style>
"""

OUTPUT_DIR = Path(__file__).parent / "output"

COLORE_ESAURITO    = "#f8d7da"
COLORE_NON_TROVATO = "#f0f0f0"
COLORE_MEDIA       = "#e8e8ff"
COLORE_MEDIA_DEBOLE = "#ededf2"  # media su campione esiguo (poche doppie): sbiadita
COLORE_RIFERIMENTO = "#fef9e7"


def colore_prezzo_relativo(valore: int, min_val: int, max_val: int) -> str:
    if min_val == max_val:
        return "hsl(120, 55%, 88%)"
    ratio = (valore - min_val) / (max_val - min_val)
    hue = int(120 * (1 - ratio))
    return f"hsl({hue}, 55%, 88%)"


GIORNI_IT = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]


def _pasqua(anno: int) -> date:
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    giorno = (h + l - 7 * m + 114) % 31 + 1
    return date(anno, mese, giorno)


def festivi_italiani(anno: int) -> set[str]:
    pasqua = _pasqua(anno)
    return {d.isoformat() for d in [
        date(anno, 1, 1),   # Capodanno
        date(anno, 1, 6),   # Epifania
        date(anno, 4, 25),  # Liberazione
        date(anno, 5, 1),   # Festa del Lavoro
        date(anno, 6, 2),   # Repubblica
        date(anno, 8, 15),  # Ferragosto
        date(anno, 11, 1),  # Ognissanti
        date(anno, 12, 8),  # Immacolata
        date(anno, 12, 25), # Natale
        date(anno, 12, 26), # Santo Stefano
        pasqua,
        pasqua + timedelta(days=1),  # Pasquetta
    ]}

def fmt_giorno(d: str) -> str:
    giorno = date.fromisoformat(d)
    sigla  = GIORNI_IT[giorno.weekday()]
    return f"{sigla} {d[8:10]}"


def mese_label(m: str) -> str:
    mesi = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
            "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    anno, mm = m.split("-")
    return f"{mesi[int(mm)]} {anno}"


lookup = lookup_entry


def _fmt_data_agg(d: date) -> str:
    giorni_fa = (date.today() - d).days
    if giorni_fa == 0:
        label = "oggi"
    elif giorni_fa == 1:
        label = "ieri"
    else:
        label = f"{giorni_fa} giorni fa"
    return f"{d.day:02d}/{d.month:02d}/{d.year} ({label})"


def media_giorno(calendario: dict, nomi: list, manuali: dict, riferimento: str,
                 giorno: str, oggi=None, nomi_in_media: set | None = None) -> tuple[str, bool]:
    """(testo, debole): debole=True se meno di metà dei mediabili ha una doppia quel
    giorno → la media è il residuo caro, poco affidabile (vedi DISPONIBILITA_MIN_MEDIA)."""
    valori = valori_media(calendario, nomi, manuali, giorno, riferimento, oggi, nomi_in_media)
    if not valori:
        return "—", False
    media = sum(valori) / len(valori)
    base = len(nomi_in_media) if nomi_in_media is not None else \
        sum(1 for n in nomi if n not in manuali and n != riferimento)
    debole = base > 0 and len(valori) / base < DISPONIBILITA_MIN_MEDIA
    return f"€ {int(media)}" + ("°" if debole else ""), debole


def prezzi_giorno(calendario: dict, nomi: list, manuali: dict, riferimento: str,
                  giorno: str, oggi=None) -> dict[str, int]:
    """Ritorna {nome: valore_intero} per tutti i competitor con prezzo valido
    (esclude storici, esauriti, non-doppie e prezzi stantii)."""
    result = {}
    for nome in nomi:
        if nome in manuali or nome == riferimento:
            continue
        cella, _ = lookup(calendario, nome, giorno, oggi)
        # le celle senza prezzo corrente ("— (€120 · 30/04)", "✕ (...)") contengono
        # un € storico che parse_valore catturerebbe come prezzo vero
        if cella.startswith(("—", "✕")):
            continue
        p = parse_valore(cella)
        if p and not is_extra_letti(cella):
            result[nome] = p
    return result


def render_tabella_mese(calendario: dict, nomi: list, manuali: dict,
                         riferimento: str, giorni_mese: list[str],
                         oggi=None, nomi_in_media: set | None = None):
    header_giorni = [fmt_giorno(g) for g in giorni_mese]

    minmax = {}
    for g in giorni_mese:
        prezzi = prezzi_giorno(calendario, nomi, manuali, riferimento, g, oggi)
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

        row = [nome]
        row_colori = [""]
        for g in giorni_mese:
            cella, _ = lookup(calendario, nome, g, oggi)
            p        = parse_valore(cella)
            if cella.startswith("✕"):
                colore = COLORE_ESAURITO
            elif cella.startswith("—") or not cella:
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
    row_media = ["MEDIA"]
    row_media_colori = [COLORE_MEDIA]
    for g in giorni_mese:
        testo, debole = media_giorno(calendario, nomi, manuali, riferimento, g, oggi, nomi_in_media)
        row_media.append(testo)
        row_media_colori.append(COLORE_MEDIA_DEBOLE if debole else COLORE_MEDIA)
    rows_data.append(row_media)
    rows_colori.append(row_media_colori)

    # riga Hotel Nuovo Tirreno (riferimento)
    if riferimento:
        row_rif = [f"▶ {riferimento}"]
        row_rif_colori = [COLORE_RIFERIMENTO]
        for g in giorni_mese:
            cella, _ = lookup(calendario, riferimento, g, oggi)
            p        = parse_valore(cella)
            if cella.startswith("✕"):
                colore = COLORE_ESAURITO
            elif cella.startswith("—") or not cella:
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
        nome = rows_data[idx][0]
        border_bold = ""
        if nome == "MEDIA":
            border_bold = "font-weight: bold; border-top: 3px solid #6b7280"
        elif nome.startswith("▶"):
            border_bold = "border-top: 3px solid #d1d5db"
        result = []
        for c in cols:
            if c:
                s = f"background-color: {c}; color: #1a1a1a; font-size: 0.85rem"
                if border_bold:
                    s += f"; {border_bold}"
                result.append(s)
            else:
                result.append(border_bold)
        return result

    today_iso = date.today().isoformat()
    anni = {date.fromisoformat(g).year for g in giorni_mese}
    festivi = set().union(*(festivi_italiani(a) for a in anni))
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
        {"selector": "th", "props": [
            ("background-color", "#f0f2f6"), ("font-size", "0.78rem"),
            ("font-weight", "600"), ("text-align", "center"),
        ]},
    ]
    for i, g in enumerate(giorni_mese):
        col_n = i + 2  # colonna 1 = Hotel, CSS è 1-indexed
        giorno_dt = date.fromisoformat(g)
        if giorno_dt.weekday() >= 5 or g in festivi:
            sticky_css.append({"selector": f"th:nth-child({col_n})", "props": [
                ("color", "#b91c1c"),
            ]})
        if g == today_iso:
            sticky_css.append({"selector": f"th:nth-child({col_n})", "props": [
                ("background-color", "#fef3c7"), ("color", "#92400e"),
                ("border-bottom", "2px solid #f59e0b"),
            ]})
            sticky_css.append({"selector": f"td:nth-child({col_n})", "props": [
                ("border-left", "2px solid #f59e0b"),
                ("border-right", "2px solid #f59e0b"),
            ]})
    styled = df.style.apply(style_fn, axis=1).set_table_styles(sticky_css).hide(axis="index")
    html = styled.to_html()
    st.markdown(f'<div style="overflow-x:auto;width:100%">{html}</div>', unsafe_allow_html=True)


# ── UI principale ────────────────────────────────────────────────────────────

st.set_page_config(page_title="HotelCompare", layout="wide")
st.markdown(CSS_GLOBALE, unsafe_allow_html=True)
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
        data_agg = _fmt_data_agg(max(data_vista_vals))
    else:
        data_agg = "—"

    st.sidebar.markdown(f"📅 **{periodo}**  \n🏨 {len(calendario)} hotel  \n🔄 {data_agg}", unsafe_allow_html=True)
else:
    computed = scelta.split("_computed")[-1].replace(".json", "")
    if len(computed) == 8:
        data_agg = _fmt_data_agg(date(int(computed[:4]), int(computed[4:6]), int(computed[6:8])))
    else:
        data_agg = "—"
    st.sidebar.markdown(f"📅 **{meta.get('data_inizio')} → {meta.get('data_fine')}**  \n🏨 {len(calendario)} hotel  \n🔄 {data_agg}", unsafe_allow_html=True)

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
st.sidebar.markdown(
    f"<span style='background:{COLORE_MEDIA_DEBOLE};padding:2px 8px;border-radius:3px'>€ 250° MEDIA sbiadita</span>"
    f"<br><span style='font-size:0.8rem;color:#666'>meno di metà degli hotel ha una doppia quel "
    "giorno: prezzo trainato dalle camere care rimaste — leggi con cautela</span>",
    unsafe_allow_html=True
)

# Tutti i giorni
oggi = date.today().isoformat()
tutti_giorni = sorted(set(
    g for hotel_cal in calendario.values() for g in hotel_cal
    if g >= oggi
))

if not tutti_giorni:
    st.warning("Nessun dato nel file selezionato.")
    st.stop()

# Nomi hotel e riferimento
cfg_raw    = json.loads((Path(__file__).parent / "competitors.json").read_text())
manuali    = {c["nome"]: c["nota"] for c in cfg_raw["competitor"] if "nota" in c}
riferimento = next((c["nome"] for c in cfg_raw["competitor"] if c.get("riferimento")), "")
nomi       = list(calendario.keys())

# hotel ammessi alla media: calcolato una volta su tutti i giorni futuri.
# Quali hotel restano fuori e perché è una decisione statistica interna
# (vedi docs/decisioni-numeri.md), non informazione da mostrare all'utente.
oggi_d = date.today()
nomi_in_media = {n for n in nomi if n not in manuali and n != riferimento
                 and hotel_in_media(calendario, n, tutti_giorni, oggi_d)}

# Navigazione mese
mesi_disponibili = sorted(set(g[:7] for g in tutti_giorni))

if "mese_idx" not in st.session_state:
    st.session_state.mese_idx = 0

idx = max(0, min(st.session_state.mese_idx, len(mesi_disponibili) - 1))

mesi_per_riga = min(len(mesi_disponibili), 6)
righe = [mesi_disponibili[i:i+mesi_per_riga] for i in range(0, len(mesi_disponibili), mesi_per_riga)]
for riga in righe:
    cols = st.columns(mesi_per_riga)
    for j, mese in enumerate(riga):
        with cols[j]:
            if st.button(
                mese_label(mese),
                key=f"mese_{mese}",
                use_container_width=True,
                type="primary" if mese == mesi_disponibili[idx] else "secondary",
            ):
                st.session_state.mese_idx = mesi_disponibili.index(mese)
                st.rerun()

st.subheader(mese_label(mesi_disponibili[idx]))

giorni_mese = [g for g in tutti_giorni if g.startswith(mesi_disponibili[idx])]
render_tabella_mese(calendario, nomi, manuali, riferimento, giorni_mese, oggi_d, nomi_in_media)

st.caption("La riga **MEDIA** considera solo doppie confrontabili viste negli ultimi 15 giorni "
           "(i prezzi più vecchi restano in tabella ma non entrano nella media).")

# Legenda prezzi
with st.expander("Legenda prezzi"):
    st.markdown("""
| Simbolo | Significato |
|---|---|
| `€ 120*` | B&B, matrimoniale standard (doppia + colazione, prezzo reale) |
| `€ 136≈` | solo camera + stima colazione (€8/persona) — colazione non trovata |
| `€ 120×7` | prezzo da soggiorno minimo 7 notti |
| `€ 120#*` | B&B economy double (`#≈` = economy + stima colazione) |
| `~€ 120` | matrimoniale trovata, tipo pensione non identificabile |
| `€ 120S` | singola (esclusa dalle medie) |
| `€ 120T` | tripla (fallback — esclusa dalle medie) |
| `€ 120Q` | quadrupla (fallback estremo — esclusa dalle medie) |
| `€ 120A` | appartamento (fallback — escluso dalle medie) |
| `✕` | esaurito (indicativo) |
| `— (€120 · 30/04)` | non disponibile oggi (o prezzo più vecchio di 15 giorni) — ultimo noto |
""")
