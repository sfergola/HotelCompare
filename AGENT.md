# HotelCompare — Istruzioni per l'agente AI

## Cos'è questo progetto
Scraper prezzi competitor su Booking.com per Hotel Nuovo Tirreno (Lido di Camaiore).
Genera un calendario prezzi giornaliero per ogni hotel competitor, visualizzabile via web app Streamlit.

## Architettura

```
competitors.json (max_workers=3)
    ↓
run.py               — entry point, orchestrazione
    ├── Fase 1: scraper.risolvi_urls()  (1 browser)
    ├── Fase 2: algorithm.scrapa_hotel_worker() × N  (ProcessPoolExecutor)
    │           ogni worker ha il proprio browser Playwright
    │           scrive output/partial_<hotel>_..._inprogress.json → _computed.json
    ├── Fase 3: merge partial → calendar_from..._computed<oggi>.json
    ├── Fase 4: filler.esegui_filler()
    ├── Fase 5: report.genera_csv() + report.genera_report_testo()
    └── Fase 6: git_utils.git_push_calendar() → commit calendar_merged.json + push
filler.py            — merge di tutti i run storici → calendar_merged.json
                       ogni entry ottiene data_vista (quando è stato visto il prezzo)
report.py            — genera CSV e TXT dal calendario
app.py               — visualizzazione Streamlit (legge calendar_merged.json di default)
git_utils.py         — git commit + push condiviso (branch rilevato automaticamente)
run_scheduled.py     — avvio automatico notturno (cron ogni 30 min)
                       condizione: git log calendar_merged.json > 3 giorni fa (GIORNI_TRA_RUN)
                       fascia: 19:30–09:00 (fuori fascia: esce silenziosamente)
                       lock file output/run_in_progress.lock contiene PID di run.py
panel.py             — pannello Tkinter: stato, log live, Avvia/Stop
                       lancia da GNOME launcher (Super → "HotelCompare")
                       avvio manuale ignora la condizione 3 giorni
carica_manuale_durante_run.py — push parziale durante run: legge i partial già pronti,
                       aggiorna calendar_merged.json e fa commit+push senza aspettare il run completo
terraform/main.tf    — config Terraform VM Oracle ARM (tracciato nel repo)
.github/workflows/scraping.yml — GitHub Actions piano B (Lun/Mar/Mer 02:00 UTC)
```

## File principali

| File | Responsabilità |
|---|---|
| `scraper.py` | Playwright + parsing prezzi + `lookup_entry`, `fmt_storico` |
| `algorithm.py` | algoritmo greedy per-giorno + checkpoint |
| `report.py` | genera CSV e TXT dal calendario |
| `filler.py` | riempie date mancanti con prezzi storici dai run precedenti |
| `run.py` | entry point: risolve URL → scrapa → filler → report → auto-push |
| `run_scheduled.py` | avvio automatico notturno: 3gg (GIORNI_TRA_RUN), fascia 19:30–09:00, lock file con PID |
| `panel.py` | pannello Tkinter: stato, log live, Avvia/Stop (launcher GNOME) |
| `carica_manuale_durante_run.py` | push parziale mentre run.py è ancora in corso |
| `app.py` | visualizzazione Streamlit con tabella colorata |
| `git_utils.py` | git push condiviso tra run.py, run_scheduled.py, panel.py |
| `competitors.json` | config statica: hotel, URL, max_workers — non modificata a runtime |
| `terraform/main.tf` | Terraform VM Oracle ARM — tracciato nel repo |
| `.github/workflows/scraping.yml` | GitHub Actions piano B |
| `tests/` | unit test funzioni pure (pytest, no rete, no browser) |
| `scripts/retry_stack_apply.sh` | retry VM Oracle: ruota AD-1/2/3, gira in locale |
| `scripts/oracle_keepalive.sh` | keepalive da installare sulla VM Oracle |

## Come avviare

```bash
source venv/bin/activate
python run.py                  # scraping + report
streamlit run app.py           # web app locale
python run_scheduled.py        # run automatico (con guard 3 giorni)
```

**Setup cron (una tantum per macchina):**
```bash
(crontab -l 2>/dev/null; echo "@reboot /home/salvatore/Projects/HotelCompare/venv/bin/python run_scheduled.py >> /home/salvatore/Projects/HotelCompare/output/run_scheduled.log 2>&1") | crontab -
```

## Configurazione date
In `competitors.json`:
- `data_inizio` — primo giorno da scrapare (controllo manuale)
- `data_fine` — ultimo giorno (controllo manuale — cambialo per run parziali)
- `stagione_fine` — fine stagione fissa, usata dallo scheduler automatico (non toccare)
- `run_scheduled.py` imposta `data_inizio=domani` e `data_fine=stagione_fine` ad ogni run automatico
  → dopo un run automatico, `data_fine` torna a `stagione_fine`
  → per run parziali manuali: cambia `data_inizio`/`data_fine`, poi ripristina se necessario

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
| `— (€120* · 30/04)` | non trovato oggi (o prezzo >30gg), ultimo prezzo noto dal 30/04 |
| `✕ (€120* · 30/04)` | esaurito oggi, ultimo prezzo noto dal 30/04 |
| `✕` | esaurito (nessun prezzo storico disponibile) |
| `—` | non trovato (nessun prezzo storico disponibile) |

## Regole della MEDIA (competitor)
Tutte le soglie vivono in `scraper.py` (`COLAZIONE_STIMA_PERSONA`, `SOGLIA_OUTLIER`,
`SOGLIA_STALENESS_GIORNI`, `COPERTURA_MIN`). Entra nella media solo una **doppia
confrontabile**: esclusi singole/triple/quadruple/appartamenti (`is_extra_letti`),
prezzi visti >30gg fa (`prezzo_stantio` → declassati a storico anche in tabella),
outlier oltre 2,5× la mediana del giorno, e gli hotel sotto il 30% di celle pulite
(`hotel_in_media` — es. Mariotti, quasi sempre sold-out). Logica condivisa tra
`app.py` e `report.py` via `valore_per_media`.

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

**Eccezione:** aggiornamenti dati automatici (`run.py`, `run_scheduled.py`) scrivono direttamente su main — è il loro scopo e non toccano il codice.

## Deploy
- Web app: Streamlit Community Cloud → branch `main`, file `app.py`
- Aggiornamento dati: `python run.py` → auto-commit + push (nessun passaggio manuale)
- Scraping automatico: cron locale `@reboot → run_scheduled.py`, parte quando i dati hanno ≥3 giorni (fascia 19:30–09:00)
- Repo pubblico su GitHub → GitHub Actions gratuito illimitato (da configurare)
- `output/*.json` gitignored tranne `calendar_merged.json` (unico file dati committato)

## Parallelismo
`competitors.json` → campo `max_workers` (default: 3).
Ogni hotel ha il proprio processo Playwright. Partial files salvati in `output/partial_<hotel>_...json`.
Durata reale osservata: ~6h con 3 worker e 13 hotel (stagione maggio–settembre).
Per ridurre RAM/CPU usa `max_workers: 1` (sequenziale, un browser condiviso).
