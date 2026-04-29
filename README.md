# HotelCompare

Scraper prezzi competitor su Booking.com per Hotel Nuovo Tirreno (Lido di Camaiore).

Cerca il prezzo minimo di camera matrimoniale/doppia con colazione inclusa (B&B) per ogni sabato nel periodo configurato. Output: CSV + report testo con hotel per riga e date per colonna.

## Stato funzionalità

| Funzionalità | Stato |
|---|---|
| Scraping prezzi da Booking.com | ✅ |
| Query 7-notti sabato→sabato | ✅ |
| Parser layout tabella (Tipologia camera) | ✅ |
| Parser layout card (N° max persone) | ✅ |
| Divisione prezzo settimanale → notte | ✅ |
| Report CSV (hotel × date) | ✅ |
| Rilevamento tipo pensione (B&B vs solo pernottamento) | ✅ |
| Periodo configurabile (data_inizio / data_fine) | ✅ |

## Quick start

```bash
# Prima volta
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Ogni run
source venv/bin/activate
python compare.py
```

Output in `output/report_YYYYMMDD.csv` e `output/report_YYYYMMDD.txt`.

## Configurazione (`competitors.json`)

```json
{
  "data_inizio": "2026-06-01",
  "data_fine":   "2026-06-30",
  "adulti": 2,
  "competitor": [
    { "nome": "Hotel Sirio", "citta": "Lido di Camaiore" },
    { "nome": "Hotel Verbena", "nota": "non su Booking — verifica manuale" }
  ]
}
```

- **`data_inizio`** — primo sabato da scrapare (default: oggi)
- **`data_fine`** — ultimo sabato (escluso)
- **`booking_url`** — compilato automaticamente al primo run; riscrivibile a mano
- **`nota`** — hotel non su Booking, viene mostrato come "verifica manuale" nel report

## Struttura

```
compare.py          Scraper principale
competitors.json    Config: hotel, date, adulti
test_one_night.py   Test rapido su una data
debug_context.py    Debug struttura pagine Booking
output/             CSV e TXT generati (gitignored)
venv/               Virtualenv (gitignored)
```
