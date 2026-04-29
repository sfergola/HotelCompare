"""
HotelCompare — scraper prezzi competitor su Booking.com
Uso: python compare.py

Cerca prezzi camera matrimoniale/doppia: solo camera e camera+colazione.
Output: CSV + report testo — ogni hotel su due righe (solo / B&B), date per colonna.
"""

import json, re, random, time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


CONFIG_PATH = Path(__file__).parent / "competitors.json"
OUTPUT_DIR  = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

EURO_RE = re.compile(r"€\s*(\d+(?:[.,]\d+)?)")

KEYWORDS_MATRIMONIALE = ["matrimoniale", "doppia", "double", "twin"]
KEYWORDS_COLAZIONE    = ["colazione inclusa", "prima colazione", "breakfast inclus",
                         "pernottamento e prima", "b&b", "eccezionale colazione"]
KEYWORDS_SOLO         = ["solo pernottamento", "room only", "senza colazione"]


# ── config ─────────────────────────────────────────────────────────────────

def carica_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)

def salva_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ── helpers ─────────────────────────────────────────────────────────────────

def date_range(start: date, end: date):
    d = start
    while d < end:
        yield d
        d += timedelta(days=1)

def build_url(booking_url: str, checkin: date, checkout: date, adulti: int) -> str:
    base = booking_url.split("?")[0]
    return (f"{base}?checkin={checkin}&checkout={checkout}"
            f"&group_adults={adulti}&no_rooms=1&selected_currency=EUR")

def chiudi_popup(page):
    for testo in ["Accetta", "Accetto", "Accept", "OK", "Chiudi", "Dismiss"]:
        try:
            btn = page.get_by_role("button", name=testo).first
            if btn.is_visible(timeout=800):
                btn.click()
                time.sleep(0.4)
        except PlaywrightTimeout:
            pass


# ── ricerca URL ─────────────────────────────────────────────────────────────

def cerca_url_booking(page, nome: str, citta: str) -> str | None:
    query = quote_plus(f"{nome} {citta}")
    url   = f"https://www.booking.com/searchresults.it.html?ss={query}&lang=it"
    print(f"  Cerco '{nome}' su Booking.com...", end=" ", flush=True)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(2.0, 3.5))
        chiudi_popup(page)
        for sel in [
            "[data-testid='property-card'] a[data-testid='title-link']",
            "[data-testid='property-card-container'] a",
        ]:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=4000):
                    href = el.get_attribute("href") or ""
                    if "/hotel/" in href:
                        base = href.split("?")[0]
                        if not base.startswith("http"):
                            base = "https://www.booking.com" + base
                        print(f"trovato → {base}")
                        return base
            except PlaywrightTimeout:
                continue
        print("non trovato")
        return None
    except Exception as e:
        print(f"errore: {e}")
        return None


def risolvi_urls(page, cfg: dict) -> dict[str, str]:
    urls: dict[str, str] = {}
    aggiornato = False
    for comp in cfg["competitor"]:
        nome = comp["nome"]
        if "nota" in comp:
            print(f"  '{nome}' → {comp['nota']}")
            continue
        if "booking_url" in comp:
            urls[nome] = comp["booking_url"].split("?")[0]
            print(f"  '{nome}' → già nel config")
            continue
        url = cerca_url_booking(page, nome, comp.get("citta", ""))
        if url:
            comp["booking_url"] = url
            urls[nome] = url
            aggiornato = True
        else:
            print(f"  ⚠ '{nome}' — saltato")
        time.sleep(random.uniform(2.0, 4.0))
    if aggiornato:
        salva_config(cfg)
        print("\n  ✓ competitors.json aggiornato con gli URL trovati.\n")
    return urls


# ── estrazione prezzo ────────────────────────────────────────────────────────

def _parse_valore(testo: str) -> float | None:
    m = EURO_RE.search(testo)
    if m:
        try:
            return float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            pass
    return None

