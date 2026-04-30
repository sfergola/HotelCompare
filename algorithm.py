"""
algorithm.py — logica greedy per-giorno per la costruzione del calendario prezzi.

Responsabilità:
  - iterare su ogni giorno del periodo
  - per ogni giorno, trovare il soggiorno più breve che restituisce una doppia
  - fallback a tripla/quadrupla se non trovata doppia entro 7 notti
  - salvare il calendario su JSON in modo incrementale (write-then-rename)
  - riprendere da checkpoint se il run precedente è stato interrotto

Struttura JSON prodotta:
  {
    "meta": {"data_inizio": "YYYY-MM-DD", "data_fine": "YYYY-MM-DD", "adulti": N},
    "calendario": {
      "Hotel Sirio": {
        "2026-05-01": {"prezzo": "€ 120", "notti": 1, "stato": "ok"},
        "2026-05-02": {"prezzo": "€ 120", "notti": 3, "stato": "ok"},
        ...
      }
    }
  }

Il campo "notti" indica da quale durata di soggiorno deriva il prezzo.
Giorni consecutivi con lo stesso notti>1 condividono la stessa query.
"""

import json
import random
import time
from datetime import date, timedelta
from pathlib import Path

from scraper import scrapa_query, is_extra_letti

MAX_NOTTI = 7


# ── utilità ─────────────────────────────────────────────────────────────────

def giorno_range(start: date, end: date):
    """Yield ogni giorno in [start, end)."""
    d = start
    while d < end:
        yield d
        d += timedelta(days=1)


def _salva_json(path: Path, data: dict):
    """Scrittura atomica: scrive su .tmp poi rinomina, evita corruzione in caso di crash."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _is_fallback(prezzo: str) -> bool:
    """True se il prezzo viene da tripla o quadrupla (T/Q) — non ideale ma accettabile."""
    return is_extra_letti(prezzo)


# ── logica per singolo giorno ────────────────────────────────────────────────

def scrapa_giorno(page, booking_url: str, checkin: date, adulti: int,
                  data_fine: date) -> dict:
    """
    Trova il prezzo per notte a partire da checkin, provando 1n → MAX_NOTTI.

    Strategia:
      - Commit alla prima doppia/singola trovata (qualsiasi pensione)
      - Se solo tripla/quadrupla trovate, usa il risultato con meno notti
      - Se "esaurito" su tutte le durate, segnala esaurito
      - Se nulla trovato, segnala non_trovato

    Returns:
        {"prezzo": str|None, "notti": int|None, "stato": str}
    """
    miglior_doppia   = None
    miglior_fallback = None
    qualsiasi_esaurito = False

    for n in range(1, MAX_NOTTI + 1):
        if checkin + timedelta(days=n) > data_fine:
            break

        res = scrapa_query(page, booking_url, checkin, n, adulti)
        time.sleep(random.uniform(4.0, 8.0))

        if res["stato"] == "esaurito":
            qualsiasi_esaurito = True
            continue

        if res["prezzo"] is None:
            continue

        if not _is_fallback(res["prezzo"]):
            miglior_doppia = {"prezzo": res["prezzo"], "notti": n, "stato": "ok"}
            break
        else:
            if miglior_fallback is None:
                miglior_fallback = {"prezzo": res["prezzo"], "notti": n, "stato": "ok"}

    if miglior_doppia:
        return miglior_doppia
    if miglior_fallback:
        return miglior_fallback

    stato = "esaurito" if qualsiasi_esaurito else "non_trovato"
    return {"prezzo": None, "notti": None, "stato": stato}


# ── loop principale ──────────────────────────────────────────────────────────

def scrapa_calendario(page, urls: dict[str, str], data_inizio: date, data_fine: date,
                      adulti: int, json_path: Path) -> dict:
    """
    Scrapa prezzi per ogni competitor per ogni giorno del periodo.
    Riprende automaticamente da checkpoint se json_path esiste già.

    Returns:
        calendario: {"nome_hotel": {"YYYY-MM-DD": {"prezzo", "notti", "stato"}}}
    """
    giorni = list(giorno_range(data_inizio, data_fine))

    calendario: dict = {}
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            calendario = data.get("calendario", {})
            print(f"  Checkpoint trovato — riprendo da {json_path.name}\n")
        except Exception:
            print("  Checkpoint corrotto, parto da zero.\n")

    meta = {
        "data_inizio": str(data_inizio),
        "data_fine":   str(data_fine),
        "adulti":      adulti,
    }

    totale = len(urls)
    for idx, (nome, url) in enumerate(urls.items(), 1):
        cal_hotel = calendario.setdefault(nome, {})
        giorni_mancanti = [g for g in giorni if str(g) not in cal_hotel]

        if not giorni_mancanti:
            print(f"[{idx}/{totale}] {nome} — già completo, saltato")
            continue

        print(f"[{idx}/{totale}] {nome} — {len(giorni_mancanti)} giorni da scrappare")

        d_idx = 0
        while d_idx < len(giorni):
            giorno = giorni[d_idx]
            g_str  = str(giorno)

            if g_str in cal_hotel:
                d_idx += 1
                continue

            print(f"  {g_str} ...", end=" ", flush=True)
            res = scrapa_giorno(page, url, giorno, adulti, data_fine)
            print(res["prezzo"] or f"({res['stato']})")

            notti = res.get("notti") or 1
            for i in range(notti):
                g = giorno + timedelta(days=i)
                if g < data_fine:
                    cal_hotel[str(g)] = res.copy()

            d_idx += notti

            _salva_json(json_path, {"meta": meta, "calendario": calendario})

    return calendario
