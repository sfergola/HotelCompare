# HotelCompare — Istruzioni per l'agente AI

## Cos'è questo progetto
Scraper prezzi competitor su Booking.com per Hotel Nuovo Tirreno (Lido di Camaiore).
Genera un report CSV + TXT con i prezzi di camera matrimoniale B&B di ogni hotel competitore,
organizzati per hotel (righe) e date sabato-sabato (colonne).

## Architettura
- `compare.py` — scraper principale: risolve URL, scrapa, genera report
- `competitors.json` — config: lista hotel + booking_url + date
- `test_one_night.py` — test rapido su una singola data
- `debug_context.py`, `debug_one.py`, `debug_selectors.py` — strumenti debug pagine Booking
- `output/` — gitignored: CSV e TXT generati

## Come avviare
```bash
source venv/bin/activate
python compare.py
```

## Configurazione date
Nel file `competitors.json`:
- `data_inizio` — primo sabato da scrapare (default: oggi se non presente)
- `data_fine` — data di fine (esclusa)

## Logica scraping
- Query 7 notti (sabato→sabato): gli hotel costieri richiedono soggiorno minimo settimanale
- Prezzo trovato / 7 = prezzo/notte nel report
- Parser 1: cerca header "Tipologia camera" (layout tabella)
- Parser 2: cerca "N° max persone" (layout card, usato dalla maggior parte degli hotel)
- Fallback: primo prezzo € nella sezione principale (prefisso ~ nel report)
- Priorità: matrimoniale+B&B > qualsiasi camera+B&B
- Sanity check: prezzo/notte < 25€ → scartato (evita tariffe di servizio dal fallback)

## Legenda report
- `€ 175` = matrimoniale B&B confermato
- `€ 175*` = B&B confermato, tipo camera non verificato
- `~€ 175` = prezzo indicativo (fallback, tipo camera non verificato)
- `—` = non disponibile / non trovato

## Aggiungere un competitor
In `competitors.json`, aggiungi un oggetto nella lista `competitor`:
```json
{ "nome": "Hotel Esempio", "citta": "Lido di Camaiore" }
```
Al primo run, lo scraper cerca l'URL su Booking.com e lo salva automaticamente.
Se l'hotel non è su Booking, usa invece:
```json
{ "nome": "Hotel Esempio", "nota": "verifica manuale su hotelesempio.it" }
```
