"""
Esempio di adapter per il listino di un fornitore fittizio XYZ.

Questo adapter mostra come mappare le colonne di un file Excel del
fornitore ai nomi standard utilizzati dall'applicazione.  Adatta le
colonne originali (es. 'CodiceFor', 'Descrizione', 'PrezzoListino',
'Sconto1', ecc.) agli alias interni ('codice fornitore', 'Descrizione
articolo', 'prezzo di listino', 'sconto1', ecc.).

Per implementare un nuovo adapter per un fornitore reale, copia questo
file, rinomina la classe e modifica il dizionario `mapping` in base
all'intestazione del file.
"""

from __future__ import annotations

import pandas as pd
from .base_adapter import BaseAdapter


class FornitoreXYZAdapter(BaseAdapter):
    """Adapter di esempio per un fornitore XYZ con file Excel/CSV."""

    # Definizione del mapping: colonna originale -> colonna interna
    mapping = {
        'Codice': 'codice',
        'CodiceFor': 'codice fornitore',
        'Descrizione': 'Descrizione articolo',
        'PrezzoListino': 'prezzo di listino',
        'UM': 'unità di misura per unità di vendita',
        'QuantitàUM': 'L',  # quantità per unità di misura
        'Sconto1': 'AJ',  # sconto1 interno
        'Sconto2': 'AK',  # sconto2 interno
        'Sconto3': 'AL',  # sconto3 interno
        'EAN': 'Codice EAN',
    }

    def _map_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        # Crea una copia del DataFrame con i nomi standard.
        mapped = pd.DataFrame()
        for original, target in self.mapping.items():
            if original in df.columns:
                mapped[target] = df[original]
            else:
                # Se la colonna non è presente, riempi con None
                mapped[target] = None
        return mapped
