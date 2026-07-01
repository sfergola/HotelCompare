# HotelCompare — Istruzioni per l'agente AI

## Cos'è questo progetto
Scraper prezzi competitor su Booking.com per Hotel Nuovo Tirreno (Lido di Camaiore).
Genera un calendario prezzi giornaliero per ogni hotel competitor, visualizzabile via web app Streamlit.

## Architettura

**Primario = cloud.** Lo scraping gira in automatico su **GitHub Actions** (`.github/workflows/scraping.yml`),
~ogni 2 giorni, indipendente dal PC. Il locale (`run.py`/`panel.py`) è solo fallback manuale.

```
competitors.json (max_workers=2 locale; in cloud sovrascritto a 4 via env MAX_WORKERS)
    ↓
run.py               — entry point, orchestrazione (usato sia in locale sia dal workflow cloud)
    ├── Fase 1: scraper.risolvi_urls()  (1 browser)
    ├── Fase 2: algorithm.scrapa_hotel_worker() × N  (ProcessPoolExecutor)
    │           ogni worker ha il proprio browser Playwright
    │           scrive output/partial_<hotel>_..._inprogress.json → _computed.json
    ├── Fase 3: merge partial → calendar_from..._computed<oggi>.json
    ├── Fase 4: filler.esegui_filler()
    ├── Fase 5: report.genera_csv() + report.genera_report_testo()
    └── Fase 6: git_utils.git_push_calendar() → commit calendar_merged.json + push
                (esce 1 se la push fallisce → run rosso, niente dati persi in silenzio)
filler.py            — merge di tutti i run storici → calendar_merged.json
                       ogni entry ottiene data_vista (quando è stato visto il prezzo)
report.py            — genera CSV e TXT dal calendario
app.py               — visualizzazione Streamlit (legge calendar_merged.json di default)
git_utils.py         — push resiliente: pull --rebase + 3 retry, torna bool (branch auto)
.github/workflows/scraping.yml — SCRAPING CLOUD (primario): cron Lun/Mer/Ven/Sab 01:00 UTC
                       + jitter 0-60min, MAX_WORKERS=4, timeout 360, backup artifact
panel.py             — pannello Tkinter: stato, log live, Avvia/Stop (fallback manuale locale)
                       lancia da GNOME launcher (Super → "HotelCompare")
run_scheduled.py     — scheduler DA LAPTOP, ora dormiente (cron locale rimosso): guard 3gg,
                       fascia 19:30–09:00, lock file con PID. Tenuto come rete di riserva
carica_manuale_durante_run.py — push parziale durante run (fallback locale)
```

> Oracle Cloud: **abbandonato** (VM mai creata, "Out of host capacity"). `terraform/main.tf` e gli
> `scripts/oracle_*` restano solo come storico — non usati.

## File principali

| File | Responsabilità |
|---|---|
| `scraper.py` | Playwright + parsing prezzi + `lookup_entry`, `fmt_storico` |
| `algorithm.py` | algoritmo greedy per-giorno + checkpoint |
| `report.py` | genera CSV e TXT dal calendario |
| `filler.py` | riempie date mancanti con prezzi storici dai run precedenti |
| `run.py` | entry point: risolve URL → scrapa → filler → report → push. Legge `MAX_WORKERS` da env (cloud) |
| `.github/workflows/scraping.yml` | **scraping cloud PRIMARIO**: cron ~ogni 2gg + jitter, MAX_WORKERS=4, backup artifact |
| `git_utils.py` | push resiliente (pull --rebase + 3 retry, torna bool) — condiviso |
| `panel.py` | pannello Tkinter: fallback manuale locale (launcher GNOME) |
| `run_scheduled.py` | scheduler da laptop, **dormiente** (cron locale rimosso): guard 3gg, fascia 19:30–09:00, lock PID |
| `carica_manuale_durante_run.py` | push parziale mentre run.py è ancora in corso (fallback locale) |
| `app.py` | visualizzazione Streamlit con tabella colorata |
| `competitors.json` | config statica: hotel, URL, max_workers — non modificata a runtime |
| `tests/` | unit test funzioni pure (pytest, no rete, no browser) |
| `scripts/spotcheck.py` | verifica live ("contract test" manuale): confronta prezzo salvato vs live su Booking per celle-campione, verdetto MATCH/DRIFT/⚠LOST/esaurito |
| `terraform/main.tf`, `scripts/oracle_*` | storico Oracle Cloud — **abbandonato**, non usati |

## Come avviare

Lo scraping in produzione gira **da solo in cloud** (GitHub Actions). In locale serve solo per
run manuali di riserva:

```bash
source venv/bin/activate
python run.py                  # scraping + report (manuale)
streamlit run app.py           # web app locale
```

Per lanciare lo scraping cloud a mano: `gh workflow run scraping.yml` (o dal tab Actions).

## Configurazione date
In `competitors.json`:
- `data_inizio` — primo giorno da scrapare (controllo manuale)
- `data_fine` — ultimo giorno; in cloud è la data effettiva di fine scraping (di norma = `stagione_fine`)
- `stagione_fine` — fine stagione fissa (non toccare)
- In cloud `run.py` non trova `scheduler_state.json` → usa il fallback: `data_inizio=oggi` (include
  il same-day, dato in più), `data_fine=competitors.json["data_fine"]`. Per run parziali manuali:
  cambia le date, poi ripristina.
- `run_scheduled.py` (dormiente) impostava `data_inizio=domani`, `data_fine=stagione_fine` via
  `scheduler_state.json` — vale solo se lo riattivi come fallback locale.