def estrai_prezzo(page) -> dict:
    """
    Ritorna {"solo": str|None, "bb": str|None}.
    Considera solo camere matrimoniali/doppie con tipo pernottamento confermato.
    """
    testo_pagina = page.inner_text("body")
    righe = [r.strip() for r in testo_pagina.split("\n") if r.strip()]

    risultati: list[tuple[str, float, str | None]] = []  # (nome_camera, prezzo, board)

    # === Parser 1: layout tabella con header "Tipologia camera" ===
    start = None
    for i, r in enumerate(righe):
        if "Tipologia camera" in r or "tipo di camera" in r.lower():
            start = i
            break

    if start is not None:
        camera_corrente: str | None = None
        prezzo_corrente: float | None = None
        for r in righe[start: start + 250]:
            rl = r.lower()
            if (any(rl.startswith(k) for k in ["camera", "suite", "appartamento"])
                    and len(r) < 90 and not EURO_RE.search(r)
                    and "recension" not in rl):
                if camera_corrente and prezzo_corrente:
                    risultati.append((camera_corrente, prezzo_corrente, None))
                camera_corrente = r
                prezzo_corrente = None
                continue
            v = _parse_valore(r)
            if v and v > 20 and len(r) < 25 and prezzo_corrente is None:
                prezzo_corrente = v
                continue
            if prezzo_corrente is not None and camera_corrente:
                if any(k in rl for k in KEYWORDS_COLAZIONE):
                    risultati.append((camera_corrente, prezzo_corrente, "bb"))
                    camera_corrente = None
                    prezzo_corrente = None
                elif any(k in rl for k in KEYWORDS_SOLO):
                    risultati.append((camera_corrente, prezzo_corrente, "solo"))
                    camera_corrente = None
                    prezzo_corrente = None
        if camera_corrente and prezzo_corrente:
            risultati.append((camera_corrente, prezzo_corrente, None))

    # === Parser 2: layout card con "N° max persone" ===
    if not risultati:
        for i, r in enumerate(righe):
            if "n° max persone" not in r.lower() and "max persone" not in r.lower():
                continue
            for j in range(i + 1, min(i + 6, len(righe))):
                rj = righe[j]
                if rj.lower().startswith("prezzo"):
                    continue
                v = _parse_valore(rj)
                if not (v and v > 20):
                    continue
                board: str | None = None
                for k in range(j + 1, min(j + 8, len(righe))):
                    rl = righe[k].lower()
                    if any(kw in rl for kw in KEYWORDS_COLAZIONE):
                        board = "bb"
                        break
                    if any(kw in rl for kw in KEYWORDS_SOLO):
                        board = "solo"
                        break
                camera = "camera"
                for m_idx in range(i - 1, max(i - 45, -1), -1):
                    rm  = righe[m_idx]
                    rml = rm.lower()
                    if (any(rml.startswith(k) for k in ["camera", "suite", "appartamento"])
                            and 10 < len(rm) < 90 and not EURO_RE.search(rm)):
                        camera = rm
                        break
                risultati.append((camera, v, board))
                break

    if not risultati:
        return {"solo": None, "bb": None}

    matrimoniali = [(n, p, b) for n, p, b in risultati
                    if any(k in n.lower() for k in KEYWORDS_MATRIMONIALE)]

    if not matrimoniali:
        return {"solo": None, "bb": None}

    solo_prezzi = [p for n, p, b in matrimoniali if b == "solo"]
    bb_prezzi   = [p for n, p, b in matrimoniali if b == "bb"]

    return {
        "solo": f"€ {int(min(solo_prezzi))}" if solo_prezzi else None,
        "bb":   f"€ {int(min(bb_prezzi))}"   if bb_prezzi   else None,
    }


# ── scraping notte ───────────────────────────────────────────────────────────

