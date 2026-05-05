# HotelCompare — Istruzioni per l'agente AI

## Cos'è questo progetto
Scraper prezzi competitor su Booking.com per Hotel Nuovo Tirreno (Lido di Camaiore).
Genera un calendario prezzi giornaliero per ogni hotel competitor, visualizzabile via web app Streamlit.

## Architettura

```
competitors.json
    ↓
run.py               — entry point, orchestrazione
    ├── scraper.risolvi_urls()
    └── algorithm.scrapa_calendario()
            per ogni competitor × giorno:
                scrapa_giorno() — prova 1n→7n, commit sulla prima doppia
filler.py            — arricchisce i — e ✕ con l'ultimo prezzo storico noto
report.py            — genera CSV e TXT
app.py               — visualizzazione Streamlit (legge output/*.json)
run_scheduled.py     — wrapper per esecuzione automatica settimanale
```

## File principali

| File | Responsabilità |
|---|---|
| `scraper.py` | Playwright + parsing prezzi + `lookup_entry`, `fmt_storico` |
| `algorithm.py` | algoritmo greedy per-giorno + checkpoint |
| `report.py` | genera CSV e TXT dal calendario |
| `filler.py` | riempie date mancanti con prezzi storici dai run precedenti |
| `run.py` | entry point: risolve URL → scrapa → filler → report |
| `run_scheduled.py` | wrapper @reboot: guard settimanale + notifica desktop + auto-push |
| `app.py` | visualizzazione Streamlit con tabella colorata |
| `competitors.json` | config: hotel, URL, periodo, riferimento |

## Come avviare

```bash
source venv/bin/activate
python run.py                  # scraping + report
streamlit run app.py           # web app locale
python run_scheduled.py        # run automatico (con guard settimanale)
```

## Configurazione date
In `competitors.json`:
- `data_inizio` — primo giorno da scrapare
- `data_fine` — ultimo giorno (escluso)
- `run_scheduled.py` sovrascrive `data_inizio` con domani ad ogni run automatico

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
| `— (€120* · 30/04)` | non trovato oggi, ultimo prezzo noto dal 30/04 |
| `✕ (€120* · 30/04)` | esaurito oggi, ultimo prezzo noto dal 30/04 |
| `✕` | esaurito (nessun prezzo storico disponibile) |
| `—` | non trovato (nessun prezzo storico disponibile) |

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

## Deploy
- Web app: Streamlit Community Cloud → branch `main`, file `app.py`
- Aggiornamento dati: `python run.py` → `git push origin main`
- Scraping automatico: GitHub Actions ogni martedì 09:00 e mercoledì 10:00 (CEST), con guard settimanale