## Logica algoritmo per-giorno
Per ogni hotel × giorno:
1. Prova soggiorni 1n, 2n, ..., 7n in ordine
2. Commit sulla prima **doppia/singola** trovata — prezzo diviso per le notti
3. Tripla/quadrupla usate come fallback visuale (escluse dalle medie)
4. I giorni successivi coperti dallo stesso soggiorno vengono saltati
5. Il risultato include `notti` (durata del soggiorno che ha prodotto il prezzo)

## Checkpoint e ripresa
I dati in corso vengono salvati in `output/*_inprogress.json`.
Al prossimo `run.py`, i giorni già scrappati vengono saltati automaticamente.

## Legenda celle

Obiettivo del confronto: **doppia + colazione**. La B&B reale vince sempre; se l'hotel
quel giorno vende solo la camera nuda, si stima la colazione (marker `≈`).

| Cella | Significato |
|---|---|
| `€ 120*` | B&B, matrimoniale standard (doppia + colazione, prezzo reale) |
| `€ 136≈` | solo camera + stima colazione (`COLAZIONE_STIMA_PERSONA`=€8/persona) |
| `€ 120×7` | prezzo da soggiorno minimo 7 notti |
| `€ 120#*` | B&B economy double (`#≈` = economy + stima colazione) |
| `~€ 120` | matrimoniale trovata, tipo pensione non identificabile |
| `€ 120S` | singola (**esclusa dalle medie**) |
| `€ 120T` | tripla (fallback — esclusa dalle medie) |
| `€ 120Q` | quadrupla (fallback estremo — esclusa dalle medie) |
| `€ 120A` | appartamento (fallback — escluso dalle medie) |
| `— (€120* · 30/04)` | non trovato oggi (o prezzo >15gg), ultimo prezzo noto dal 30/04 |
| `✕ (€120* · 30/04)` | esaurito oggi, ultimo prezzo noto dal 30/04 |
| `✕` | esaurito (nessun prezzo storico disponibile) |
| `—` | non trovato (nessun prezzo storico disponibile) |

## Regole della MEDIA (competitor)
Tutte le soglie vivono in `scraper.py` (`COLAZIONE_STIMA_PERSONA`, `SOGLIA_OUTLIER`,
`SOGLIA_STALENESS_GIORNI`, `COPERTURA_MIN`). Entra nella media solo una **doppia
confrontabile**: esclusi singole/triple/quadruple/appartamenti (`is_extra_letti`),
prezzi visti >15gg fa (`prezzo_stantio` → declassati a storico anche in tabella),
outlier oltre 2,5× la mediana del giorno, e gli hotel sotto il 30% di celle pulite
(`hotel_in_media` — es. Mariotti, quasi sempre sold-out). Logica condivisa tra
`app.py` e `report.py` via `valore_per_media` / `media_competitor`.

> **Prima di toccare una qualsiasi soglia o regola che cambia i numeri mostrati, leggi
> `docs/decisioni-numeri.md`** — raccoglie tutte le decisioni statistiche/logiche (cosa si
> confronta, stima colazione, priorità camere, esclusioni dalla media) con il *perché* e il
> *quando riconsiderarle*. È la fonte di verità per la logica dei numeri.

## Aggiungere un competitor
In `competitors.json`, aggiungi nella lista `competitor`:
```json
{ "nome": "Hotel Esempio", "citta": "Lido di Camaiore" }
```
Al primo run lo scraper cerca l'URL su Booking automaticamente.
Se non è su Booking:
```json
{ "nome": "Hotel Esempio", "nota": "verifica manuale su hotelesempio.it" }
```
Per l'hotel di riferimento (non incluso nelle medie):
```json
{ "nome": "Hotel Nuovo Tirreno", "citta": "Lido di Camaiore", "riferimento": true }
```

## Workflow branch

**Regola:** non lavorare mai direttamente su `main`. Ogni modifica va su un branch dedicato.

```
main          → produzione stabile (Streamlit Cloud lo legge)
feature/*     → nuova funzionalità
fix/*         → bug fix
refactor/*    → pulizia codice senza cambiare comportamento
```

**Flusso standard:**
1. `git checkout -b feature/nome-feature`
2. lavora, committa sul branch
3. testa end-to-end (almeno: `streamlit run app.py` e verifica visiva)
4. solo se tutto ok → `git checkout main && git merge feature/nome-feature && git push`

**Eccezione:** l'aggiornamento dati automatico (il workflow cloud che lancia `run.py`) scrive
direttamente su main — è il suo scopo e non tocca il codice.

## Deploy
- Web app: Streamlit Community Cloud → branch `main`, file `app.py` (+ `.streamlit/config.toml`, tema chiaro)
- Scraping automatico: **GitHub Actions in cloud** (`.github/workflows/scraping.yml`), ~ogni 2 giorni
  (Lun/Mer/Ven/Sab 01:00 UTC + jitter), MAX_WORKERS=4, push resiliente + backup artifact. Repo
  pubblico → minuti Actions gratis e illimitati. Nessun PC acceso richiesto.
- Aggiornamento manuale: `python run.py` (o `panel.py`) in locale → commit + push. Rete di riserva
  se le Actions si fermano.
- `output/*.json` gitignored tranne `calendar_merged.json` (unico file dati committato)

## Parallelismo
`competitors.json` → campo `max_workers` (default locale: **2**, sicuro sui 3,7GB del PC).
In cloud è sovrascritto a **4** via env `MAX_WORKERS` nel workflow (runner = 4 vCPU): serve per stare
sotto il **tetto rigido di 6h** dei runner GitHub (a 2 worker sforava e veniva killato).
Ogni hotel ha il proprio processo Playwright. Partial files salvati in `output/partial_<hotel>_...json`.
Durata reale: ~2h35m a 4 worker (cloud, 13 hotel); ~6h a 3 worker (laptop).
