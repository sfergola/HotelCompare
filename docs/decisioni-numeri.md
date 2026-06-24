# Decisioni che producono i numeri — HotelCompare

> **Cos'è questo documento.** Ogni prezzo e ogni media che l'app mostra è il risultato di una
> catena di **decisioni statistiche e logiche** prese da chi costruisce lo strumento, non un dato
> "grezzo" letto da Booking. Questo file le raccoglie tutte in un posto solo: *cosa* abbiamo deciso,
> *dove* vive nel codice, *perché* l'abbiamo deciso così, e *quando converrebbe riconsiderarlo*.
>
> **A chi serve.** Al PM (Salvatore) per sapere su cosa sta poggiando un numero; all'agente AI
> quando tocca la logica dei prezzi (deve leggere qui prima di cambiare una soglia); a chiunque
> faccia audit/review e voglia chiedersi "esiste un paradigma migliore?".
>
> **Regola d'oro.** Queste decisioni NON vanno esposte all'utente finale nell'app: lui deve vedere
> numeri affidabili, non il come. Se cambi una costante qui sotto, **i numeri mostrati cambiano** —
> aggiorna anche questo documento nello stesso commit.

---

## 0. Il pannello di controllo — tutte le costanti in un colpo d'occhio

Tutte le manopole che spostano i numeri. Cambiarne una è una decisione esplicita.

| Costante | Valore | Dove | Effetto |
|---|---|---|---|
| `COLAZIONE_STIMA_PERSONA` | `8` €/persona | `scraper.py` | stima colazione aggiunta alle celle solo-camera (`≈`) |
| `SOGLIA_STALENESS_GIORNI` | `15` giorni | `scraper.py` | oltre questa età un prezzo esce dalla media ed è declassato a storico |
| `SOGLIA_OUTLIER` | `2.5` × mediana | `scraper.py` | prezzo oltre N× la mediana del giorno esce dalla media |
| `COPERTURA_MIN` | `0.30` (30%) | `scraper.py` | hotel sotto questa quota di celle pulite esce dalla media |
| `DISPONIBILITA_MIN_MEDIA` | `0.50` (50%) | `scraper.py` | se meno di metà dei mediabili ha una doppia quel giorno, la media è segnalata poco affidabile (sbiadita, marker `°`) |
| `MAX_NOTTI` | `7` notti | `algorithm.py` | durata massima di soggiorno provata per trovare un prezzo |
| soglia prezzo minimo | `25` €/notte | `scraper.py` `normalizza_prezzo` | sotto questa cifra/notte la cella è scartata (implausibile per una doppia) |
| `adulti` | `2` | `competitors.json` | occupazione fissa del confronto |
| euristiche parser | `v > 20`, `len < 25` | `scraper.py` `estrai_prezzo` | filtri su cosa conta come "riga-prezzo" |

---

## 1. Cosa confrontiamo: "doppia + colazione"

**Decisione.** L'unità di confronto è il prezzo per notte di una **camera doppia/matrimoniale con
colazione**, per 2 adulti. Non "la camera più economica in assoluto", non "la prima che appare".

**Dove.** `scraper.py` → `estrai_prezzo` (ordine di preferenza dei gruppi); `build_url`
(`group_adults=2`).

**Perché.** È il prodotto che vende davvero l'Hotel Nuovo Tirreno e ciò che un cliente confronta
realmente. Confrontare "il più economico" mischierebbe singole, camere nude e appartamenti — mele
con pere — e darebbe un mercato fittiziamente più basso.

**Conseguenza diretta sul numero.** La **B&B reale vince sempre** sul confronto, anche se più cara
di una solo-camera dello stesso hotel: vogliamo il prezzo *doppia + colazione*, non il minimo
assoluto. (Verificato sui dump reali: dove esiste la B&B vera è più accurata della stima.)

**Quando riconsiderarlo.** Se il mercato locale iniziasse a vendere prevalentemente solo-camera, o
se HNT cambiasse il proprio prodotto di punta (es. mezza pensione).

---

## 2. Come si sceglie il prezzo di una singola cella (il parser)

Quando un hotel ha più camere e più tariffe lo stesso giorno, la cella mostra **una** cifra. Le
regole che la scelgono, in ordine:

1. **Priorità per tipo di camera:** matrimoniale standard → economy double (`#`) → singola (`S`).
   Tripla (`T`), quadrupla (`Q`), appartamento (`A`) solo come *fallback visuale* se non c'è altro,
   ed **esclusi dalla media**.
2. **All'interno del tipo, priorità per board:** B&B reale (`*`) → solo-camera (`≈`) → board non
   identificata (`~`).
