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

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:
    PlaywrightTimeout = Exception


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
KEYWORDS_ESAURITO     = ["non ci sono camere disponibili per le date selezionate",
                         "no rooms available for your dates",
                         "sold out",
                         "nessuna disponibilità per le date selezionate",
                         "non abbiamo disponibilità per questa struttura"]

ROOM_START = ["camera", "suite", "appartamento", "stanza", "bungalow", "studio",
              "monolocale", "economy", "double", "twin", "single", "singola",
              "standard", "superior", "deluxe", "classic", "comfort", "junior"]

# fine della tabella camere — oltre questi marker i prezzi appartengono ad altre sezioni
STOP_MARKERS = ["recensioni degli ospiti", "domande frequenti", "regole della struttura"]

RE_OCCUPANZA           = re.compile(r"n° max persone[^\d]*(\d+)")
RE_PREZZO_ATTUALE      = re.compile(r"prezzo attuale\s*€\s*([\d.,]+)")
RE_SOTTOCAMERA         = re.compile(r"camera \d+\s*:")
RE_COLAZIONE_PAGAMENTO = re.compile(r"colazione\s+(?:a pagamento|(?:a|per)\s*€)")


# ── soglie della MEDIA (parametri di dominio, modificabili) ───────────────────
# Tutto ciò che decide quali prezzi entrano nella media dei competitor vive qui,
# non sparso nella logica: cambiare un confronto = cambiare un numero.

COLAZIONE_STIMA_PERSONA = 8     # €/persona: stima aggiunta alla solo-camera per
                                # confrontarla con le doppie-colazione (marker ≈)
SOGLIA_STALENESS_GIORNI = 30    # un prezzo visto oltre N giorni fa esce dalla media
SOGLIA_OUTLIER          = 2.5   # un prezzo oltre N× la mediana del giorno esce dalla media
COPERTURA_MIN           = 0.30  # un hotel sotto questa quota di celle pulite esce dalla media


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


