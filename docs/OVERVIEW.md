<!--
  Generato da /explain_project
  Ultimo aggiornamento: 2026-05-12
  Commit di riferimento: d87906e
  NON modificare a mano — aggiornato dalla skill /explain_project
-->

## VISIONE — A COSA SERVE QUESTO PROGETTO

HotelCompare permette a Hotel Nuovo Tirreno (Lido di Camaiore) di monitorare i prezzi dei competitor su Booking.com. Produce un calendario prezzi giornaliero per ogni hotel competitor, con rilevamento automatico del soggiorno minimo, visualizzabile tramite una web app condivisibile. L'obiettivo è che la direzione possa vedere ogni settimana, senza intervento tecnico, a quanto vendono i competitor.

---

## OBIETTIVO FINALE

Sistema completamente automatico su Oracle Cloud:
1. La VM Oracle si avvia → cron lancia `run_scheduled.py` (Lun/Mar/Mer)
2. Se non ancora eseguito questa settimana → lancia `run.py`
3. Al termine → commit + push automatico su GitHub
4. Streamlit Cloud si ricarica → la direzione apre il link e vede i prezzi aggiornati

Il PC personale esce dal loop — nessun calore, nessun vincolo di uptime, nessun intervento manuale.

**Prossimo passo (in corso):** branch `Oracle_cloud_migration` — migrazione cron dalla macchina locale alla VM Oracle Cloud Free Tier (ARM A1.Flex, sempre attiva, gratuita). Vedi `docs/adr/0002-infrastruttura-split-oracle-streamlit.md`.

---

## PUNTO DI PARTENZA — STATO ATTUALE

Il sistema è **funzionante in produzione**. Il branch `main` contiene:

- Scraper completo con parsing robusto (doppia, singola, economy, tripla, quadrupla, appartamento)
- Algoritmo greedy per-giorno con rilevamento minimum stay
- Parallelismo controllato (max_workers in `competitors.json`)
- Filler storico: i prezzi di run precedenti riempiono le date mancanti
- Web app Streamlit con tabella colorata, prima colonna fissa, navigazione per mese
- Sidebar mostra data aggiornamento effettiva (derivata dai `data_vista` in `calendar_merged.json`)
- Auto-commit e push al termine di ogni run
- Script per push parziale durante run in corso

**Come avviarlo:**
```bash
source venv/bin/activate
python run.py          # scraping completo
streamlit run app.py   # web app locale
```

**Setup cron (una tantum per macchina):**
```bash
(crontab -l 2>/dev/null; echo "@reboot /home/salvatore/Projects/HotelCompare/venv/bin/python run_scheduled.py >> /home/salvatore/Projects/HotelCompare/output/run_scheduled.log 2>&1") | crontab -
```
Verifica con `crontab -l`. Il cron usa il path assoluto del venv — non serve `source venv/bin/activate`.

---

## CHI USA IL SISTEMA E COME

**Flusso normale (settimanale):**
1. Il PC si avvia → `run_scheduled.py` verifica giorno e settimana
2. Se non ancora fatto → chiama `run.py` → scrapa tutti i competitor → push automatico
3. La direzione apre il link Streamlit → vede il calendario prezzi

**Flusso manuale (quando serve):**
- `python run.py` → run completo, riprende dal checkpoint se interrotto
- `python carica_manuale_durante_run.py` → push parziale mentre run.py è ancora in corso
- Modifica `competitors.json` per cambiare periodo o aggiungere hotel

---

## ARCHITETTURA — COM'È FATTO IL SISTEMA

```
competitors.json  ← config: hotel, URL, periodo, max_workers
    ↓
run.py
    ├── Fase 1: scraper.risolvi_urls()        — 1 browser, risolve URL mancanti
    ├── Fase 2: algorithm.scrapa_hotel_worker() × max_workers
    │           ogni worker ha il proprio browser Playwright
    │           scrive partial_<hotel>_..._inprogress.json → _computed.json
    ├── Fase 3: merge partial → calendar_from..._computed<oggi>.json
    ├── Fase 4: filler.esegui_filler()         — merge storico → calendar_merged.json
    ├── Fase 5: report.genera_csv() + genera_report_testo()
    └── Fase 6: git commit + push (calendar_merged.json)
```