3. **Si sceglie il prezzo minimo** tra le tariffe equivalenti (la più conveniente realmente
   prenotabile).
4. **Con sconto attivo:** se Booking mostra "Prezzo attuale € Y", vince **Y** (il post-sconto), mai
   il barrato. *(Questo era il bug dell'audit 10/06: prendevamo il barrato → competitor +7-9%.)*
5. **Le tariffe "per 1 ospite" della doppia sono escluse** (`occ != 1`): non sono il prezzo della
   doppia. Su Booking reale sono marcate `N° max persone: 1`.

**Dove.** `scraper.py` → `estrai_prezzo`.

**Perché il minimo.** È il prezzo che il cliente può davvero ottenere quel giorno per quella camera.

**Quando riconsiderarlo.** Se si volesse mostrare il prezzo "consigliato/in evidenza" di Booking
invece del più conveniente — è una definizione diversa di "prezzo di mercato".

### 2b. Soglie tecniche del parser (euristiche, non semantica)

- `v > 20`: una riga con meno di €20 non è una tariffa camera (è una colazione, una tassa…).
- `len(riga) < 25`: i prezzi stanno su righe corte; le righe lunghe sono descrizioni.
- Le righe con keyword di colazione sono escluse dalla cattura-prezzo *(fix audit 21/06)*.

**Quando riconsiderarlo.** Sono cuciti sulla forma testuale di Booking: se cambia il layout, qui si
mette mano. → vedi rischio "degradazione silenziosa" in [audit veridicità].

---

## 3. La stima colazione (celle `≈`)

**Decisione.** Se un hotel quel giorno vende **solo la camera nuda** (niente B&B), per confrontarla
con le doppie-colazione degli altri le aggiungiamo una **stima di colazione fissa: 8 €/persona ×
2 adulti = 16 €/notte**. La cella è marcata `≈`.

**Dove.** `COLAZIONE_STIMA_PERSONA = 8` in `scraper.py`; applicata in `normalizza_prezzo`.

**Perché.** Senza, confronteremmo solo-camera contro B&B (mele con pere) e il mercato sembrerebbe
più basso di quanto sia. La stima riallinea il confronto all'unità "doppia + colazione" (§1).

**Perché 8 €.** Stima conservativa del costo colazione nella zona. È un *parametro di dominio*: se
hai un dato migliore, cambialo — è una sola riga.

**Quando riconsiderarlo.** Se le colazioni reali viste nei dump fossero sistematicamente sopra/sotto
€8, o se volessi una stima per-hotel invece che fissa.

---

## 4. L'algoritmo per-giorno (soggiorni 1→7 notti)

**Decisione.** Per ogni hotel × giorno, proviamo soggiorni di 1, 2, … fino a `MAX_NOTTI = 7` notti.
Ci si **ferma alla prima doppia/singola trovata**; tripla/quadrupla solo se non c'è altro. Il prezzo
è diviso per le notti (prezzo/notte).

**Dove.** `algorithm.py` → `scrapa_giorno`, `MAX_NOTTI`.

**Conseguenza importante (da sapere).** Se il prezzo viene da un soggiorno di N notti (minimum
stay), quel **prezzo/notte medio viene scritto su tutti gli N giorni coperti**, con marker `×N`. Non
è il prezzo reale della singola notte di quel giorno: è la media spalmata del soggiorno. È il miglior
dato disponibile quando Booking impone un minimum stay.

**Quando riconsiderarlo.** Se volessi privilegiare sempre il soggiorno 1 notte (più fedele al
singolo giorno ma più spesso "non disponibile").

---

## 5. Cosa entra nella MEDIA dei competitor

La riga `MEDIA` è il cuore decisionale dello strumento. Un prezzo entra nella media **solo se è una
doppia confrontabile e affidabile**. Le esclusioni, e il perché di ognuna:

| Escluso | Regola | Perché |
|---|---|---|
| Singole, triple, quadruple, appartamenti | `is_extra_letti` (S/T/Q/A) | non sono la doppia che confrontiamo (§1) |
| Prezzi vecchi (> 15 giorni) | `SOGLIA_STALENESS_GIORNI`, `prezzo_stantio` | un prezzo di oltre 2 settimane fa non è più "il prezzo di oggi"; declassato a storico |
| Outlier (> 2,5× la mediana del giorno) | `SOGLIA_OUTLIER`, `filtra_prezzi_anomali` | l'"ultima camera a €888" non rappresenta il mercato; serve con ≥4 valori |
| Hotel quasi-cieco (< 30% celle pulite) | `COPERTURA_MIN`, `hotel_in_media` | pochi dati rari e sballati distorcerebbero la media (es. Mariotti, ~15%, quasi sempre sold-out) |
| Hotel di riferimento (HNT) | `riferimento` | è il soggetto del confronto, non un competitor |
| Hotel a verifica manuale | `manuali` | non scrappati automaticamente |

**Dove.** Logica unica in `scraper.py` → `valore_per_media`, `filtra_prezzi_anomali`,
`hotel_in_media`, `media_competitor` (condivisa tra `app.py` e `report.py`).

**Perché queste quattro soglie e non altre.** Sono il minimo per avere una media che rappresenti
*chi ha davvero disponibilità a prezzi sensati*, robusta a: prezzi non confrontabili, dati stantii,
picchi anomali, hotel non rappresentativi.

### 5b. Perché la media non si basa su prezzi vecchi — la soglia di staleness

**Decisione (24/06).** Un prezzo entra nella media solo se è stato visto **negli ultimi 15 giorni**
(`SOGLIA_STALENESS_GIORNI = 15`, prima era 30). La media è il numero su cui l'albergatore prezza:
non deve poggiare su dati stantii spacciati per attuali.

**Perché 15 e non 10 o 30.** Lo scraper gira **ogni 3 giorni** (`GIORNI_TRA_RUN`). Quindi:
- un prezzo più vecchio di 15 giorni = quel giorno ha **fallito ~5 run consecutivi** → è un dato
  genuinamente malato, giusto escluderlo dalla media;
- a 10 giorni (~3 run falliti) si rischia di potare celle solo per un paio di intoppi di rete
  normali → la media si regge su meno hotel ed è più ballerina;
- 30 giorni era troppo: un prezzo di 3 settimane appariva ancora come "attuale".

15 taglia il marcio senza impoverire la media. **Quando riconsiderarlo:** se cambia la cadenza dei
run (`GIORNI_TRA_RUN`), va riproporzionato — la soglia è ~5 cadenze.

**Doppio lavoro della soglia (da sapere).** `SOGLIA_STALENESS_GIORNI` fa due cose con un solo
numero: (1) esclude il prezzo dalla *media*; (2) declassa la cella in *tabella* da `€120*` a
`— (€120 · data)`. È voluto e coerente: oltre soglia il prezzo non è "attuale" né nel calcolo né a
schermo, e la data resa visibile dice all'utente quanto è vecchio. Lo *storage* del prezzo non si
perde mai (vedi §7): resta in `calendar_merged.json`, solo non conta come corrente.

**Nota sullo storage vs la media.** La paura "perdiamo i prezzi vecchi" è infondata: il merged
**conserva sempre l'ultimo prezzo disponibile per ogni giorno scrapato, con la sua data** (§7). La
staleness non butta via niente — decide solo *cosa conta come prezzo di oggi* nella media. Sono due
piani distinti: lo storico è memoria, la media è fotografia del presente.

**Quando riconsiderare le altre soglie della media:**
- `SOGLIA_OUTLIER = 2,5×` e `COPERTURA_MIN = 30%` sono tarati sull'audit del 16/06 (unico hotel
  escluso: Mariotti). Da rivedere se cambiano gli hotel monitorati.

