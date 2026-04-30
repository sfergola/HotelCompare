"""
HotelCompare — scraper prezzi competitor su Booking.com
Uso: python compare.py

Per ogni sabato nel range esegue 3 query:
  Sab→Sab (7n)  — settimana intera
  Lun→Sab (5n)  — prima parte settimana (checkin lunedì)
  Sab→Lun (2n)  — weekend (checkin sabato, checkout lunedì)

Prezzo mostrato: solo camera se trovato, B&B* se solo camera non disponibile.
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
KEYWORDS_ECONOMY      = ["economy", "budget", "basic"]
KEYWORDS_SINGOLA      = ["singola", "single"]
KEYWORDS_TRIPLA       = ["tripla", "triple", "3 letti", "tre letti"]
KEYWORDS_QUADRUPLA    = ["quadrupla", "quadruple", "4 letti", "quattro letti"]
KEYWORDS_COLAZIONE    = ["colazione inclusa", "prima colazione", "breakfast inclus",
                         "pernottamento e prima", "b&b", "eccezionale colazione"]
KEYWORDS_SOLO         = ["solo pernottamento", "room only", "senza colazione"]

# parole con cui può iniziare il nome di una camera
ROOM_START = ["camera", "suite", "appartamento", "stanza", "bungalow", "studio",
              "monolocale", "economy", "double", "twin", "single", "singola",
              "standard", "superior", "deluxe", "classic", "comfort", "junior"]

# (label, offset_giorni_dal_sabato, notti)
TIPI_QUERY = [
    ("Sab→Sab",  0, 7),
    ("Lun→Sab", +2, 5),
    ("Sab→Lun",  0, 2),
]


# ── config ─────────────────────────────────────────────────────────────────

def carica_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)

def salva_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ── helpers ─────────────────────────────────────────────────────────────────

def sab_range(start: date, end: date):
    """Yield ogni sabato in [start, end)."""
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

def _is_economy(nome: str) -> bool:
    return any(k in nome.lower() for k in KEYWORDS_ECONOMY)

def _is_singola(nome: str) -> bool:
    return any(k in nome.lower() for k in KEYWORDS_SINGOLA)

def _is_tripla(nome: str) -> bool:
    return any(k in nome.lower() for k in KEYWORDS_TRIPLA)

def _is_quadrupla(nome: str) -> bool:
    return any(k in nome.lower() for k in KEYWORDS_QUADRUPLA)

def _is_extra_letti(prezzo: str) -> bool:
    return bool(re.search(r'\d[TQ]\*?$', prezzo))

def estrai_prezzo(page) -> str | None:
    """
    Ritorna:
      "€ NNN"   = solo camera, matrimoniale/doppia standard
      "€ NNN*"  = B&B, matrimoniale/doppia standard
      "€ NNN#"  = solo camera, economy/budget double
      "€ NNN#*" = B&B, economy/budget double
      "€ NNNS"  = solo camera, singola (nessuna doppia trovata)
      "€ NNNS*" = B&B, singola
      "~€ NNN"  = matrimoniale trovata, tipo pensione non identificato
      "~€ NNN#" = economy double, pensione non identificata
      "~€ NNNS" = singola, pensione non identificata
      "€ NNNT"  = tripla (fallback, solo visuale — esclusa dalle medie)
      "€ NNNT*" = B&B, tripla
      "€ NNNQ"  = quadrupla (fallback estremo, solo visuale — esclusa dalle medie)
      "€ NNNQ*" = B&B, quadrupla
      None      = non trovato
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
            if (any(rl.startswith(k) for k in ROOM_START)
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
                    if (any(rml.startswith(k) for k in ROOM_START)
                            and 10 < len(rm) < 90 and not EURO_RE.search(rm)):
                        camera = rm
                        break
                risultati.append((camera, v, board))
                break

    if not risultati:
        return None

    matrimoniali = [(n, p, b) for n, p, b in risultati
                    if any(k in n.lower() for k in KEYWORDS_MATRIMONIALE)]
    singole      = [(n, p, b) for n, p, b in risultati
                    if _is_singola(n) and not any(k in n.lower() for k in KEYWORDS_MATRIMONIALE)]

    standard = [(n, p, b) for n, p, b in matrimoniali if not _is_economy(n)]
    economy  = [(n, p, b) for n, p, b in matrimoniali if _is_economy(n)]

    for gruppo, marker in [(standard, ""), (economy, "#"), (singole, "S")]:
        solo_p = [p for n, p, b in gruppo if b == "solo"]
        bb_p   = [p for n, p, b in gruppo if b == "bb"]
        if solo_p:
            return f"€ {int(min(solo_p))}{marker}"
        if bb_p:
            return f"€ {int(min(bb_p))}{marker}*"

    # board non identificata ma camera giusta trovata: mostra con ~ (pensione ignota)
    for gruppo, marker in [(standard, ""), (economy, "#"), (singole, "S")]:
        none_p = [p for n, p, b in gruppo if b is None]
        if none_p:
            return f"~€ {int(min(none_p))}{marker}"

    triple    = [(n, p, b) for n, p, b in risultati if _is_tripla(n)]
    quadruple = [(n, p, b) for n, p, b in risultati if _is_quadrupla(n)]

    for gruppo, marker in [(triple, "T"), (quadruple, "Q")]:
        if not gruppo:
            continue
        solo_p = [p for n, p, b in gruppo if b == "solo"]
        bb_p   = [p for n, p, b in gruppo if b == "bb"]
        any_p  = [p for n, p, b in gruppo]
        if solo_p:
            return f"€ {int(min(solo_p))}{marker}"
        if bb_p:
            return f"€ {int(min(bb_p))}{marker}*"
        if any_p:
            return f"€ {int(min(any_p))}{marker}"

    return None


# ── scraping notte ───────────────────────────────────────────────────────────

def scrapa_notte(page, nome: str, booking_url: str, checkin: date, adulti: int,
                 notti: int, sab: date, tipo: str) -> dict:
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
                prefix    = "~" if prezzo.startswith("~") else ""
                m_sfx     = re.match(r'~?€\s*\d+(.*)', prezzo)
                suffix    = m_sfx.group(1) if m_sfx else ""
                per_notte = int(v / notti)
                prezzo    = f"{prefix}€ {per_notte}{suffix}" if per_notte >= 25 else None
        stato = "ok" if prezzo else "non_trovato"
    except Exception as e:
        prezzo = None
        stato  = f"errore: {str(e)[:60]}"
    return {
        "competitor": nome,
        "settimana":  str(sab),
        "tipo":       tipo,
        "checkin":    str(checkin),
        "prezzo":     prezzo,
        "stato":      stato,
    }


# ── report ───────────────────────────────────────────────────────────────────

def _lookup(risultati, sab, nome, tipo):
    res = next((r for r in risultati
                if r["settimana"] == sab and r["competitor"] == nome and r["tipo"] == tipo), None)
    return (res["prezzo"] if res else None) or "—"

def genera_csv(risultati: list[dict], nomi: list[str], manuali: dict,
               sab_uniche: list[str]) -> str:
    date_header = ",".join(s[8:10] + "-" + s[5:7] for s in sab_uniche)
    righe = [f"Hotel,Tipo,{date_header}"]

    for nome in nomi:
        if nome in manuali:
            righe.append(f"{nome},—,verifica manuale")
            continue
        for tipo, _, _ in TIPI_QUERY:
            prezzi = ",".join(_lookup(risultati, s, nome, tipo) for s in sab_uniche)
            righe.append(f"{nome},{tipo},{prezzi}")

    for tipo, _, _ in TIPI_QUERY:
        medie = []
        for s in sab_uniche:
            prezzi = [_lookup(risultati, s, n, tipo) for n in nomi if n not in manuali]
            valori = [_parse_valore(p) for p in prezzi if not _is_extra_letti(p)]
            valori = [v for v in valori if v]
            medie.append(f"€ {int(sum(valori)/len(valori))}" if valori else "")
        righe.append(f"MEDIA,{tipo}," + ",".join(medie))

    if manuali:
        righe.append("")
        for nome, nota in manuali.items():
            righe.append(f"{nome},,{nota}")

    return "\n".join(righe)


def genera_report_testo(risultati: list[dict], nomi: list[str], manuali: dict,
                        sab_uniche: list[str]) -> str:
    sab_mostra = sab_uniche[:18]
    col_nome   = 20
    col_tipo   = 9
    col_data   = 8
    larghezza  = col_nome + col_tipo + col_data * len(sab_mostra)

    header = (" " * (col_nome + col_tipo)
              + "".join(f"{s[8:10]+'-'+s[5:7]:<{col_data}}" for s in sab_mostra))
    sep    = "─" * larghezza
    righe  = [header, sep]

    for nome in nomi:
        if nome in manuali:
            righe.append(f"{nome:<{col_nome + col_tipo}}verifica manuale")
            righe.append(sep)
            continue
        for k, (tipo, _, _) in enumerate(TIPI_QUERY):
            nome_col = f"{nome:<{col_nome}}" if k == 0 else " " * col_nome
            riga = nome_col + f"{tipo:<{col_tipo}}"
            for s in sab_mostra:
                p = _lookup(risultati, s, nome, tipo)
                riga += f"{p:<{col_data}}"
            righe.append(riga)
        righe.append(sep)

    for k, (tipo, _, _) in enumerate(TIPI_QUERY):
        nome_col = f"{'MEDIA':<{col_nome}}" if k == 0 else " " * col_nome
        riga = nome_col + f"{tipo:<{col_tipo}}"
        for s in sab_mostra:
            prezzi = [_lookup(risultati, s, n, tipo) for n in nomi if n not in manuali]
            valori = [_parse_valore(p) for p in prezzi if not _is_extra_letti(p)]
            valori = [v for v in valori if v]
            m = f"€{int(sum(valori)/len(valori))}" if valori else "—"
            riga += f"{m:<{col_data}}"
        righe.append(riga)

    if len(sab_uniche) > 18:
        righe.append(f"\n  ... (+{len(sab_uniche)-18} settimane nel CSV)")

    righe += [
        "",
        "Legenda:",
        "  € 140   = solo camera, matrimoniale/doppia standard",
        "  € 140*  = B&B, matrimoniale/doppia standard",
        "  € 120#  = solo camera, economy/budget double",
        "  € 120#* = B&B, economy double",
        "  € 80S   = solo camera, singola (nessuna doppia trovata)",
        "  € 80S*  = B&B, singola",
        "  ~€ 140  = matrimoniale trovata, tipo pensione non identificato",
        "  € 80T   = tripla (fallback — solo visuale, esclusa dalle medie)",
        "  € 80T*  = B&B, tripla",
        "  € 80Q   = quadrupla (fallback estremo — solo visuale, esclusa dalle medie)",
        "  € 80Q*  = B&B, quadrupla",
        "  —       = non disponibile / tipo camera non rilevato",
        "",
        "Tipi soggiorno:",
        "  Sab→Sab (7n) = settimana intera",
        "  Lun→Sab (5n) = da lunedì al sabato (prima parte settimana)",
        "  Sab→Lun (2n) = da sabato a lunedì (weekend)",
    ]
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
    sabati      = list(sab_range(data_inizio, data_fine))

    print(f"HotelCompare — {len(cfg['competitor'])} competitor, "
          f"{len(sabati)} sabati × {len(TIPI_QUERY)} tipi "
          f"({data_inizio} → {data_fine})\n")

    risultati = []
    from_str  = str(data_inizio).replace("-", "")
    to_str    = str(data_fine).replace("-", "")
    oggi_str  = str(oggi).replace("-", "")
    stem      = f"competitors_from{from_str}_to{to_str}_computed{oggi_str}"
    json_path = OUTPUT_DIR / f"{stem}.json"
    csv_path  = OUTPUT_DIR / f"{stem}.csv"
    txt_path  = OUTPUT_DIR / f"{stem}.txt"

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
            totale = len(sabati) * len(nomi) * len(TIPI_QUERY)
            print(f"=== Fase 2: scraping ({totale} richieste, ~{totale*7//60} min) ===\n")

            n = 0
            for sab in sabati:
                for nome in nomi:
                    for tipo, offset, notti in TIPI_QUERY:
                        checkin = sab + timedelta(days=offset)
                        if checkin < data_inizio:
                            continue
                        n += 1
                        print(f"[{n}/{totale}] {nome} — {tipo} — {checkin} ...",
                              end=" ", flush=True)
                        res = scrapa_notte(page, nome, urls[nome], checkin,
                                           adulti, notti=notti, sab=sab, tipo=tipo)
                        risultati.append(res)
                        print(res["prezzo"] or f"({res['stato']})")

                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump(risultati, f, ensure_ascii=False, indent=2)

                        time.sleep(random.uniform(4.0, 8.0))

        finally:
            browser.close()

    tutti_nomi = list(urls.keys()) + list(manuali.keys())
    sab_uniche = sorted(set(r["settimana"] for r in risultati))

    csv_path.write_text(
        genera_csv(risultati, tutti_nomi, manuali, sab_uniche), encoding="utf-8")
    txt_path.write_text(
        genera_report_testo(risultati, tutti_nomi, manuali, sab_uniche), encoding="utf-8")

    print(f"\nDone.\n  CSV  : {csv_path}\n  Testo: {txt_path}\n")
    print(genera_report_testo(risultati, tutti_nomi, manuali, sab_uniche))


if __name__ == "__main__":
    main()
