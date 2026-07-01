# HotelCompare

Scraper prezzi competitor su Booking.com per Hotel Nuovo Tirreno (Lido di Camaiore).
Per ogni hotel e ogni giorno del periodo, trova il prezzo minimo di camera doppia/matrimoniale.
Output: calendario JSON, CSV, report testo, web app Streamlit.

## Stato funzionalità

| Funzionalità | Stato |
|---|---|
| Scraping prezzi da Booking.com (Playwright) | ✅ |
| Algoritmo greedy per-giorno (1n → 7n, skip avanzato) | ✅ |
| Parser camera doppia / singola / economy / tripla | ✅ |
| Rilevamento tipo pensione (B&B vs solo pernottamento) | ✅ |
| Scraping parallelo per-hotel (ProcessPoolExecutor) | ✅ |
| Checkpoint per-hotel (ripresa automatica) | ✅ |
| Merge storico run (`calendar_merged.json`) | ✅ |
| Prezzi storici per celle `—/✕` (`data_vista`) | ✅ |
| Web app Streamlit con tabella colorata per mese | ✅ |
| Report CSV e TXT | ✅ |
| Scraping automatico in cloud (GitHub Actions, ~ogni 2 giorni) | ✅ |
| Push resiliente (pull --rebase + retry) + backup artifact | ✅ |
| Unit test funzioni pure (pytest, no rete) | ✅ |
| Linting ruff | ✅ |

## Quick start

```bash
# Prima volta
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Scraping
source venv/bin/activate
python run.py

# Web app (locale)
streamlit run app.py
```

## Configurazione (`competitors.json`)

```json
{
  "data_inizio":   "2026-05-08",
  "data_fine":     "2026-09-21",
  "stagione_fine": "2026-09-21",
  "adulti":        2,
  "max_workers":   2,
  "competitor": [
    { "nome": "Hotel Sirio", "citta": "Lido di Camaiore" },
    { "nome": "Hotel Nuovo Tirreno", "citta": "Lido di Camaiore", "riferimento": true },
    { "nome": "Hotel Verbena", "nota": "non su Booking — verifica manuale" }
  ]
}
```

| Campo | Significato |
|---|---|
| `data_inizio` | Primo giorno da scrapare (default: oggi) |
| `data_fine` | Ultimo giorno — modificabile per run parziali |
| `stagione_fine` | Fine stagione fissa usata dallo scheduler automatico |
| `max_workers` | Browser paralleli in locale (2 = sicuro sui 3,7GB del PC). In cloud è sovrascritto a 4 via env `MAX_WORKERS` |
| `riferimento: true` | Hotel escluso dalle medie, mostrato separatamente |
| `nota` | Hotel non su Booking, mostrato come "verifica manuale" |

## Legenda celle

| Cella | Significato |
|---|---|
| `€ 120` | Solo camera, matrimoniale standard |
| `€ 120*` | B&B, matrimoniale standard |
| `€ 120×7` | Prezzo da soggiorno minimo 7 notti |
| `€ 120#` | Economy double |
| `€ 120S` | Singola (nessuna doppia trovata) |
| `~€ 120` | Matrimoniale trovata, tipo pensione non identificabile |
| `€ 120T` | Tripla (fallback — esclusa dalle medie) |
| `€ 120Q` | Quadrupla (fallback estremo — esclusa dalle medie) |
| `— (€120* · 30/04)` | Non trovato oggi, ultimo prezzo noto dal 30/04 |
| `✕ (€120* · 30/04)` | Esaurito oggi, ultimo prezzo noto dal 30/04 |
| `✕` | Esaurito (nessun prezzo storico disponibile) |
| `—` | Non trovato (nessun prezzo storico disponibile) |

## Struttura

```
run.py               Entry point: risolve URL → scrapa → filler → report
algorithm.py         Algoritmo greedy + worker parallelo per-hotel
scraper.py           Playwright + parsing prezzi
filler.py            Merge run storici → calendar_merged.json
report.py            Genera CSV e TXT
app.py               Web app Streamlit
git_utils.py         Push resiliente del calendario (pull --rebase + retry)
run_scheduled.py     Fallback locale dormiente (scheduler da laptop, non più usato)
competitors.json     Config: hotel, URL, periodo, adulti, max_workers
.github/workflows/scraping.yml   Scraping automatico in cloud (primario)
output/              JSON, CSV, TXT generati (partial + finali)
```

## Automazione

Lo scraping gira **in cloud su GitHub Actions** (`.github/workflows/scraping.yml`), ~ogni 2 giorni,
indipendente dal PC. Il workflow chiama `run.py` (4 worker), pusha `calendar_merged.json` e Streamlit
Cloud si aggiorna. In locale lo scraping è solo **manuale** (`python run.py` o il pannello `panel.py`),
come rete di riserva se le Actions si fermano.