---

### 5c. Giorni con poche doppie: bias di selezione e campione minimo

**Il problema (osservato il 24/06 sul 26-27/06).** Nei giorni di picco di domanda metà degli hotel
va sold-out. La media si calcola allora **solo sui sopravvissuti** — e i sopravvissuti sono le
**camere care**: le economiche si vendono per prime. Risultato: in un giorno di picco la media non
dice "il prezzo tipico", dice "quel che resta prenotabile, che è il caro". È un **bias di selezione
verso l'alto**, non un errore di calcolo (verificato: il 26/06 media 306 € su 5 hotel, il 27/06 257 €
su soli 3, contro ~130-140 € dei giorni normali). Sotto i 4 valori il filtro outlier non scatta
nemmeno → il giorno è doppiamente fragile.

**Decisione (24/06).** Non si nasconde né si sopprime la media (proprio nei picchi serve di più):
si **segnala la bassa affidabilità**. Se **meno del 50% dei mediabili** ha una doppia confrontabile
quel giorno (`DISPONIBILITA_MIN_MEDIA = 0.50`), la cella MEDIA è mostrata **sbiadita** con marker
`°`, e la legenda spiega come leggerla.

**Perché relativa e non un conteggio assoluto.** Un numero secco (es. "<4 doppie") non scala col
numero di hotel monitorati e va ritarato a ogni aggiunta. La quota *disponibili/mediabili* è
robusta: "metà del mercato non ha camera" significa lo stesso con 11 o con 30 hotel.

