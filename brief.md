# AGGIORNAMENTO 30/06/2026 — scraping nel cloud, addio dipendenza dal PC acceso (Treno 2, con Salvatore)

Obiettivo della sessione (richiesta di Salvatore): *"vorrei che facesse tutto da solo, anche a PC
spento/schermo chiuso"*. La verità dura emersa: finché lo scrape gira sul laptop sarà sempre
ostaggio del PC acceso e sveglio — nessun trucco di lock lo aggira. La risposta è il **cloud**.

### Cosa è stato capito
1. **Lock/PID demistificati**: il lock file è un cartello "OCCUPATO"; il PID è la matricola del
   programma; "lock stantio" = cartello su stanza vuota dopo crash. Il fix del 25/06 lo pulisce da solo.
2. **Il PC locale ha solo 3,7 GB RAM** (misurato durante un run): 3 Chromium = ~2,4 GB → satura e
   **swappa** (= "PC compromesso mentre lavoro"). → `max_workers` 3 → **2** (~1,6 GB, niente swap).
3. **GitHub Actions era già configurato ma NON ha MAI scrapato davvero**: i run duravano 46-54s =
   `run_scheduled.py` colpiva una guardia da laptop ed usciva. Il run del 30/06 (dati vecchi >3gg,
   in fascia) è andato oltre le guardie e **è crashato su `FileNotFoundError: notify-send`** — un
   tool desktop assente sul runner, chiamato *prima* di iniziare lo scrape. Quindi la domanda
   "Booking blocca l'IP del datacenter?" non ha MAI avuto risposta.

### Cosa è stato fatto (branch `fix/ci-scraping-reale`, pushato — NON ancora su main)
- commit `080c715`: `max_workers` 2 in competitors.json.
- commit `8a77722`: il workflow CI chiama **`run.py`** invece di `run_scheduled.py`. Motivo: in cloud
  lo scheduler è già la cron di GitHub; le guardie di run_scheduled (notify-send, fascia oraria, lock)
  sono cruft da laptop che lì fa solo danno. run.py fa scraping + push da solo.
- Lanciato il workflow a mano (`workflow_dispatch`) sul branch → **run ID 28445053459**.
- commit `c31cc8a`: cron **ogni 2 giorni** (`0 1 * * 1,3,5,0`) + **jitter** `sleep 0-60min` sui run
  schedulati (non parte mai allo stesso minuto) + timeout 300→360.

### Decisioni di assetto (Treno 2, finali)
- **Un solo branch.** Mai due (locale/cloud): divergono in silenzio. Le differenze stanno nella
  config/ambiente, non nel branch.
- **`max_workers: 2` ovunque.** Il laptop (3,7GB) vuole ≤2; in cloud la velocità di un job notturno
  non presidiato non conta → niente override env (sarebbe complessità inutile). Cloud = 4 vCPU/16GB.
- **Cron locale RIMOSSO** dal crontab del PC (resta solo la riga mattpocock-skills). Niente più
  scheduler automatico sul portatile.
- **Locale = fallback manuale**: `panel.py` / `python run.py` quando Salvatore decide (es. se GitHub
  Actions si rompe). `run_scheduled.py` + lock restano nel repo come rete dormiente, NON smantellati.
- **Cloud = primario**, repo pubblico → minuti Actions illimitati e gratis.

### VERDETTO BOOKING (di fatto risolto)
Il run 28445053459 ha girato **75+ min senza fallire** → Booking **NON blocca** l'IP di GitHub.
(I vecchi crash erano a ~50s: notify-send, non un blocco.) Conferma al 100% = run completato con
prezzi veri in `calendar_merged.json`. Anti-detection pesante (UA/proxy/fingerprint): NON farla ora,
è un problema che non abbiamo; il timing è un segnale debole. Si aggiunge solo SE Booking bloccherà.

### PROSSIMI PASSI
1. **Aspettare la fine del run 28445053459** e verificare prezzi veri nel calendario del branch.
2. **Merge `fix/ci-scraping-reale` su main** → accende lo scheduling automatico cloud (fino al merge
   su main gira ancora il vecchio workflow rotto).
3. Pendente da sessioni precedenti: ancora aperto lo **Scenario C** (parser aggancia numero sbagliato).

