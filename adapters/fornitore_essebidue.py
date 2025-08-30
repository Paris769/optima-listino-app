"""
Adapter per il listino del fornitore EssebiDue.

Questo adapter è stato preparato ipotizzando che il file Excel/CSV di
EssebiDue contenga colonne con nomi comuni come 'Codice',
'Cod.Fornitore', 'Descrizione', 'UM', 'Quantità', 'Prezzo', 'Sconto1',
'Sconto2', 'Sconto3', 'EAN'.  Il dizionario `mapping` può essere
modificato per riflettere l'intestazione reale del file.  I valori
verranno convertiti nei nomi standard utilizzati dal listino aziendale.

Per aggiornare il mapping:
    - Chiave: nome della colonna nel file di EssebiDue.
    - Valore: nome della colonna interna del listino.

Ad esempio, se il file EssebiDue utilizza 'CodiceForn' al posto di
'Cod.Fornitore', è sufficiente aggiungere `'CodiceForn': 'codice fornitore'`.
"""

from __future__ import annotations

import pandas as pd
from .base_adapter import BaseAdapter


class FornitoreEssebiDueAdapter(BaseAdapter):
    """Adapter per importare il listino del fornitore EssebiDue."""

    # Definizione del mapping: colonna originale -> colonna interna
    mapping = {
        # Colonne codice
        'Codice': 'codice',
        'Cod.Fornitore': 'codice fornitore',
        'Codice Fornitore': 'codice fornitore',
        # Descrizione e unità di misura
        'Descrizione': 'Descrizione articolo',
        'UM': 'unità di misura per unità di vendita',
        'Quantità': 'L',  # quantità per unità di misura
        # Prezzi e sconti
        'Prezzo': 'prezzo di listino',
        'Listino': 'prezzo di listino',
        'Sconto1': 'AJ',
        'Sconto2': 'AK',
        'Sconto3': 'AL',
        # Codici EAN
        'EAN': 'Codice EAN',
        'Barcode': 'Codice EAN',
    }

    def _map_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Mappa le colonne del file EssebiDue ai nomi interni del listino.

        Parametri
        ----------
        df : pd.DataFrame
            DataFrame letto dal file del fornitore.

        Restituisce
        ----------
        pd.DataFrame
            DataFrame con colonne standard.
        """
        mapped = pd.DataFrame()
        for original, target in self.mapping.items():
            if original in df.columns:
                mapped[target] = df[original]
        # Assicura che tutte le colonne del mapping esistano, anche se non
        # erano presenti nel file: le riempie con None
        for target in set(self.mapping.values()):
            if target not in mapped.columns:
                mapped[target] = None
        return mapped