**Checkpoint e ripresa:** ogni hotel salva il proprio progresso in `output/partial_*_inprogress.json`. Al prossimo run, i giorni già scrappati vengono saltati automaticamente.

**Filler storico:** `filler.py` legge tutti i `calendar_from*_computed*.json` presenti in `output/` (dal più nuovo al più vecchio) e costruisce `calendar_merged.json` con i prezzi più recenti e i prezzi storici come fallback quando il dato manca nel run più recente.

---

## STACK TECNICO

| Componente | Tecnologia | Perché |
|---|---|---|
| Scraping | Playwright + Chromium headless | Booking.com usa JS per i prezzi |
| Parallelismo | ProcessPoolExecutor | Ogni hotel ha il proprio processo e browser |
| Config | JSON | Modificabile senza codice |
| Output | JSON + CSV + TXT | JSON per la web app, CSV per Excel |
| Web app | Streamlit + Pandas | Python puro, nessun HTML/JS |
| Deploy | Streamlit Community Cloud | Gratis, link fisso, si aggiorna con git push |

---

## CONTESTO DOMINIO

**Hotel di riferimento:** Hotel Nuovo Tirreno (`"riferimento": true` in `competitors.json`) — appare separato dalla media, non incluso nel calcolo medie.

**Hotel manuali:** Hotel Verbena e Hotel Alba sul Mare non sono su Booking.com — appaiono in tabella come "verifica manuale".

**Stagione:** da `data_inizio` a `data_fine` in `competitors.json`. Lo scheduler usa `stagione_fine` come fine stagione fissa.

**File principali in `output/`:**
- `calendar_merged.json` — unico file committato su git, letto da Streamlit
- `calendar_from*_computed*.json` — output di ogni run (gitignored)
- `partial_*_inprogress.json` — checkpoint in corso (gitignored)
- `partial_*_computed*.json` — checkpoint completati (gitignored)

**Multi-tenant (visione futura):**
- `clienti.json` — gitignored, mappa token → nome cliente + lista competitor visibili. Ogni cliente riceve un URL `app.py?token=abc123`. Non ancora implementato. Vedi `docs/adr/0003-multitenant-token-clienti-json.md`.

---

## FORMATO CELLE

| Cella | Significato |
|---|---|
| `€ 120` | solo camera, matrimoniale standard |
| `€ 120*` | B&B, matrimoniale standard |
| `€ 120×7` | prezzo da soggiorno minimo 7 notti |
| `€ 120#` | economy double |
| `€ 120S` | singola (nessuna doppia trovata) |
| `~€ 120` | matrimoniale trovata, tipo pensione non identificabile |
| `€ 120T` | tripla (fallback — esclusa dalle medie) |
| `€ 120Q` | quadrupla (fallback estremo — esclusa dalle medie) |
| `€ 120A` | appartamento (fallback — escluso dalle medie) |
| `— (€120* · 30/04)` | non trovato oggi, ultimo prezzo noto dal 30/04 |
| `✕ (€120* · 30/04)` | esaurito oggi, ultimo prezzo noto dal 30/04 |
| `✕` | esaurito (nessun prezzo storico disponibile) |
| `—` | non trovato (nessun prezzo storico disponibile) |

---

## COME CONTRIBUIRE — GUIDA PRATICA

**Workflow branch (regola fondamentale):**
Non lavorare mai direttamente su `main`. Ogni modifica va su un branch dedicato:
```bash
git checkout -b feature/nome-feature
# ... lavora e committa ...
streamlit run app.py   # testa visivamente
git checkout main && git merge feature/nome-feature && git push
```
Eccezione: `run.py` e `run_scheduled.py` committano direttamente su `main` — è il loro scopo e non toccano il codice.

**Aggiungere un competitor:**
```json
{ "nome": "Hotel Esempio", "citta": "Lido di Camaiore" }
```
Al primo run lo scraper cerca l'URL su Booking automaticamente.
Se non è su Booking: `{ "nome": "Hotel Esempio", "nota": "verifica manuale su hotelesempio.it" }`

**Cambiare il periodo:**
In `competitors.json` modifica `data_inizio` e `data_fine`.
Per run manuali parziali: cambia le date, esegui `python run.py`, ripristina se necessario.

