# HotelCompare

Tool di monitoraggio prezzi competitor su Booking.com per hotel costieri in Versilia.
Genera report comparativi per supportare le decisioni di pricing dell'Hotel Nuovo Tirreno.

## Language

**Competitor**:
Un hotel della zona (Lido di Camaiore) i cui prezzi vengono monitorati.
_Avoid_: hotel, struttura

**Prezzo per notte**:
Prezzo totale del soggiorno diviso il numero di notti. Non è necessariamente il prezzo della singola notte — dipende dal minimum stay.
_Avoid_: prezzo notte, tariffa

**Minimum stay**:
Numero minimo di notti che un competitor accetta per una data di checkin. Varia per periodo e hotel. Non è un dato direttamente disponibile — viene inferito dal comportamento di Booking.com.

**Soggiorno minimo trovato**:
Il numero di notti del soggiorno più breve per cui Booking.com ha restituito un prezzo, a partire da un dato giorno. Determina quante celle del calendario condividono lo stesso prezzo.
_Avoid_: minimum stay effettivo

**Tipo camera** (gerarchia di preferenza):
1. Matrimoniale/doppia standard
2. Economy double
3. Singola
4. Tripla (solo visuale, esclusa dalle medie)
5. Quadrupla (solo visuale, esclusa dalle medie)

**Stato cella**:
- `€126` — prezzo trovato nel run più recente
- `—` — nessun prezzo trovato nel run più recente (causa ignota — potrebbe riaprire)
- `✕` — esaurito nel run più recente (Booking mostra esplicitamente "sold out") — indicativo, potrebbe significare camera venduta

**Prezzo storico** (affianca lo stato corrente):
Il prezzo più recente mai osservato per quella cella, mostrato solo quando lo stato corrente è `—` o `✕`.
Formato: `— (€120* · 05/05)` o `✕ (€120* · 05/05)`.
Semantica: "lo stato è questo oggi, ma l'ultima volta che c'era disponibilità il prezzo era X".
Non mostrato quando c'è un prezzo reale — in quel caso la data di scraping non è rilevante.
_Avoid_: prezzo precedente, cache

**calendar_merged.json**:
Calendario unificato prodotto da `filler.py`. Regola: il run più recente vince sempre su ogni cella, indipendentemente da cosa conteneva. Se la cella più recente è `—` o `✕`, affianca il prezzo più recente mai osservato con la data dello scraping. È la fonte dati primaria di `app.py`.

**Tipo pensione**:
- `solo camera` — pernottamento senza pasti
- `B&B` — colazione inclusa
- `ignota` — Booking non espone il dato in modo leggibile (es. Hotel Dei Tigli)

**Marker prezzo** (suffissi nel report):
- `€ 126` — matrimoniale, solo camera
- `€ 126*` — matrimoniale, B&B
- `~€ 126` — matrimoniale, pensione ignota
- `€ 126#` — economy double
- `€ 126S` — singola
- `€ 126T` — tripla (fallback visuale)
- `€ 126Q` — quadrupla (fallback visuale)

**Cella calendario**:
Intersezione giorno × competitor nella visualizzazione calendario. Mostra il prezzo per notte e il soggiorno minimo trovato (es. `€126 ×7`).

**stagione_fine**:
Data di fine stagione fissa in `competitors.json`. Usata solo dallo scheduler automatico (`run_scheduled.py`). Non viene mai modificata dai run. `data_fine` è la controparte manuale, modificabile liberamente per run parziali.
_Avoid_: data_fine dello scheduler, end date

## Decisioni prese (feature/calendar-view)

1. **Unità di prezzo**: prezzo del soggiorno più breve disponibile diviso le notti — non la media di periodi fissi.
2. **Indicatore soggiorno**: ogni cella mostra il numero di notti da cui deriva il prezzo (es. `€126 ×7`). Celle consecutive dallo stesso soggiorno hanno lo stesso colore o stile.
3. **Periodo**: tutto il range `data_inizio`→`data_fine`, organizzato per mese. Nessun filtro per ora.
4. **Tipo pensione**: mantenuta nel calendario tramite marker nella cella (`€126` = solo camera, `€126*` = B&B). Una riga per competitor — non righe separate per pensione. Priorità: solo camera > B&B.
5. **Output**: tre formati — Streamlit (visualizzazione principale), CSV (per Excel), TXT (per lettura rapida).
6. **Struttura file**:
   - `scraper.py` — logica Playwright: carica pagina, estrae prezzo e stato (trovato/non trovato/esaurito)
   - `algorithm.py` — algoritmo giorno-per-giorno: decide quali query fare, riempie il calendario
   - `report.py` — genera CSV e TXT dal calendario
   - `app.py` — visualizzazione Streamlit
   - `competitors.json` — config invariata
7. **Persistenza**: salvataggio incrementale su JSON dopo ogni richiesta, con write-then-rename per evitare corruzione del file. Al prossimo run, i giorni già scrappati vengono saltati.
8. **Naming file output**: `calendar_from{YYYYMMDD}_to{YYYYMMDD}_computed{YYYYMMDD}.{ext}` — ogni run produce file nuovi, i vecchi restano.
9. **Scraper**: sostituisce quello attuale su `feature/calendar-view`. Il branch `main` resta stabile con il vecchio report.