def scrapa_notte(page, nome: str, booking_url: str, checkin: date, adulti: int,
                 notti: int = 1) -> dict:
    checkout = checkin + timedelta(days=notti)
    url = build_url(booking_url, checkin, checkout, adulti)
    try:
        page.goto(url, wait_until="networkidle", timeout=40000)
        time.sleep(random.uniform(2.5, 4.5))
        chiudi_popup(page)
        page.evaluate("window.scrollTo(0, 1200)")
        time.sleep(1.5)
        prezzi = estrai_prezzo(page)
        if notti > 1:
            for key in ("solo", "bb"):
                val = prezzi[key]
                if val:
                    v = _parse_valore(val)
                    if v:
                        per_notte = int(v / notti)
                        prezzi[key] = f"€ {per_notte}" if per_notte >= 25 else None
        solo  = prezzi["solo"]
        bb    = prezzi["bb"]
        stato = "ok" if (solo or bb) else "non_trovato"
    except Exception as e:
        solo  = None
        bb    = None
        stato = f"errore: {str(e)[:60]}"
    return {"competitor": nome, "checkin": str(checkin), "solo": solo, "bb": bb, "stato": stato}


# ── report ───────────────────────────────────────────────────────────────────

def genera_csv(risultati: list[dict], nomi: list[str], manuali: dict,
               date_uniche: list[str]) -> str:
    """Hotels per riga (2 righe ciascuno: solo + B&B), date per colonna."""
    righe = ["Hotel," + ",".join(d[5:] for d in date_uniche)]

    for nome in nomi:
        if nome in manuali:
            righe.append(nome + ",verifica manuale")
            continue
        solo_riga, bb_riga = [], []
        for d in date_uniche:
            res = next((r for r in risultati if r["checkin"] == d and r["competitor"] == nome), None)
            solo_riga.append((res["solo"] if res else "") or "")
            bb_riga.append((res["bb"]     if res else "") or "")
        righe.append(nome + " (solo)," + ",".join(solo_riga))
        righe.append(nome + " (B&B),"  + ",".join(bb_riga))

    solo_medie, bb_medie = [], []
    for d in date_uniche:
        sv, bv = [], []
        for nome in nomi:
            if nome in manuali:
                continue
            res = next((r for r in risultati if r["checkin"] == d and r["competitor"] == nome), None)
            if res:
                v = _parse_valore(res["solo"] or "")
                if v:
                    sv.append(v)
                v = _parse_valore(res["bb"] or "")
                if v:
                    bv.append(v)
        solo_medie.append(f"€ {int(sum(sv)/len(sv))}" if sv else "")
        bb_medie.append(f"€ {int(sum(bv)/len(bv))}"   if bv else "")

    righe.append("MEDIA (solo)," + ",".join(solo_medie))
    righe.append("MEDIA (B&B),"  + ",".join(bb_medie))

    if manuali:
        righe.append("")
        for nome, nota in manuali.items():
            righe.append(f"{nome},{nota}")

    return "\n".join(righe)