Nota: tutto gira in cloud sul branch → PC locale libero, `main` intatto fino al merge.

---

# AGGIORNAMENTO 24/06/2026 — affidabilità della media (Treno 2, con Salvatore)

Sessione di revisione consapevole sui numeri della media. **Tutto mergiato su main (`3caf5e5`) e
pushato**, branch `fix/staleness-15gg` eliminato, 96 test verdi.

### Cosa è stato deciso e fatto
1. **Staleness 30 → 15 giorni** (`SOGLIA_STALENESS_GIORNI`). La media usa solo prezzi visti negli
   ultimi 15gg (~5 cadenze di run da 3gg); i più vecchi restano in tabella come storico con la data.
   Chiarito che *storage* (il merged conserva sempre l'ultimo prezzo per giorno) e *media* (cosa
   conta come prezzo di oggi) sono due piani distinti → doc §5b e §7.
2. **Caption freschezza** sotto la tabella nell'app — segnala che la media è su prezzi ≤15gg
   (segnale di fiducia, non meccanica interna; sfumatura alla regola d'oro del 21/06).
3. **Media sbiadita `°` quando <50% degli hotel ha una doppia** quel giorno
   (`DISPONIBILITA_MIN_MEDIA = 0.50`, soglia RELATIVA). Motivo: nei picchi metà mercato va sold-out
   e la media diventa il "residuo caro" (bias di selezione verso l'alto). Verificato su dati reali:
   sbiadisce solo 26/06 (45%) e 27/06 (27%), lascia pieni i giorni normali (64-100%).
   **Insight di Salvatore:** la distribuzione stagionale NON è usabile per tarare la soglia perché
   confondata dal lead-time (lug/ago oggi al 91% solo perché distanti) → soglia scelta da primo
   principio, non dai dati. Doc §5c.
4. `docs/decisioni-numeri.md` è ora la fonte di verità completa della logica numeri (§0,5b,5c,7).

### DA FARE — prossimi problemi aperti (in ordine)
1. **[radice paura veridicità] Scenario C** — il parser aggancia il numero *sbagliato*, non
   *assente*. Cella piena, plausibile, falsa (è il bug-barrato dell'audit). Non coperto da: occhio
   (non apri l'app ogni giorno), smoke test (becca solo "zero numeri"), spotcheck `--live` (parser
   che controlla sé stesso → cieco sugli errori sistematici). Serve un oracolo *esterno*. Idea
   parziale: alert swap-camera (salto >40% tra run, TODO #1b).
2. **#4 fonte-dati**: CSV/TXT (`run.py:147`, solo-fresco) ≠ app (`calendar_merged.json`, merged) →
   stessa "media" può dare numeri diversi. Unificare su merged.
3. Feature mai fatte: alert prezzi, picker mesi a griglia, multi-tenant.

### Nota sullo spotcheck (emersa stanotte)
La parte `--live` è debole (parser vs sé stesso = MATCH falsamente rassicurante; becca solo LOST).
La parte utile è il default senza rete: genera i link Booking da confrontare a occhio. Valutare di
declassare/togliere `--live`.

Prossimo: attaccare lo **Scenario C** (numeri sbagliati) — radice della paura veridicità.

---

# AGGIORNAMENTO 21/06/2026 — follow-up audit veridicità (Treno 1, notturno)

Salvatore ha richiesto un audit della **logica completa che porta a scrivere un prezzo**
(paura: "i prezzi scritti sono diversi da quelli reali su Booking?"). Lavoro fatto su branch
`audit/veridicita-followup` → **MERGIATO su main (`dd1b514`) e pushato il 22/06**, branch eliminato.
Aggiunti anche: rimozione avviso "esclusi-media" dall'app + `docs/decisioni-numeri.md` (fonte di
verità delle decisioni statistiche/logiche sui numeri). 92 test verdi. **Resta aperto il blocco di
decisioni di prodotto qui sotto ("DA FARE — Treno 2").**

### Premessa git (sua domanda esplicita)
Niente di sospeso: prima di stanotte **un solo branch (`main`), allineato a origin, working tree
pulito, zero commit non mergiati/non pushati**. Il vecchio `fix/veridicita-prezzi` è già mergiato
e rimosso. Tutto il lavoro di stanotte è su `audit/veridicita-followup`, commit locale **non
pushato** — review tua, poi merge.

### Cosa ho FATTO (verità verificate, non sospetti)
1. **Mappa completa della catena prezzo** rivista riga per riga: `build_url → inner_text("body")
   → estrai_prezzo → normalizza_prezzo → scrapa_giorno(1n→7n) → propagazione multi-notte →
   filler → lookup_entry`. Punto di forza inatteso: esiste già una **regression suite con dump
   reali di Booking** (`tests/fixtures/`) — è il guard che catturò il bug del barrato.
2. **Dubbio "filtro `occ != 1` inefficace" → SMENTITO sui dati reali.** Su Booking la tariffa
   1-ospite di una doppia è marcata `N° max persone: 1` (righe 162/181 del dump Capri) → il
   filtro funziona davvero. Falso allarme, chiuso.
3. **BUG TROVATO E FIXATO** (commit `8f88f33`): una riga `Buona colazione per € 21` (>20€, <25
   char) veniva catturata dal `min()` come prezzo candidato **e** mangiava il segnale di board.
   Senza riga "Prezzo attuale" a mascherarla, una doppia solo-camera veniva scritta come
   **`~€ 21` invece di `€ 130≈`** — un prezzo-spazzatura bassissimo. Guard su `KEYWORDS_COLAZIONE`
   + `RE_COLAZIONE_PAGAMENTO` in entrambi i parser. **+2 test di regressione**, le 3 fixture reali
   ancora ok (fix non tocca il percorso sconti).
4. **REFACTOR a comportamento invariato** (commit `ecc5ae9`): `app.media_giorno` e `report._media`
   erano **identiche riga per riga** → rischio che web app e CSV mostrino medie diverse toccandone
   una sola. Estratta `media_competitor()` in `scraper.py` (ritorna `float|None`), usata da
   entrambi. **+5 test. Totale suite: 92 verdi.**

### Divergenze PER DESIGN (legittime, ma vanno sapute — rispondono alla tua paura)
- **Scrivi la doppia più ECONOMICA**, non la prima che vede il cliente.
- **Una cella può avere fino a 30gg ed apparire come attuale** (`SOGLIA_STALENESS_GIORNI=30`).
  È la causa statistica #1 per cui un numero può differire da Booking-ora.
- **Soggiorno multi-notte = €/notte medio imputato** su tutti i giorni coperti (cella marcata `×N`).
- **Colazione STIMATA** (€8/pax) sulle celle `≈`, non letta.

### DA FARE — decisioni che spettano a te (Treno 2)
1. **[il rischio sistemico più grande] Alert anti-silenzio.** Oggi se Booking cambia layout,
   `estrai_prezzo` torna `None` → `non_trovato` → il filler ripiega sullo storico, mostrato come
   attuale fino a 30gg. **Una regressione del parser NON urla, degrada in silenzio.** Proposta
   (NON implementata, le soglie sono scelta tua): sanity check post-run che allarma se un hotel
   passa da "N prezzi" a "0 prezzi", o se `non_trovato` supera una soglia. È il TODO #1b.
2. **Ripensare i 30 giorni di staleness**: troppo lunghi per prezzi? O rendere visibile l'età
   anche sotto soglia (es. sbiadire celle >7gg). Decisione di prodotto.
3. **Spot-check live = l'unica cosa che ti leva il dubbio dallo stomaco.** 3-4 hotel × 2-3 date,
   aprire Booking ora e diffare con `calendar_merged.json`. Posso lanciare query live mirate (non
   il run da 4h), ma **serve il tuo ok perché colpisce Booking**.
4. **Incoerenza fonte-dati CSV/TXT vs web app** (osservata, NON un bug, da decidere): `run.py:147`
   genera i report da `_merge_partials` (**solo il run fresco**), mentre `app.py` legge
   `calendar_merged.json` (**con storico + staleness**). Quindi la MEDIA di un giorno nel CSV può
   differire da quella mostrata nell'app. Va deciso quale fonte vuoi nei report (probabilmente la
   merged, per coerenza con ciò che guardi).

### Prossimo passo
Review del commit `8f88f33` su `audit/veridicita-followup` → se ok, merge su main. Poi decidere
su #1 (alert) e #3 (spot-check live).

---

# AGGIORNAMENTO 16/06/2026 — blocco decisioni implementato (Treno 1)

Salvatore ha ratificato le decisioni aperte; implementate tutte sul branch
`fix/veridicita-prezzi`. **85 test verdi.** Pronto per review + merge.

### Cosa è stato implementato
1. **Semantica cella = "doppia + colazione"** (non più "cheapest"). In `estrai_prezzo`
   la **B&B reale vince sempre**; se l'hotel quel giorno vende solo camera nuda → marker
   `≈` e `normalizza_prezzo` aggiunge la stima colazione (`COLAZIONE_STIMA_PERSONA = €8/
   persona × adulti`, per notte). Verificato sui dump reali: Lido Inn 20/06 ora `€ 329*`
   (= 319 camera + 10 colazione reale), 08/08 `€ 724*` — la B&B reale è più accurata della
   stima, che resta solo fallback.
2. **Singole (`S`) fuori dalla media** (`is_extra_letti` ora include S).
3. **Outlier a 2,5×** la mediana (`SOGLIA_OUTLIER`).
4. **Hotel sotto 30% celle pulite fuori dalla media** (`hotel_in_media`, `COPERTURA_MIN`).
   Audit dati reali: l'unico escluso è **Mariotti** (17,5%); tutti gli altri 64–100%.
5. **Staleness: prezzo >30gg fuori dalla media + declassato a storico in tabella**
   (`prezzo_stantio`, `SOGLIA_STALENESS_GIORNI`). Logica media centralizzata in
   `valore_per_media` (prima duplicata tra app.py e report.py).

### Impatto sui dati attuali (audit calendar_merged.json, 97 giorni)
Media nuova vs vecchia: **+2,5€ medio** (max +32 sul 26/06), sale per la rimozione di
Mariotti. Dopo il prossimo run (parser nuovo) le celle solo-camera/`~` diventeranno
B&B-reale o `≈` → la media salirà ancora un po': è il confronto doppia+colazione voluto.

### Deciso ma NON ancora fatto
- **Alert inter-run** (salto prezzo >X% tra run = swap camera): Salvatore lo vuole,
  "poi ne ragioniamo meglio". Non urgente per il merge → resta nel TODO.

### Prossimo passo
Verifica visiva `streamlit run app.py` → merge su main → run completo col parser nuovo
("runniamo i prezzi con nuove features").

---

# Brief — Audit veridicità prezzi (Treno 1, 10/06/2026)

Branch: `fix/veridicita-prezzi` (2 commit, NON mergiato su main — decidi tu dopo review).
Audit richiesto da Salvatore: "i prezzi visualizzati sono veritieri?". Eseguito con 2 agenti
(analisi dati storici + verifica live su Booking con dump pagina) + review codice completa.

## Verdetto in una riga

I dati erano veri al ~98% come *numeri*, ma con un bias sistematico appena scoperto: **con
sconti attivi il parser catturava il prezzo barrato, non quello effettivo → competitor
sovrastimati del 7-9%**. Rischio concreto: prezzare HNT troppo alto rispetto al mercato reale.

## Cosa è stato verificato live (10/06, dump in tests/fixtures/)

| Caso | Calendario diceva | Prezzo VERO | Causa |
|---|---|---|---|
| Lido Inn 08/08 (3n) | € 252*/notte | € 232/notte solo camera | barrato € 757 vs attuale € 696 + board sbagliata |
| Capri 20/06 (5n) | € 178*/notte (live parser) | € 174/notte B&B | barrato + tariffa "Solo per 1 ospite" contata come doppia |
| Lido Inn 20/06 (1n) | € 319* | € 319 solo camera | board contaminata dalla tariffa successiva |
| Esauriti (5 casi) | ✕ | ✕ | corretto ✓ |
| URL "le-cirque-club" per Lido Inn | — | è davvero Lido Inn ✓ | slug vecchio Booking, falso allarme |

## Fix applicati sul branch (tutti testati, 64 test passano)

1. **Parser riscritto a blocchi-tariffa** (`scraper.py:estrai_prezzo`): usa "Prezzo attuale € Y",
   altrimenti il minimo della tariffa (il barrato è sempre più alto); board legata alla singola
   tariffa; "colazione per € N" = solo camera; tariffe 1-ospite escluse dalle doppie; header
   "Tipologia" nudo riconosciuto; stop a fine tabella. **3 dump reali come fixture di test.**
2. **MEDIA protetta da outlier** (>3× mediana del giorno): il caso reale è Dei Tigli 06/06
   `~€ 888` che gonfiava la MEDIA da €161 a €242. I picchi-evento sincronizzati (26-27/06,
   confermati reali su 5 hotel) sopravvivono perché alzano la mediana.
3. **Scala colori**: i prezzi storici dentro "— (€120 · 30/04)" e "✕ (...)" non vengono più
   trattati come prezzi correnti; T/Q/A con suffisso ×N ora correttamente esclusi.
4. **`run.py`: `timedelta` non importato** → ogni run manuale senza scheduler_state crashava
   (regressione del commit 4d71c1b, mai eseguito da allora).
5. **`carica_manuale_durante_run.py`** cercava i partial col range date di competitors.json,
   ma run.py ora calcola le date a runtime → non avrebbe trovato nulla. Ora glob sui file <48h.
6. **filler**: `data_vista` dello scrape preservata (prima sovrascritta con la data del file)
   e normalizzata ISO (c'erano 2 formati); stesso per `storico_data`.
7. Sidebar: mostra "aggiornato 04/06/2026 (6 giorni fa)" per esteso (il label di età veniva troncato).

## Cosa NON ho toccato (decisioni tue — Treno 2)

1. **Semantica "vince la tariffa più economica"**: prima la solo-camera aveva precedenza sul
   B&B anche se più cara (Capri: avrebbe mostrato € 245/notte solo camera invece di € 174 B&B).
   Ho cambiato in cheapest-wins (il cliente vede la più economica) con marker che dice quale.
   È nel fix 1 ma è una scelta di prodotto: **ratificala o dimmi di tornare a solo>B&B**.
2. **Soglia outlier 3× mediana**: conservativa, da ratificare. La cella €888 resta visibile
   in tabella (potrebbe essere l'ultima camera vera) — esce solo dalla MEDIA.
3. **Mariotti è quasi cieco**: 27% copertura, 0 prezzi puliti (solo ~/T/Q), 73% celle "✕ +
   storico di 3+ settimane". Trend coerente con sell-out reale, non bug. Opzioni: flag UI
   "dato inaffidabile", escluderlo dalla MEDIA, o lasciare.
4. ~~**Cadenza run**~~ → **DECISO 11/06 (Salvatore): ogni 3 giorni.** Implementato:
   `GIORNI_TRA_RUN = 3` in run_scheduled.py, usato anche dal pannello.
5. **Singole S in MEDIA**: abbassano la media fino a −15€ su giorni puntuali (04/07). Escludere?
6. **Off-by-one**: `data_fine 2026-09-21` ma l'ultimo giorno scrapato è il 20/09 (il 21 è
   checkout). Voluto?

## Prossimo passo operativo (aggiornato 11/06)

La notte 10→11/06 il run automatico è partito **dal branch** (repo checked-out su
fix/veridicita-prezzi) e ha usato il parser nuovo: 13/13 hotel, 0 non_trovato, 100% celle
fresche, output coerente con la ground truth verificata a mano (Lido Inn 20/06 → € 319 solo
camera). Il commit dati `ed14b1d` è sul branch, pushato su origin/fix-veridicita-prezzi.

Quindi: **il merge porta su main sia il codice sia i dati già puliti** — non serve più un run
completo dopo. Produzione (main/Streamlit) resta coi dati barrati del 04/06 finché non mergi.
Test pre-merge: `streamlit run app.py` + verifica visiva.

## Domande aperte

- Le 4 decisioni sopra (semantica cheapest-wins, soglia outlier, Mariotti, cadenza).
- Vuoi un alert automatico quando un prezzo salta >X% tra run (sanity inter-run)? L'audit ha
  trovato ~1-2% di celle per run con "swap camera" (es. € 629* → € 214*) che oggi passano in silenzio.
