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
        "2026-05-01": {"prezzo": "€ 120", "notti": 1, "stato": "ok", "data_vista": "YYYY-MM-DD"},
        ...
      }
    }
  }

Il campo "notti" indica da quale durata di soggiorno deriva il prezzo.
Il campo "data_vista" indica quando è stato scrappato quel prezzo.
Giorni consecutivi con lo stesso notti>1 condividono la stessa query (soggiorno lungo).
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


def _safe_nome(nome: str) -> str:
    """Converte il nome hotel in un nome file sicuro."""
    return "".join(c if c.isalnum() else "_" for c in nome).strip("_")[:40]


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


# ── loop per singolo hotel ───────────────────────────────────────────────────

def _scrapa_giorni_hotel(page, nome: str, url: str, giorni: list,
                          adulti: int, data_fine: date,
                          cal_hotel: dict, meta: dict,
                          partial_path: Path, oggi_str: str):
    """
    Scrapa tutti i giorni per un hotel. Modifica cal_hotel in place.
    Salva checkpoint incrementale su partial_path.
    """
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

        res["data_vista"] = oggi_str

        notti = res.get("notti") or 1
        if notti > 1:
            ultimo_coperto = giorno + timedelta(days=notti - 1)
            print(f"    ↳ soggiorno {notti}n, copre anche "
                  f"{giorno + timedelta(1)} … {ultimo_coperto}")

        for i in range(notti):
            g = giorno + timedelta(days=i)
            if g < data_fine:
                cal_hotel[str(g)] = res.copy()

        d_idx += notti
        _salva_json(partial_path, {"meta": meta, "calendario": {nome: cal_hotel}})


# ── worker per ProcessPoolExecutor ───────────────────────────────────────────

def scrapa_hotel_worker(args: tuple) -> tuple[str, dict]:
    """
    Funzione top-level (picklable) per ProcessPoolExecutor.
    Crea il proprio browser Playwright, scrapa un hotel, chiude il browser.

    args: (nome, url, data_inizio_str, data_fine_str, adulti,
           output_dir_str, from_str, to_str, oggi_str, user_agent)
    """
    (nome, url, data_inizio_str, data_fine_str, adulti,
     output_dir_str, from_str, to_str, oggi_str, user_agent) = args

    from playwright.sync_api import sync_playwright

    output_dir  = Path(output_dir_str)
    safe        = _safe_nome(nome)
    prog_path   = output_dir / f"partial_{safe}_from{from_str}_to{to_str}_inprogress.json"
    done_path   = output_dir / f"partial_{safe}_from{from_str}_to{to_str}_computed{oggi_str}.json"

    data_inizio = date.fromisoformat(data_inizio_str)
    data_fine   = date.fromisoformat(data_fine_str)
    giorni      = list(giorno_range(data_inizio, data_fine))

    cal_hotel: dict = {}
    if prog_path.exists():
        try:
            d = json.loads(prog_path.read_text(encoding="utf-8"))
            cal_hotel = d.get("calendario", {}).get(nome, {})
            fatti = sum(1 for g in giorni if str(g) in cal_hotel)
            print(f"[{nome}] checkpoint: {fatti}/{len(giorni)} già fatti")
        except Exception:
            cal_hotel = {}

    giorni_mancanti = [g for g in giorni if str(g) not in cal_hotel]
    if not giorni_mancanti:
        print(f"[{nome}] già completo — skip")
        if prog_path.exists():
            prog_path.replace(done_path)
        return nome, cal_hotel

    print(f"[{nome}] {len(giorni_mancanti)} giorni da scrappare")

    meta = {
        "nome":        nome,
        "data_inizio": data_inizio_str,
        "data_fine":   data_fine_str,
        "adulti":      adulti,
    }

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=user_agent,
            locale="it-IT",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        _scrapa_giorni_hotel(page, nome, url, giorni, adulti, data_fine,
                             cal_hotel, meta, prog_path, oggi_str)
        browser.close()

    if prog_path.exists():
        prog_path.replace(done_path)

    return nome, cal_hotel


# ── loop principale (compatibilità) ─────────────────────────────────────────

def scrapa_calendario(page, urls: dict[str, str], data_inizio: date, data_fine: date,
                      adulti: int, json_path: Path) -> dict:
    """
    Scrapa prezzi per ogni competitor sequenzialmente (un browser condiviso).
    Usato da test_one_night.py e come fallback per max_workers=1.
    """
    giorni = list(giorno_range(data_inizio, data_fine))
    oggi_str = str(date.today())

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
        cal_hotel       = calendario.setdefault(nome, {})
        giorni_mancanti = [g for g in giorni if str(g) not in cal_hotel]

        if not giorni_mancanti:
            print(f"[{idx}/{totale}] {nome} — già completo, saltato")
            continue

        print(f"[{idx}/{totale}] {nome} — {len(giorni_mancanti)} giorni da scrappare")

        _scrapa_giorni_hotel(page, nome, url, giorni, adulti, data_fine,
                             cal_hotel, meta, json_path, oggi_str)

        _salva_json(json_path, {"meta": meta, "calendario": calendario})

    return calendario