**Perché 50% e non un valore tarato sui dati di oggi.** La distribuzione di disponibilità della
stagione **non è usabile per tarare la soglia**: è confondata dal *lead-time* (i giorni lontani
appaiono pieni solo perché nessuno ha ancora prenotato; lug/ago oggi stanno al ~91% perché distanti,
non perché meno richiesti). Quindi 50% è scelto **da primo principio**: sotto metà mercato
disponibile la media è il "residuo caro", non il prezzo tipico. Verifica sul dato attuale: giorni
vicini ma non di picco restano pieni (29/06 all'82%, 04/07 al 91%), mentre 26-27/06 — evento reale —
crollano a 45% e 27%. La disponibilità qui segue la *domanda*, non solo la vicinanza.

**Conseguenza accettata.** Giorni vicini ad alta domanda *verranno* sbiaditi (è corretto: quelle
medie sono davvero meno affidabili). Se col tempo si osservasse che il near-term viene sbiadito a
tappeto (rumore da pura prossimità), si passerà a una misura **robusta al lead-time** (confronto a
parità di giorni-al-check-in) — richiede storico che oggi non abbiamo, quindi rimandata.

**Dove.** `scraper.py` → `valori_media` (numeratore = doppie disponibili) e `DISPONIBILITA_MIN_MEDIA`;
base (denominatore) = hotel mediabili del giorno; resa in `app.py` (riga MEDIA, colore + marker `°`).

---

## 6. Cosa resta VISIBILE in tabella ma fuori dalla media

Esclusione dalla media ≠ sparizione. Restano visibili (in tabella, non nel calcolo):
- gli hotel sotto copertura (es. Mariotti), con i loro `✕` e prezzi rari;
- gli outlier (potrebbero essere l'ultima camera vera);
- i prezzi storici, nel formato `— (€120 · 30/04)`;
- triple/quadruple/appartamenti come fallback visuale.

**Perché.** Trasparenza del dato grezzo a chi guarda, pulizia del dato aggregato nella media. Sono
due livelli diversi: la cella racconta *cosa c'è*, la media racconta *com'è il mercato*.

> **Nota di design (21/06):** l'avviso "Esclusi dalla media: …" è stato **rimosso dall'app**. È una
> decisione statistica interna (questo documento), non informazione per l'utente finale.
>
> **Sfumatura (24/06):** una cosa è la *meccanica interna* (quali hotel sono esclusi e perché →
> resta nascosta); altra è una *garanzia di freschezza* utile all'albergatore. Per questo l'app
> mostra una caption sotto la tabella — "la MEDIA considera solo doppie viste negli ultimi 15
> giorni" — e la legenda chiarisce i 15 giorni sul marker storico. È un segnale di fiducia sulla
> qualità del dato, non l'esposizione del *come*: coerente con la regola d'oro.

---

## 7. Lo storage: l'ultimo prezzo disponibile per ogni giorno (il "merged")

**Come funziona.** `calendar_merged.json` è il database dei prezzi. Per ogni `(hotel, giorno
scrapato)` tiene **sempre l'ultimo prezzo disponibile con la sua data**, costruito così
(`filler.py` → `_merge`, run uniti dal più recente al più vecchio):
- se il run più recente **ha** il prezzo → finisce in `prezzo` + `data_vista` (quando l'ha visto);
- se il run più recente **non** ce l'ha (non trovato / esaurito) → si scorre indietro e si mette il
  primo prezzo disponibile in `storico_prezzo` + `storico_data`.

**Conseguenza.** Un giorno non resta mai "vuoto" se almeno un run passato l'aveva visto: si mostra
l'ultimo prezzo noto, marcato come storico con la data (`— (€120 · data)`). È la dinamica che fa sì
che **non serva preoccuparsi di "perdere" i prezzi vecchi**: sono conservati.

**Relazione con la staleness (§5b).** Storage e media sono due piani diversi: il merged *conserva*
ogni ultimo prezzo (memoria), la staleness decide *quali di questi contano come prezzo di oggi*
nella media (fotografia del presente). Un prezzo oltre 15 giorni resta nel file e visibile in
tabella, ma esce dalla media.

**Dove.** `filler.py` → `esegui_filler`, `_merge`; lettura via `scraper.py` → `lookup_entry`.

---

## Collegamenti
- Storia e verifiche dell'audit veridicità prezzi: memoria di progetto `project_audit_veridicita`.
- Architettura della pipeline: `AGENT.md` (sezioni "Logica algoritmo", "Legenda celle", "Regole
  della MEDIA") e `brief.md`.
- Decisioni ancora aperte (alert anti-silenzio, staleness, spot-check live): `brief.md`.
