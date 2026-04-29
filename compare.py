"""
HotelCompare — scraper prezzi competitor su Booking.com
Uso: python compare.py

Cerca il prezzo di camera matrimoniale/doppia con colazione inclusa.
Output: CSV + report testo con hotel per riga, date per colonna, riga media.
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
KEYWORDS_NO_DISP      = ["non abbiamo disponibilità", "controlla date disponibili",
                         "non è disponibile per"]


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

def sabati_range(start: date, end: date):
    days_ahead = (5 - start.weekday()) % 7
    d = start + timedelta(days=days_ahead)
    while d < end:
        yield d
        d += timedelta(weeks=1)

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

def estrai_prezzo(page) -> str | None:
    testo_pagina = page.inner_text("body")
    testo_lower  = testo_pagina.lower()
    ha_strutture_simili = "strutture simili" in testo_lower
    righe = [r.strip() for r in testo_pagina.split("\n") if r.strip()]

    risultati: list[tuple[str, float, bool]] = []  # (nome_camera, prezzo, ha_colazione)

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
                    risultati.append((camera_corrente, prezzo_corrente, False))
                camera_corrente = r
                prezzo_corrente = None
                continue
            v = _parse_valore(r)
            if v and v > 20 and len(r) < 25 and prezzo_corrente is None:
                prezzo_corrente = v
                continue
            if prezzo_corrente is not None and camera_corrente:
                ha_colazione = any(k in rl for k in KEYWORDS_COLAZIONE)
                no_col = any(k in rl for k in ["solo pernottamento", "room only", "senza colazione"])
                if ha_colazione or no_col:
                    risultati.append((camera_corrente, prezzo_corrente, ha_colazione))
                    prezzo_corrente = None
        if camera_corrente and prezzo_corrente:
            risultati.append((camera_corrente, prezzo_corrente, False))

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
                ha_col = False
                for k in range(j + 1, min(j + 8, len(righe))):
                    rl = righe[k].lower()
                    if any(kw in rl for kw in KEYWORDS_COLAZIONE):
                        ha_col = True
                        break
                    if any(kw in rl for kw in ["solo pernottamento", "room only", "senza colazione"]):
                        break
                camera = "camera"
                for m in range(i - 1, max(i - 45, -1), -1):
                    rm = righe[m]
                    rml = rm.lower()
                    if (any(rml.startswith(k) for k in ["camera", "suite", "appartamento"])
                            and 10 < len(rm) < 90 and not EURO_RE.search(rm)):
                        camera = rm
                        break
                risultati.append((camera, v, ha_col))
                break

    # === Fallback: primo prezzo € nella sezione principale ===
    if not risultati:
        testo_principale = testo_pagina
        if ha_strutture_simili:
            idx = testo_pagina.lower().find("strutture simili")
            testo_principale = testo_pagina[:idx]
        m = EURO_RE.search(testo_principale)
        if m:
            v = float(m.group(1).replace(".", "").replace(",", "."))
            if v > 20:
                return f"~€ {int(v)}"
        return None

    # Priorità 1: matrimoniale/doppia + colazione
    bb_mat = [(p, n) for n, p, c in risultati
              if c and any(k in n.lower() for k in KEYWORDS_MATRIMONIALE)]
    if bb_mat:
        return f"€ {int(min(bb_mat)[0])}"

    # Priorità 2: qualsiasi camera + colazione
    bb_any = [(p, n) for n, p, c in risultati if c]
    if bb_any:
        return f"€ {int(min(bb_any)[0])}*"

    return None


# ── scraping notte ───────────────────────────────────────────────────────────

def scrapa_notte(page, nome: str, booking_url: str, checkin: date, adulti: int,
                 notti: int = 7) -> dict:
    checkout = checkin + timedelta(days=notti)
    url = build_url(booking_url, checkin, checkout, adulti)
    try:
        page.goto(url, wait_until="networkidle", timeout=40000)
        time.sleep(random.uniform(2.5, 4.5))
        chiudi_popup(page)
        page.evaluate("window.scrollTo(0, 1200)")
        time.sleep(1.5)
        prezzo = estrai_prezzo(page)
        if prezzo and notti > 1:
            v = _parse_valore(prezzo)
            if v:
                prefix = "~" if "~" in prezzo else ""
                suffix = "*" if prezzo.endswith("*") else ""
                per_notte = int(v / notti)
                prezzo = f"{prefix}€ {per_notte}{suffix}" if per_notte >= 25 else None
        stato  = "ok" if prezzo else "non_trovato"
    except Exception as e:
        prezzo = None
        stato  = f"errore: {str(e)[:60]}"
    return {"competitor": nome, "checkin": str(checkin), "prezzo": prezzo, "stato": stato}


# ── report ───────────────────────────────────────────────────────────────────

def genera_csv(risultati: list[dict], nomi: list[str], manuali: dict,
               date_uniche: list[str]) -> str:
    """Hotels per riga, date per colonna."""
    # Header
    righe = ["Hotel," + ",".join(d[5:] for d in date_uniche)]  # es. 28-Apr

    for nome in nomi:
        if nome in manuali:
            prezzi_riga = ["verifica manuale"] * len(date_uniche)
        else:
            prezzi_riga = []
            for d in date_uniche:
                res = next((r for r in risultati
                            if r["checkin"] == d and r["competitor"] == nome), None)
                prezzi_riga.append((res["prezzo"] if res else "") or "")
        righe.append(nome + "," + ",".join(prezzi_riga))

    # Riga media
    medie = []
    for d in date_uniche:
        valori = []
        for nome in nomi:
            if nome in manuali:
                continue
            res = next((r for r in risultati
                        if r["checkin"] == d and r["competitor"] == nome), None)
            if res and res["prezzo"]:
                v = _parse_valore(res["prezzo"])
                if v:
                    valori.append(v)
        medie.append(f"€ {int(sum(valori)/len(valori))}" if valori else "")
    righe.append("MEDIA," + ",".join(medie))

    if manuali:
        righe.append("")
        for nome, nota in manuali.items():
            righe.append(f"{nome},{nota}")

    return "\n".join(righe)


def genera_report_testo(risultati: list[dict], nomi: list[str], manuali: dict,
                        date_uniche: list[str]) -> str:
    """Report leggibile: hotel per riga, mostra solo prime 30 date + totale."""
    date_mostra = date_uniche[:30]
    col_hotel = 24
    col_data  = 8

    header = f"{'Hotel':<{col_hotel}}" + "".join(f"{d[5:]:<{col_data}}" for d in date_mostra)
    if len(date_uniche) > 30:
        header += f"  ... (+{len(date_uniche)-30} date nel CSV)"
    righe = [header, "-" * len(header)]

    for nome in nomi:
        if nome in manuali:
            riga = f"{nome:<{col_hotel}}" + "verifica manuale"
        else:
            riga = f"{nome:<{col_hotel}}"
            for d in date_mostra:
                res = next((r for r in risultati
                            if r["checkin"] == d and r["competitor"] == nome), None)
                p = (res["prezzo"] if res else "") or "—"
                riga += f"{p:<{col_data}}"
        righe.append(riga)

    # Riga media
    riga_media = f"{'MEDIA':<{col_hotel}}"
    for d in date_mostra:
        valori = []
        for nome in nomi:
            if nome in manuali:
                continue
            res = next((r for r in risultati
                        if r["checkin"] == d and r["competitor"] == nome), None)
            if res and res["prezzo"]:
                v = _parse_valore(res["prezzo"])
                if v:
                    valori.append(v)
        media = f"€{int(sum(valori)/len(valori))}" if valori else "—"
        riga_media += f"{media:<{col_data}}"
    righe.append(riga_media)

    righe.append("")
    righe.append("Legenda:")
    righe.append("  € 175  = matrimoniale B&B confermato")
    righe.append("  € 175* = B&B confermato, tipo camera non verificato")
    righe.append("  ~€ 175 = prezzo indicativo (soggiorno minimo, tipo camera non verificato)")
    righe.append("  —      = non disponibile / non trovato")
    if manuali:
        righe.append("")
        for nome, nota in manuali.items():
            righe.append(f"{nome}: {nota}")

    return "\n".join(righe)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    cfg       = carica_config()
    data_fine   = date.fromisoformat(cfg["data_fine"])
    adulti      = cfg.get("adulti", 2)
    oggi        = date.today()
    data_inizio = date.fromisoformat(cfg["data_inizio"]) if "data_inizio" in cfg else oggi
    giorni      = list(sabati_range(data_inizio, data_fine))

    print(f"HotelCompare — {len(cfg['competitor'])} competitor, {len(giorni)} sabati ({data_inizio} → {data_fine})\n")

    risultati   = []
    oggi_str    = str(oggi).replace("-", "")
    json_path   = OUTPUT_DIR / f"prezzi_{oggi_str}.json"
    csv_path    = OUTPUT_DIR / f"report_{oggi_str}.csv"
    txt_path    = OUTPUT_DIR / f"report_{oggi_str}.txt"

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
            urls = risolvi_urls(page, cfg)
            manuali = {c["nome"]: c["nota"] for c in cfg["competitor"] if "nota" in c}

            if not urls:
                print("Nessun URL trovato.")
                return

            nomi   = list(urls.keys())
            totale = len(giorni) * len(nomi)
            print(f"=== Fase 2: scraping ({totale} richieste, ~{totale*6//60} min) ===\n")

            for i, checkin in enumerate(giorni):
                for j, nome in enumerate(nomi):
                    n = i * len(nomi) + j + 1
                    print(f"[{n}/{totale}] {nome} — {checkin} ...", end=" ", flush=True)
                    res = scrapa_notte(page, nome, urls[nome], checkin, adulti)
                    risultati.append(res)
                    print(res["prezzo"] or f"({res['stato']})")

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