def genera_report_testo(risultati: list[dict], nomi: list[str], manuali: dict,
                        date_uniche: list[str]) -> str:
    """Report leggibile: hotel per riga (solo+B&B), prime 30 date."""
    date_mostra = date_uniche[:30]
    col_hotel   = 28
    col_data    = 8

    header = f"{'Hotel':<{col_hotel}}" + "".join(f"{d[5:]:<{col_data}}" for d in date_mostra)
    if len(date_uniche) > 30:
        header += f"  ... (+{len(date_uniche)-30} date nel CSV)"
    righe = [header, "-" * (col_hotel + col_data * len(date_mostra))]

    for nome in nomi:
        if nome in manuali:
            righe.append(f"{nome:<{col_hotel}}" + "verifica manuale")
            continue
        riga_solo = f"{nome + ' (solo)':<{col_hotel}}"
        riga_bb   = f"{nome + ' (B&B)':<{col_hotel}}"
        for d in date_mostra:
            res = next((r for r in risultati if r["checkin"] == d and r["competitor"] == nome), None)
            riga_solo += f"{(res['solo'] if res else '') or '—':<{col_data}}"
            riga_bb   += f"{(res['bb']   if res else '') or '—':<{col_data}}"
        righe.append(riga_solo)
        righe.append(riga_bb)

    riga_solo_m = f"{'MEDIA (solo)':<{col_hotel}}"
    riga_bb_m   = f"{'MEDIA (B&B)':<{col_hotel}}"
    for d in date_mostra:
        sv, bv = [], []
        for nome in nomi:
            if nome in manuali:
                continue
            res = next((r for r in risultati if r["checkin"] == d and r["competitor"] == nome), None)
            if res:
                v = _parse_valore(res["solo"] or "")
                if v:
                    sv.append(v)
                v = _parse_valore(res["bb"] or "")
                if v:
                    bv.append(v)
        riga_solo_m += f"{f'€{int(sum(sv)/len(sv))}' if sv else '—':<{col_data}}"
        riga_bb_m   += f"{f'€{int(sum(bv)/len(bv))}' if bv else '—':<{col_data}}"
    righe.append(riga_solo_m)
    righe.append(riga_bb_m)

    righe.append("")
    righe.append("Legenda:")
    righe.append("  € 115 (solo) = matrimoniale/doppia, solo pernottamento")
    righe.append("  € 130 (B&B)  = matrimoniale/doppia, colazione inclusa")
    righe.append("  —            = non disponibile / tipo camera non rilevato")
    if manuali:
        righe.append("")
        for nome, nota in manuali.items():
            righe.append(f"{nome}: {nota}")

    return "\n".join(righe)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    cfg         = carica_config()
    data_fine   = date.fromisoformat(cfg["data_fine"])
    adulti      = cfg.get("adulti", 2)
    oggi        = date.today()
    data_inizio = date.fromisoformat(cfg["data_inizio"]) if "data_inizio" in cfg else oggi
    giorni      = list(date_range(data_inizio, data_fine))

    print(f"HotelCompare — {len(cfg['competitor'])} competitor, "
          f"{len(giorni)} giorni ({data_inizio} → {data_fine})\n")

    risultati   = []
    from_str    = str(data_inizio).replace("-", "")
    to_str      = str(data_fine).replace("-", "")
    oggi_str    = str(oggi).replace("-", "")
    stem        = f"competitors_from{from_str}_to{to_str}_computed{oggi_str}"
    json_path   = OUTPUT_DIR / f"{stem}.json"
    csv_path    = OUTPUT_DIR / f"{stem}.csv"
    txt_path    = OUTPUT_DIR / f"{stem}.txt"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            locale="it-IT",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        try:
            print("=== Fase 1: risoluzione URL ===")
            urls    = risolvi_urls(page, cfg)
            manuali = {c["nome"]: c["nota"] for c in cfg["competitor"] if "nota" in c}

            if not urls:
                print("Nessun URL trovato.")
                return

            nomi   = list(urls.keys())
            totale = len(giorni) * len(nomi)
            print(f"=== Fase 2: scraping ({totale} richieste, ~{totale*7//60} min) ===\n")

            for i, checkin in enumerate(giorni):
                for j, nome in enumerate(nomi):
                    n = i * len(nomi) + j + 1
                    print(f"[{n}/{totale}] {nome} — {checkin} ...", end=" ", flush=True)
                    res = scrapa_notte(page, nome, urls[nome], checkin, adulti)
                    risultati.append(res)
                    if res["solo"] or res["bb"]:
                        parti = []
                        if res["solo"]: parti.append(f"solo:{res['solo']}")
                        if res["bb"]:   parti.append(f"B&B:{res['bb']}")
                        print("  ".join(parti))
                    else:
                        print(f"({res['stato']})")

                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(risultati, f, ensure_ascii=False, indent=2)

                    time.sleep(random.uniform(4.0, 8.0))

        finally:
            browser.close()

    tutti_nomi  = list(urls.keys()) + list(manuali.keys())
    date_uniche = sorted(set(r["checkin"] for r in risultati))

    csv_path.write_text(
        genera_csv(risultati, tutti_nomi, manuali, date_uniche), encoding="utf-8")
    txt_path.write_text(
        genera_report_testo(risultati, tutti_nomi, manuali, date_uniche), encoding="utf-8")

    print(f"\nDone.\n  CSV  : {csv_path}\n  Testo: {txt_path}\n")
    print(genera_report_testo(risultati, tutti_nomi, manuali, date_uniche))


if __name__ == "__main__":
    main()
