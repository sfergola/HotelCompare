"""
report.py — generazione report CSV e TXT dal calendario prezzi.

Input atteso (calendario):
    {
      "Hotel Sirio": {
        "2026-05-01": {"prezzo": "€ 120", "notti": 1, "stato": "ok"},
        ...
      }
    }

Formato celle:
    "€ 120"    = prezzo/notte trovato
    "€ 120×3"  = prezzo/notte da soggiorno di 3 notti (minimum stay)
    "✕"        = esaurito (indicativo)
    "—"        = non trovato / non disponibile
"""

from datetime import date

from scraper import (fmt_storico, lookup_entry, filtra_prezzi_anomali,
                     valore_per_media, hotel_in_media)


# ── helper ───────────────────────────────────────────────────────────────────

def _fmt_giorno(d: str) -> str:
    """Converte 'YYYY-MM-DD' in 'DD-MM'."""
    return d[8:10] + "-" + d[5:7]


_lookup = lookup_entry
_fmt_storico = fmt_storico


def _nomi_in_media(calendario: dict, nomi: list[str], manuali: dict,
                   giorni: list[str], riferimento: str, oggi) -> set:
    return {n for n in nomi if n not in manuali and n != riferimento
            and hotel_in_media(calendario, n, giorni, oggi)}


def _media(calendario: dict, nomi: list[str], manuali: dict, giorno: str,
           riferimento: str = "", oggi=None, nomi_in_media: set | None = None) -> str:
    valori = []
    for nome in nomi:
        if nome in manuali or nome == riferimento:
            continue
        if nomi_in_media is not None and nome not in nomi_in_media:
            continue
        entry = calendario.get(nome, {}).get(giorno)
        if not entry:
            continue
        v = valore_per_media(entry, oggi)
        if v is not None:
            valori.append(v)
    valori = filtra_prezzi_anomali(valori)
    if not valori:
        return ""
    return f"€ {int(sum(valori) / len(valori))}"


# ── CSV ──────────────────────────────────────────────────────────────────────

def genera_csv(calendario: dict, nomi: list[str], manuali: dict,
               giorni: list[str], riferimento: str = "") -> str:
    oggi = date.today()
    nomi_in_media = _nomi_in_media(calendario, nomi, manuali, giorni, riferimento, oggi)
    date_header = ",".join(_fmt_giorno(g) for g in giorni)
    righe = [f"Hotel,{date_header}"]

    for nome in nomi:
        if nome in manuali:
            righe.append(f"{nome},verifica manuale")
            continue
        celle = []
        for g in giorni:
            cella, _ = _lookup(calendario, nome, g, oggi)
            celle.append(cella)
        righe.append(f"{nome}," + ",".join(celle))

    medie = [_media(calendario, nomi, manuali, g, riferimento, oggi, nomi_in_media) for g in giorni]
    righe.append("MEDIA," + ",".join(medie))

    if manuali:
        righe.append("")
        for nome, nota in manuali.items():
            righe.append(f"{nome},{nota}")

    return "\n".join(righe)


# ── TXT ──────────────────────────────────────────────────────────────────────

def genera_report_testo(calendario: dict, nomi: list[str], manuali: dict,
                        giorni: list[str], riferimento: str = "") -> str:
    """
    Genera report TXT leggibile, suddiviso per mese.
    Ogni mese occupa un blocco separato.
    """
    from itertools import groupby

    def mese_di(g: str) -> str:
        return g[:7]

    oggi = date.today()
    nomi_in_media = _nomi_in_media(calendario, nomi, manuali, giorni, riferimento, oggi)
    righe_output = []

    for mese, giorni_mese_iter in groupby(giorni, key=mese_di):
        giorni_mese = list(giorni_mese_iter)
        anno, mm = mese.split("-")
        mesi_it = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                   "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
        titolo = f"── {mesi_it[int(mm)]} {anno} ──"
        righe_output.append(titolo)
        righe_output.append("")

        col_nome = 22
        col_data = 9

        header = " " * col_nome + "".join(f"{_fmt_giorno(g):<{col_data}}" for g in giorni_mese)
        sep    = "─" * (col_nome + col_data * len(giorni_mese))
        righe_output += [header, sep]

        for nome in nomi:
            if nome in manuali:
                righe_output.append(f"{nome:<{col_nome}}verifica manuale")
                righe_output.append(sep)
                continue

            riga = f"{nome:<{col_nome}}"
            for g in giorni_mese:
                cella, _ = _lookup(calendario, nome, g, oggi)
                riga += f"{cella:<{col_data}}"
            righe_output.append(riga)
            righe_output.append(sep)

        riga_media = f"{'MEDIA':<{col_nome}}"
        for g in giorni_mese:
            m = _media(calendario, nomi, manuali, g, riferimento, oggi, nomi_in_media)
            riga_media += f"{(m or '—'):<{col_data}}"
        righe_output.append(riga_media)
        righe_output.append("")

    righe_output += [
        "Legenda:",
        "  € 120*     = B&B, matrimoniale standard (doppia + colazione, prezzo reale)",
        "  € 136≈     = solo camera + stima colazione (€8/persona) — colazione non trovata",
        "  € 120×7    = prezzo da soggiorno minimo 7 notti",
        "  € 120#*    = B&B economy double  (#≈ = economy + stima colazione)",
        "  ~€ 120     = matrimoniale trovata, tipo pensione non identificabile",
        "  € 120S     = singola (esclusa dalle medie)",
        "  € 120T     = tripla (fallback — solo visuale, esclusa dalle medie)",
        "  € 120Q     = quadrupla (fallback estremo — solo visuale, esclusa dalle medie)",
        "  € 120A     = appartamento (fallback — solo visuale, escluso dalle medie)",
        "  ✕          = esaurito (indicativo — non affidabile al 100%)",
        "  —          = non disponibile / non trovato (o prezzo troppo vecchio)",
    ]
    if manuali:
        righe_output.append("")
        for nome, nota in manuali.items():
            righe_output.append(f"{nome}: {nota}")

    return "\n".join(righe_output)