def filtra_prezzi_anomali(valori: list[float]) -> list[float]:
    """Esclude dalla media i valori oltre SOGLIA_OUTLIER× la mediana del giorno.

    Protegge la MEDIA da prezzi anomali (es. ultima camera rimasta a €888
    quando gli altri hotel stanno a €120-150). I picchi reali sincronizzati
    tra più hotel (weekend-evento) alzano la mediana e quindi sopravvivono.
    Con meno di 4 valori non filtra: troppo pochi per distinguere un outlier.
    """
    if len(valori) < 4:
        return valori
    ordinati = sorted(valori)
    n = len(ordinati)
    mediana = ordinati[n // 2] if n % 2 else (ordinati[n // 2 - 1] + ordinati[n // 2]) / 2
    return [v for v in valori if v <= SOGLIA_OUTLIER * mediana]


def is_extra_letti(prezzo: str) -> bool:
    """True se il prezzo non è una doppia confrontabile: singola (S), tripla (T),
    quadrupla (Q), appartamento (A) — tutti esclusi dalle medie.

    Gestisce il marker board (* B&B reale, ≈ colazione stimata) e il suffisso
    minimum stay: "€ 120T×3", "€ 120S*", "€ 136S≈".
    """
    return bool(re.search(r"\d[STQA][*≈]?(?:×\d+)?$", prezzo))


def parse_data_vista(dv: str) -> "date | None":
    """Interpreta una data_vista/storico_data in uno dei due formati storici
    ('20260506' o '2026-05-06'). Ritorna None se non riconosciuta."""
    if not dv:
        return None
    try:
        if len(dv) == 8 and dv.isdigit():
            return date(int(dv[:4]), int(dv[4:6]), int(dv[6:8]))
        return date.fromisoformat(dv[:10])
    except (ValueError, IndexError):
        return None


def prezzo_stantio(entry: dict, oggi: "date | None") -> bool:
    """True se l'entry ha un prezzo ma è stato visto oltre SOGLIA_STALENESS_GIORNI
    giorni fa: con la pipeline ferma il dato non è più affidabile come prezzo corrente.
    Con oggi=None la staleness non viene valutata (retro-compatibile)."""
    if oggi is None:
        return False
    d = parse_data_vista(entry.get("data_vista", ""))
    return d is not None and (oggi - d).days > SOGLIA_STALENESS_GIORNI


def valore_per_media(entry: dict, oggi: "date | None" = None) -> "float | None":
    """Ritorna il prezzo dell'entry se è valido per la MEDIA, altrimenti None.

    Esclude: entry senza prezzo, non-doppie (S/T/Q/A via is_extra_letti) e prezzi
    stantii (>SOGLIA_STALENESS_GIORNI). L'outlier 2,5× è applicato a valle, sul
    giorno intero, da filtra_prezzi_anomali."""
    prezzo = entry.get("prezzo")
    if not prezzo or is_extra_letti(prezzo) or prezzo_stantio(entry, oggi):
        return None
    return parse_valore(prezzo)


def hotel_in_media(calendario: dict, nome: str, giorni: list[str],
                   oggi: "date | None" = None) -> bool:
    """True se l'hotel ha celle pulite a sufficienza (≥ COPERTURA_MIN) per
    contribuire a una media sensata. Sotto soglia viene escluso: un hotel quasi
    sempre sold-out (pochi dati, per lo più storici/sporchi, es. Mariotti) avrebbe
    rari valori che distorcerebbero la media senza rappresentare il mercato."""
    if not giorni:
        return False
    pulite = sum(1 for g in giorni
                 if (e := calendario.get(nome, {}).get(g)) and valore_per_media(e, oggi) is not None)
    return pulite >= COPERTURA_MIN * len(giorni)


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

    Restituisce il prezzo TOTALE del soggiorno; la stima colazione sulle celle ≈
    viene aggiunta da normalizza_prezzo (che conosce notti e adulti).

    Formato restituito:
      "€ NNN*"  = B&B, matrimoniale standard (doppia + colazione, prezzo reale)
      "€ NNN≈"  = solo camera, matrimoniale standard (→ +stima colazione)
      "€ NNN#*" = B&B, economy double      ("€ NNN#≈" = economy solo camera)
      "€ NNNS*" = B&B, singola              ("€ NNNS≈" = singola solo camera)
      "~€ NNN"  = matrimoniale trovata, tipo pensione non identificabile
      "€ NNNT"  = tripla (fallback visuale)
      "€ NNNQ"  = quadrupla (fallback estremo)
      None      = non trovato
    """
    testo_pagina = page.inner_text("body")
    righe = [r.strip() for r in testo_pagina.split("\n") if r.strip()]
    # (camera, prezzo, board, sezione_appartamenti, occupanza)
    risultati: list[tuple[str, float, str | None, bool, int | None]] = []

    # Parser 1: layout tabella con header "Tipologia ..." ("camera", "appartamento",
    # o il solo "Tipologia" usato da alcune strutture)
    start = None
    sezione_appart = False
    for i, r in enumerate(righe):
        rl = r.lower()
        if rl.startswith("tipologia") or "tipo di camera" in rl:
            start = i
            sezione_appart = "appartament" in rl or "alloggio" in rl
            break

    if start is not None:
        camera: str | None = None
        occupanza: int | None = None
        prezzo: float | None = None   # minimo delle righe-prezzo brevi della tariffa
        attuale: float | None = None  # prezzo esplicito "Prezzo attuale € Y" (post-sconto)

        def chiudi_tariffa(board: str | None):
            nonlocal prezzo, attuale
            p = attuale if attuale is not None else prezzo
            if camera and p:
                risultati.append((camera, p, board, sezione_appart, occupanza))
            prezzo = attuale = None

        for r in righe[start: start + 400]:
            rl = r.lower()

            if any(m in rl for m in STOP_MARKERS):
                break

            if (any(rl.startswith(k) for k in ROOM_START)
                    and 10 < len(r) < 90 and not EURO_RE.search(r)
                    and "recension" not in rl
                    and not RE_SOTTOCAMERA.match(rl)):
                chiudi_tariffa(None)
                camera = r
                occupanza = None
                continue

            m_occ = RE_OCCUPANZA.match(rl)
            if m_occ:
                chiudi_tariffa(None)
                occupanza = int(m_occ.group(1))
                continue

            # "Prezzo iniziale € X Prezzo attuale € Y" — Y è il prezzo vero post-sconto
            m_att = RE_PREZZO_ATTUALE.search(rl)
            if m_att:
                v = parse_valore(f"€ {m_att.group(1)}")
                if v and v > 20:
                    attuale = v
                continue

            v = parse_valore(r)
            if v and v > 20 and len(r) < 25:
                # con sconto attivo il barrato (più alto) precede l'attuale: si tiene il minimo
                prezzo = v if prezzo is None else min(prezzo, v)
                continue

            if (prezzo is not None or attuale is not None) and camera:
                # "colazione per € 10" = a pagamento → solo camera; va controllato
                # prima delle keyword di inclusione ("eccezionale colazione per € 12")
                if RE_COLAZIONE_PAGAMENTO.search(rl) or any(k in rl for k in KEYWORDS_SOLO):
                    chiudi_tariffa("solo")
                elif any(k in rl for k in KEYWORDS_COLAZIONE):
                    chiudi_tariffa("bb")
        chiudi_tariffa(None)

    # Parser 2: layout card con "N° max persone"
    if not risultati:
        for i, r in enumerate(righe):
            rl = r.lower()
            if "max persone" not in rl:
                continue
            m_occ = RE_OCCUPANZA.search(rl)
            occupanza = int(m_occ.group(1)) if m_occ else None

            # blocco tariffa: dalle righe dopo "max persone" fino al blocco successivo
            fine = min(i + 12, len(righe))
            for j in range(i + 1, min(i + 12, len(righe))):
                if "max persone" in righe[j].lower():
                    fine = j
                    break

            prezzo_blocco: float | None = None
            board: str | None = None
            for j in range(i + 1, fine):
                rj  = righe[j]
                rjl = rj.lower()
                m_att = RE_PREZZO_ATTUALE.search(rjl)
                if m_att:
                    v = parse_valore(f"€ {m_att.group(1)}")
                    if v and v > 20:
                        prezzo_blocco = v
                    continue
                if rjl.startswith("prezzo"):
                    continue
                v = parse_valore(rj)
                if v and v > 20 and len(rj) < 25:
                    prezzo_blocco = v if prezzo_blocco is None else min(prezzo_blocco, v)
                    continue
                if board is None:
                    if RE_COLAZIONE_PAGAMENTO.search(rjl) or any(kw in rjl for kw in KEYWORDS_SOLO):
                        board = "solo"
                    elif any(kw in rjl for kw in KEYWORDS_COLAZIONE):
                        board = "bb"
            if not prezzo_blocco:
                continue

            camera = "camera"
            for m_idx in range(i - 1, max(i - 45, -1), -1):
                rm  = righe[m_idx]
                rml = rm.lower()
                if (any(rml.startswith(k) for k in ROOM_START)
                        and 10 < len(rm) < 90 and not EURO_RE.search(rm)
                        and not RE_SOTTOCAMERA.match(rml)):
                    camera = rm
                    break
            risultati.append((camera, prezzo_blocco, board, False, occupanza))

    if not risultati:
        return None

    normali      = [(n, p, b, occ) for n, p, b, a, occ in risultati if not a]
    appartamenti = [(n, p, b) for n, p, b, a, occ in risultati if a]

    # le tariffe per 1 ospite in camera doppia non sono il prezzo della doppia
    matrimoniali = [(n, p, b) for n, p, b, occ in normali
                    if any(k in n.lower() for k in KEYWORDS_MATRIMONIALE) and occ != 1]
    singole      = [(n, p, b) for n, p, b, occ in normali
                    if _is_singola(n) and not any(k in n.lower() for k in KEYWORDS_MATRIMONIALE)]

    standard = [(n, p, b) for n, p, b in matrimoniali if not _is_economy(n)]
    economy  = [(n, p, b) for n, p, b in matrimoniali if _is_economy(n)]

    for gruppo, marker in [(standard, ""), (economy, "#"), (singole, "S")]:
        # confronto omogeneo "doppia + colazione": la B&B reale vince sempre (è la
        # cosa che vogliamo confrontare). Se l'hotel quel giorno vende solo la camera
        # nuda, la marchiamo ≈ → normalizza_prezzo aggiunge la stima colazione, così
        # non confrontiamo solo-camera con B&B (mele con pere).
        bb   = [p for n, p, b in gruppo if b == "bb"]
        solo = [p for n, p, b in gruppo if b == "solo"]
        if bb:
            return f"€ {int(min(bb))}{marker}*"
        if solo:
            return f"€ {int(min(solo))}{marker}≈"

    # board non identificata ma camera giusta trovata
    for gruppo, marker in [(standard, ""), (economy, "#"), (singole, "S")]:
        none_p = [p for n, p, b in gruppo if b is None]
        if none_p:
            return f"~€ {int(min(none_p))}{marker}"

    triple    = [(n, p, b) for n, p, b, occ in normali if _is_tripla(n)]
    quadruple = [(n, p, b) for n, p, b, occ in normali if _is_quadrupla(n)]

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

    # appartamento (fallback estremo — escluso dalle medie)
    if appartamenti:
        any_p = [p for n, p, b in appartamenti]
        bb_p  = [p for n, p, b in appartamenti if b == "bb"]
        if bb_p:
            return f"€ {int(min(bb_p))}A*"
        return f"€ {int(min(any_p))}A"

    return None


def normalizza_prezzo(prezzo: str, notti: int, adulti: int) -> "str | None":
    """Trasforma il prezzo-totale-soggiorno di estrai_prezzo in prezzo/notte e,
    sulle celle solo-camera (marker ≈), aggiunge la stima colazione
    (COLAZIONE_STIMA_PERSONA × adulti, per notte). Ritorna None sotto €25/notte
    (prezzo implausibile per una doppia)."""
    v = parse_valore(prezzo)
    if v is None:
        return None
    prefix = "~" if prezzo.startswith("~") else ""
    m_sfx  = re.match(r"~?€\s*[\d.,]+(.*)", prezzo)
    suffix = m_sfx.group(1) if m_sfx else ""
    per_notte = v / notti if notti else v
    if "≈" in suffix:
        per_notte += COLAZIONE_STIMA_PERSONA * adulti
    per_notte = int(per_notte)
    if per_notte < 25:
        return None
    return f"{prefix}€ {per_notte}{suffix}"


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
        if prezzo:
            prezzo = normalizza_prezzo(prezzo, notti, adulti)

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


# ── helpers condivisi tra report.py e app.py ─────────────────────────────────

def fmt_storico(entry: dict) -> str:
    """Formatta il prezzo storico come ' (€120* · 30/04)'."""
    sp = entry.get("storico_prezzo")
    if not sp:
        return ""
    sn = entry.get("storico_notti", 1)
    sd = entry.get("storico_data", "")
    sfx = f"×{sn}" if sn > 1 else ""
    d_fmt = sd[8:10] + "/" + sd[5:7] if len(sd) == 10 else sd
    return f" ({sp}{sfx} · {d_fmt})"


def lookup_entry(calendario: dict, nome: str, giorno: str,
                 oggi: "date | None" = None) -> tuple[str, int]:
    """
    Ritorna (cella_testo, notti) per un hotel e giorno.
    cella_testo include ×N se minimum stay > 1 e, se assente il prezzo corrente,
    il prezzo storico in formato: — (€120* · 30/04).

    Se oggi è passato e il prezzo è stantio (>SOGLIA_STALENESS_GIORNI), viene
    declassato allo stesso formato storico: esce dalla media e in tabella si vede
    che è un dato vecchio, non un prezzo corrente.
    """
    entry = calendario.get(nome, {}).get(giorno)
    if not entry:
        return "—", 0
    prezzo = entry.get("prezzo")
    notti  = entry.get("notti") or 1
    stato  = entry.get("stato", "non_trovato")
    if prezzo and not prezzo_stantio(entry, oggi):
        sfx = f"×{notti}" if notti > 1 else ""
        return f"{prezzo}{sfx}", notti
    if prezzo:  # presente ma stantio → mostralo come storico
        sfx = f"×{notti}" if notti > 1 else ""
        d = parse_data_vista(entry.get("data_vista", ""))
        d_fmt = f"{d.day:02d}/{d.month:02d}" if d else ""
        return f"— ({prezzo}{sfx} · {d_fmt})", 0
    storico = fmt_storico(entry)
    if stato == "esaurito":
        return f"✕{storico}", 0
    return f"—{storico}", 0
