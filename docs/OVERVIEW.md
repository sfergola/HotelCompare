<!--
  Ultimo aggiornamento: 2026-05-01
  Branch attivo: feature/calendar-view
-->

## VISIONE — A COSA SERVE QUESTO PROGETTO

HotelCompare permette a Hotel Nuovo Tirreno (Lido di Camaiore) di monitorare i prezzi dei competitor su Booking.com. Produce un calendario prezzi giornaliero per ogni hotel, con rilevamento automatico del soggiorno minimo, visualizzabile tramite una web app condivisibile.

---

## PUNTO DI PARTENZA — BRANCH `main` (stabile)

Il branch `main` contiene lo scraper originale (`compare_booking.py`) che produce report CSV + TXT con colonne per sabato. Funziona, tua mamma lo usa già.

**Come avviarlo:**
```bash
source venv/bin/activate
python compare_booking.py
```

---

## NUOVA VERSIONE — BRANCH `feature/calendar-view`

Riscrittura completa con architettura separata in moduli e visualizzazione web via Streamlit.

### Architettura

```
competitors.json
    ↓
run.py: main()
    ├── scraper.risolvi_urls()       cerca URL su Booking se mancante
    └── algorithm.scrapa_calendario()
            per ogni competitor × giorno:
                scrapa_giorno()      prova 1n→7n, commit sulla prima doppia
                    └── scraper.scrapa_query()
                            └── scraper.estrai_prezzo()
    ↓
report.genera_csv() + genera_report_testo()   → output/*.csv, *.txt
app.py (Streamlit)                             → legge output/*.json → web app
```

### Logica algoritmo per-giorno

Per ogni hotel, per ogni giorno del periodo:
1. Prova soggiorni 1n, 2n, ..., 7n in ordine
2. Commit sulla prima **doppia/singola** trovata — il prezzo viene diviso per le notti
3. Se solo tripla/quadrupla trovate → usate come fallback visuale (escluse dalle medie)
4. I giorni successivi coperti dallo stesso soggiorno vengono saltati
5. Il risultato include `notti` (durata del soggiorno che ha prodotto il prezzo)

Esempio: hotel con minimum stay 6n → `€153*×6` per 6 giorni consecutivi.

### Formato celle

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
| `✕` | esaurito (indicativo) |
| `—` | non disponibile / non trovato |

### File

| File | Responsabilità |
|---|---|
| `scraper.py` | Playwright + parsing prezzi da Booking |
| `algorithm.py` | logica greedy per-giorno + checkpoint |
| `report.py` | generazione CSV e TXT |
| `run.py` | entry point, orchestrazione |
| `app.py` | visualizzazione Streamlit |
| `competitors.json` | config: hotel, URL, periodo |

### Come avviare

```bash
source venv/bin/activate

# Genera dati:
python run.py

# Visualizza web app in locale:
streamlit run app.py
```

### Checkpoint e ripresa automatica

Se il run si interrompe (PC sospeso, rete caduta), i dati già scrappati sono salvati in `output/*_inprogress.json`. Al prossimo `python run.py` riprende dal punto di interruzione.

---

## DEPLOY — STREAMLIT CLOUD

La web app è raggiungibile da tua mamma senza che il tuo PC sia acceso.

**Setup (una tantum):**
1. Vai su share.streamlit.io → accedi con GitHub
2. New app → repo `HotelCompare`, branch `feature/calendar-view`, file `app.py`
3. Deploy → ottieni link fisso

**Flusso aggiornamento dati:**
```bash
python run.py                          # genera nuovo JSON in output/
git add output/calendar_*.json
git push                               # Streamlit Cloud si ricarica automaticamente
```

---

## STACK TECNICO

| Componente | Tecnologia | Perché |
|---|---|---|
| Scraping | Playwright + Chromium headless | Booking.com usa JS per i prezzi |
| Config | JSON | Modificabile senza codice |
| Output | JSON + CSV + TXT | JSON per la web app, CSV per Excel |
| Web app | Streamlit + Pandas | Python puro, nessun HTML/JS |
| Deploy | Streamlit Community Cloud | Gratis, link fisso, si aggiorna con git push |

---

## COMPETITOR

| Hotel | Stato | Note |
|---|---|---|
| Hotel Lido Inn | ✅ | URL confermato |
| Hotel Sirio | ✅ | Minimum stay 6n in luglio |
| Hotel Capri | ✅ | Minimum stay 5n in luglio |
| Hotel Dei Tigli | ✅ | Accetta 1n, pensione non identificabile (~€) |
| Hotel Mariotti | ✅ | URL confermato |
| Hotel La Vela | ✅ | URL confermato |
| Hotel Florentia | ✅ | URL confermato |
| Hotel Luca | ✅ | URL confermato |
| Hotel Lungomare | ✅ | URL confermato |
| Hotel Perla del Mare | ✅ | URL confermato |
| Hotel Milani | ✅ | URL confermato |
| Hotel Sylvia | ✅ | URL confermato |
| Hotel Verbena | ❌ | Non su Booking — verifica manuale su hotelverbena.it |
| Hotel Alba sul Mare | ❌ | Non su Booking — verifica manuale su hotelalbasulmare.it |

---

## ROADMAP

- [x] Scraper sabato→sabato (branch `main`)
- [x] Fallback singola, tripla, quadrupla
- [x] Algoritmo per-giorno con rilevamento minimum stay
- [x] Checkpoint con ripresa automatica
- [x] Web app Streamlit con calendario colorato
- [x] Deploy su Streamlit Cloud
- [ ] Run schedulato settimanale automatico
- [ ] Notifica quando i prezzi cambiano significativamente