**Controllare RAM/CPU:**
Il campo `max_workers` controlla quanti browser Playwright girano in parallelo.
- `max_workers: 3` → ~2h di run, usa ~3GB RAM
- `max_workers: 1` → ~5h di run, usa ~1GB RAM (sequenziale, un browser solo)

**Forzare un push parziale durante un run:**
```bash
python carica_manuale_durante_run.py
```
Legge i partial già completati, aggiorna `calendar_merged.json` e fa push. Sicuro da eseguire mentre `run.py` gira.

---

## FILE DEL PROGETTO

| File | Responsabilità |
|---|---|
| `scraper.py` | Playwright + parsing prezzi + `lookup_entry`, `fmt_storico` |
| `algorithm.py` | algoritmo greedy per-giorno + checkpoint |
| `report.py` | genera CSV e TXT dal calendario |
| `filler.py` | riempie date mancanti con prezzi storici dai run precedenti |
| `run.py` | entry point: risolve URL → scrapa → filler → report → auto-push |
| `run_scheduled.py` | wrapper @reboot: guard settimanale (Lun-Mer) + auto-push |
| `carica_manuale_durante_run.py` | push parziale durante run in corso |
| `app.py` | visualizzazione Streamlit con tabella colorata |
| `competitors.json` | config statica: hotel, URL, max_workers, riferimento — non modificata a runtime |
| `git_utils.py` | git commit + push condiviso tra run.py e run_scheduled.py |
| `scripts/retry_stack_apply.sh` | retry creazione VM Oracle: ruota tra AD-1/2/3, gira in locale con nohup |
| `scripts/oracle_keepalive.sh` | keepalive giornaliero da installare sulla VM Oracle per evitare reclaim |
| `tests/test_scraper.py` | unit test parse_valore, is_extra_letti, fmt_storico, lookup_entry |
| `tests/test_app.py` | unit test colore_prezzo_relativo, media_giorno, fmt_giorno, _fmt_data_agg |

---

## ROADMAP

- [x] Scraper prezzi Booking.com con parsing robusto
- [x] Fallback singola, tripla, quadrupla, appartamento
- [x] Algoritmo per-giorno con rilevamento minimum stay
- [x] Checkpoint con ripresa automatica
- [x] Parallelismo multi-worker (ProcessPoolExecutor)
- [x] Filler storico (`calendar_merged.json`)
- [x] Web app Streamlit con calendario colorato e colonna fissa
- [x] Deploy su Streamlit Cloud
- [x] Auto-commit e push al termine del run
- [x] Run schedulato settimanale automatico (cron @reboot)
- [x] Push parziale durante run in corso
- [x] Sidebar con data aggiornamento effettiva (max data_vista)
- [x] git_utils.py — logica git push condivisa, branch rilevato automaticamente
- [x] Unit test 33 funzioni pure (pytest, no rete)
- [x] Linting ruff — 0 errori
- [x] competitors.json separato dallo stato runtime (scheduler_state.json)
- [ ] **Migrazione Oracle Cloud** (in corso — VM non ancora creata, retry attivo in background): cron su VM ARM Always Free, nessun PC acceso necessario
- [ ] **Multi-tenant**: `clienti.json` + token URL → ogni cliente vede solo i suoi competitor (ADR-0003)
- [ ] Notifica quando i prezzi cambiano significativamente rispetto alla settimana precedente
- [ ] Gestione automatica cambio layout Booking.com (rilevamento "Visualizza tariffe")

---

## DOMANDE FREQUENTI

**Il run ha impiegato 24 ore — è normale?**
Con `max_workers: 1` e ~136 giorni × 13 hotel × 1-7 query per giorno + sleep antibot → sì, è normale. Usa `max_workers: 3` se il PC ha RAM sufficiente (~3GB liberi).

**Streamlit mostra dati vecchi dopo un push?**
`calendar_merged.json` è l'unico file che conta. Se il push è andato a buon fine e Streamlit non si aggiorna, prova a ricaricare la pagina (Streamlit Cloud impiega qualche minuto).

**Il run si è interrotto — devo ripartire da zero?**
No. I checkpoint `output/partial_*_inprogress.json` salvano il progresso hotel per hotel. `python run.py` riprende dal punto di interruzione.

**Posso aggiornare i dati mentre un run è già in corso?**
Sì: `python carica_manuale_durante_run.py` fa un push con i dati parziali già pronti, senza toccare il run in corso.
