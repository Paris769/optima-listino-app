"""
Base adapter per la normalizzazione dei listini fornitori.

Questo modulo definisce un'interfaccia di base per gli "adapter" che
trasformano file provenienti da fornitori diversi (Excel, CSV, PDF) in
DataFrame con colonne standardizzate.  Ogni fornitore può avere colonne e
formati differenti: l'obiettivo degli adapter è isolare la logica di
mapping e pulizia dal resto dell'applicazione.

Esempio di utilizzo:

    from adapters.fornitore_xyz import FornitoreXYZAdapter

    adapter = FornitoreXYZAdapter()
    df = adapter.parse_supplier_file('listino_xyz.xlsx')
    # Il DataFrame risultante avrà colonne come 'codice', 'codice fornitore',
    # 'Descrizione', 'prezzo listino', 'sconto1', etc.

Gli adapter dovrebbero sollevare eccezioni esplicative se incontrano
formati inattesi o colonne mancanti.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import pandas as pd


class BaseAdapter(ABC):
    """Classe astratta base per definire un adapter di listini fornitori."""

    supported_extensions: List[str] = ['.xlsx', '.xls', '.csv']

    def parse_supplier_file(self, path: str) -> pd.DataFrame:
        """Carica il file del fornitore e restituisce un DataFrame normalizzato.

        Parametri
        ----------
        path : str
            Il percorso al file del fornitore.

        Restituisce
        ----------
        pd.DataFrame
            DataFrame con colonne normalizzate secondo lo schema interno.
        """
        ext = os.path.splitext(path)[1].lower()
        if ext not in self.supported_extensions:
            raise ValueError(f"Estensione file non supportata: {ext}")
        if ext in {'.xls', '.xlsx', '.xlsm'}:
            df = pd.read_excel(path, dtype=str)
        else:
            df = pd.read_csv(path, dtype=str)
        df.columns = [col.strip() for col in df.columns]
        return self._map_columns(df)

    @abstractmethod
    def _map_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Trasforma il DataFrame del fornitore in formato interno.

        Ogni adapter deve implementare questo metodo per mappare le
        colonne originali a nomi standardizzati (es. 'codice', 'codice fornitore',
        'Descrizione articolo', 'prezzo di listino', 'sconto1', ecc.).
        """
        raise NotImplementedError
