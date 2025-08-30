"""
Adapter generico per importare listini fornitori in formato PDF.

Questo adapter utilizza la libreria `pdfplumber` per estrarre tabelle dal
PDF.  È adatto a listini strutturati con una singola tabella per pagina.
Assume che la prima riga estratta contenga l'intestazione delle colonne e
che le righe successive rappresentino i dati.  Le colonne vengono
convertite a nomi standard definiti nel dizionario `mapping`.

N.B.: I PDF devono essere in formato nativo (non scansione).  Per file
scansionati è necessaria una fase di OCR che non è implementata qui.
"""

from __future__ import annotations

import os
from typing import List

import pandas as pd
import pdfplumber

from .base_adapter import BaseAdapter


class PDFGenericAdapter(BaseAdapter):
    """Adapter per listini in formato PDF con tabella a struttura semplice."""

    # Estensioni supportate (solo PDF per questo adapter)
    supported_extensions: List[str] = ['.pdf']

    # Mapping di default: colonna originale -> colonna interna
    default_mapping = {
        'Codice': 'codice',
        'Codice Fornitore': 'codice fornitore',
        'Descrizione': 'Descrizione articolo',
        'UM': 'unità di misura per unità di vendita',
        'Q.tà': 'L',
        'Quantità': 'L',
        'Prezzo': 'prezzo di listino',
        'Sconto1': 'AJ',
        'Sconto2': 'AK',
        'Sconto3': 'AL',
        'EAN': 'Codice EAN',
    }

    def __init__(self, mapping: dict | None = None) -> None:
        super().__init__()
        self.mapping = mapping or self.default_mapping

    def parse_supplier_file(self, path: str) -> pd.DataFrame:
        ext = os.path.splitext(path)[1].lower()
        if ext != '.pdf':
            raise ValueError('PDFGenericAdapter supports only PDF files')
        # Estrai tutte le tabelle dal PDF e combina le righe
        rows: List[List[str]] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        rows.append(row)
        if not rows:
            raise ValueError('Nessuna tabella trovata nel PDF')
        # La prima riga dovrebbe essere l'intestazione
        header = rows[0]
        data_rows = rows[1:]
        pdf_df = pd.DataFrame(data_rows, columns=header)
        # Pulizia delle intestazioni
        pdf_df.columns = [col.strip() for col in pdf_df.columns]
        # Mappa le colonne a nomi standard
        mapped = pd.DataFrame()
        for original, target in self.mapping.items():
            if original in pdf_df.columns:
                mapped[target] = pdf_df[original]
        # Riempie le colonne mancanti con None
        for target in set(self.mapping.values()):
            if target not in mapped.columns:
                mapped[target] = None
        return mapped

    # Non è necessario ridefinire _map_columns perché parse_supplier_file
    # già normalizza e mappa le colonne.
