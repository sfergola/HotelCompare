"""
scraper.py — interazione con Booking.com via Playwright.

Responsabilità:
  - costruire URL di query
  - caricare la pagina e chiudere popup
  - estrarre prezzo e tipo camera dal testo della pagina
  - rilevare stato "esaurito"
  - eseguire singole query (checkin + notti) → prezzo/notte
  - risolvere URL Booking per hotel nuovi
"""

import re
import random
import time
from datetime import date, timedelta
from urllib.parse import quote_plus

from playwright.sync_api import TimeoutError as PlaywrightTimeout


# ── costanti di parsing ──────────────────────────────────────────────────────

EURO_RE = re.compile(r"€\s*(\d+(?:[.,]\d+)?)")

KEYWORDS_MATRIMONIALE = ["matrimoniale", "doppia", "double", "twin"]
KEYWORDS_ECONOMY      = ["economy", "budget", "basic"]
KEYWORDS_SINGOLA      = ["singola", "single"]
KEYWORDS_TRIPLA       = ["tripla", "triple", "3 letti", "tre letti"]
KEYWORDS_QUADRUPLA    = ["quadrupla", "quadruple", "4 letti", "quattro letti"]
KEYWORDS_COLAZIONE    = ["colazione inclusa", "prima colazione", "breakfast inclus",
                         "pernottamento e prima", "b&b", "eccezionale colazione"]
KEYWORDS_SOLO         = ["solo pernottamento", "room only", "senza colazione"]
KEYWORDS_ESAURITO     = ["non ci sono camere disponibili", "no rooms available",
                         "strutture simili", "sold out", "nessuna disponibilità"]

ROOM_START = ["camera", "suite", "appartamento", "stanza", "bungalow", "studio",
              "monolocale", "economy", "double", "twin", "single", "singola",
              "standard", "superior", "deluxe", "classic", "comfort", "junior"]


# ── helper pubblici (usati anche da report.py) ───────────────────────────────

def parse_valore(testo: str) -> float | None:
    """Estrae il valore numerico da una stringa tipo '€ 120*'."""
    m = EURO_RE.search(testo)
    if m:
        try:
            return float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            pass
    return None


def is_extra_letti(prezzo: str) -> bool:
    """True se il prezzo viene da tripla (T) o quadrupla (Q) — esclusi dalle medie."""
    return bool(re.search(r"\d[TQ]\*?$", prezzo))


# ── helper privati ───────────────────────────────────────────────────────────

def _is_economy(nome: str) -> bool:
    return any(k in nome.lower() for k in KEYWORDS_ECONOMY)

def _is_singola(nome: str) -> bool:
    return any(k in nome.lower() for k in KEYWORDS_SINGOLA)

def _is_tripla(nome: str) -> bool:
    return any(k in nome.lower() for k in KEYWORDS_TRIPLA)

def _is_quadrupla(nome: str) -> bool:
    return any(k in nome.lower() for k in KEYWORDS_QUADRUPLA)


# ── interazione con la pagina ────────────────────────────────────────────────

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


def rileva_esaurito(page) -> bool:
    """
    True se Booking mostra esplicitamente nessuna disponibilità.
    Non è affidabile al 100% — va interpretato come indicativo.
    """
    tl = page.inner_text("body").lower()
    return any(k in tl for k in KEYWORDS_ESAURITO)


def estrai_prezzo(page) -> str | None:
    """
    Analizza il testo della pagina e restituisce il prezzo totale del soggiorno trovato.
    La divisione per notti è responsabilità del chiamante (scrapa_query).

    Formato restituito:
      "€ NNN"   = solo camera, matrimoniale standard
      "€ NNN*"  = B&B, matrimoniale standard
      "€ NNN#"  = solo camera, economy double
      "€ NNN#*" = B&B, economy double
      "€ NNNS"  = solo camera, singola
      "€ NNNS*" = B&B, singola
      "~€ NNN"  = matrimoniale trovata, tipo pensione non identificabile
      "€ NNNT"  = tripla (fallback visuale)
      "€ NNNQ"  = quadrupla (fallback estremo)
      None      = non trovato
    """
    testo_pagina = page.inner_text("body")
    righe = [r.strip() for r in testo_pagina.split("\n") if r.strip()]
    risultati: list[tuple[str, float, str | None]] = []

    # Parser 1: layout tabella con header "Tipologia camera"
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
            v = parse_valore(r)
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

    # Parser 2: layout card con "N° max persone"
    if not risultati:
        for i, r in enumerate(righe):
            if "n° max persone" not in r.lower() and "max persone" not in r.lower():
                continue
            for j in range(i + 1, min(i + 6, len(righe))):
                rj = righe[j]
                if rj.lower().startswith("prezzo"):
                    continue
                v = parse_valore(rj)
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

    # board non identificata ma camera giusta trovata
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


def scrapa_query(page, booking_url: str, checkin: date, notti: int, adulti: int) -> dict:
    """
    Esegue una singola richiesta Booking per checkin + notti.

    Returns:
        {"prezzo": str|None, "stato": "ok"|"non_trovato"|"esaurito"|"errore:..."}
        Il prezzo è già normalizzato per notte (totale / notti).
    """
    checkout = checkin + timedelta(days=notti)
    url = build_url(booking_url, checkin, checkout, adulti)
    try:
        page.goto(url, wait_until="networkidle", timeout=40000)
        time.sleep(random.uniform(2.5, 4.5))
        chiudi_popup(page)
        page.evaluate("window.scrollTo(0, 1200)")
        time.sleep(1.5)

        if rileva_esaurito(page):
            return {"prezzo": None, "stato": "esaurito"}

        prezzo = estrai_prezzo(page)
        if prezzo and notti > 1:
            v = parse_valore(prezzo)
            if v:
                prefix    = "~" if prezzo.startswith("~") else ""
                m_sfx     = re.match(r"~?€\s*\d+(.*)", prezzo)
                suffix    = m_sfx.group(1) if m_sfx else ""
                per_notte = int(v / notti)
                prezzo    = f"{prefix}€ {per_notte}{suffix}" if per_notte >= 25 else None

        return {"prezzo": prezzo, "stato": "ok" if prezzo else "non_trovato"}
    except Exception as e:
        return {"prezzo": None, "stato": f"errore:{str(e)[:60]}"}


# ── risoluzione URL ──────────────────────────────────────────────────────────

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


def risolvi_urls(page, cfg: dict) -> tuple[dict[str, str], bool]:
    """
    Restituisce (urls, aggiornato).
    Se aggiornato=True, il chiamante deve salvare cfg su disco.
    """
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
    return urls, aggiornato
