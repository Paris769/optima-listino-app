# Listino Updater

Questo progetto contiene uno script Python (`listino_app.py`) progettato per
automatizzare l’aggiornamento del listino aziendale partendo da file Excel
forniti dai fornitori.  L’obiettivo è preservare la struttura e le formule
dell’originale, aggiornando solo i campi di input e aggiungendo i nuovi
articoli.  Inoltre lo script consente di generare offerte mirate con un
semplice algoritmo di sconto del 10% sui prezzi di listino.

## Funzionalità principali

* **Caricamento del listino**: legge il file Excel originale senza
  modificare l’ordine delle colonne o le formule.
* **Ingestione listini fornitori**: supporto per file Excel e CSV.
* **Matching prodotti**: confronto deterministico tramite `codice`, `codice
  fornitore` ed `EAN`, con possibilità di estensione a regole fuzzy.
* **Aggiornamento esistenti**: aggiorna solo i campi specificati
  (configurabili) e non tocca le formule.
* **Inserimento nuovi articoli**: aggiunge righe nuove con i dati del
  fornitore lasciando inalterate le colonne non presenti.
* **Generazione offerte**: produce una tabella con sconto e prezzo
  promozionale; la logica è personalizzabile.
* **CLI**: è possibile eseguire lo script da linea di comando per
  aggiornare il listino e generare le offerte.

## Requisiti

* Python ≥ 3.8
* Librerie: `pandas`, `openpyxl` (per scrivere i file Excel).

Per installare i requisiti:

```
bash
pip install pandas openpyxl
```

## Utilizzo

Eseguire lo script con il listino di base e il listino del fornitore:

```
bash
python listino_app.py campi_listino_optima_commenti_definitivo_29.08.25.xlsx listino_fornitore.xlsx --output listino_aggiornato.xlsx --offers offerte.xlsx
```

Opzioni disponibili:

* `--output`: percorso per il file listino aggiornato.  Se omesso, il
  listino non viene salvato.
* `--offers`: percorso per il file con le offerte generate.  Se omesso,
  l’elenco offerte non viene creato.

Al termine dello script viene stampato un riepilogo con il numero di
righe aggiornate e inserite.

## Personalizzazione

Il codice è pensato per essere personalizzato in base alle esigenze
specifiche:

* Per aggiungere supporto a PDF o altri formati, modificare il metodo
  `load_supplier_list`.
* Per cambiare i campi di matching, passare una lista di colonne diversa
  al costruttore di `ListinoUpdater`.
* Per modificare la logica di matching (es. fuzzy match), intervenire nel
  metodo `_find_matches`.
* Per implementare regole di offerta diverse, modificare il metodo
  `generate_offers`.

## Limitazioni

Questo script non effettua alcuna integrazione diretta con SAP Business One
o PrestaShop; genera esclusivamente file Excel che possono essere importati
da questi sistemi.  Non è presente alcuna logica di autenticazione verso
servizi esterni.
