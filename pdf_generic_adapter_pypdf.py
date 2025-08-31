"""
Adapter generico per importare listini fornitori in formato PDF utilizzando
la libreria `pypdf`, compatibile con Python 3.13.  Rispetto alla versione
basata su `pdfplumber`, questo adapter estrae il testo da ogni pagina e
prova a ricostruire una tabella semplice separando le colonne in base a
sequenze di spazi multipli.  Se il PDF non contiene tabelle ben formattate,
è possibile che l'estrazione non sia accurata; in tali casi conviene
convertire il listino in Excel o CSV prima del caricamento.

L'obiettivo è produrre un DataFrame con intestazioni originali; la mappatura
alle colonne interne avviene successivamente tramite la logica interattiva
nella UI di Streamlit.
"""
from __future__ import annotations

import os
import re
from typing import List

import pandas as pd
from pypdf import PdfReader

from .base_adapter import BaseAdapter


class PDFGenericAdapter(BaseAdapter):
    """Adapter per listini in formato PDF usando pypdf.

    Estrae il testo da ciascuna pagina, identifica la prima riga come
    intestazione e separa le colonne utilizzando sequenze di almeno due
    spazi come delimitatore.  Le righe successive sono trattate come dati.
    """

    # Estensioni supportate (solo PDF per questo adapter)
    supported_extensions: List[str] = ['.pdf']

    def __init__(self) -> None:
        super().__init__()

    def parse_supplier_file(self, path: str) -> pd.DataFrame:
        ext = os.path.splitext(path)[1].lower()
        if ext != '.pdf':
            raise ValueError('PDFGenericAdapter supports only PDF files')

        # Carica il PDF e concatena il testo di tutte le pagine
        reader = PdfReader(path)
        lines: List[str] = []
        for page in reader.pages:
            text = page.extract_text() or ''
            # suddivide il testo in righe e rimuove eventuali righe vuote
            for raw_line in text.split('\n'):
                line = raw_line.strip()
                if line:
                    lines.append(line)

        if not lines:
            raise ValueError('Nessun contenuto testuale trovato nel PDF')

        # La prima riga viene considerata intestazione.  Separiamo le colonne
        # usando due o più spazi consecutivi come delimitatore.
        header_tokens = re.split(r'\s{2,}', lines[0])
        header_tokens = [h.strip() for h in header_tokens if h.strip()]

        # Processa ogni riga dati, separando le colonne con la stessa
        # logica.  Se il numero di colonne è inferiore all'intestazione,
        # completa con stringhe vuote.
        data_rows: List[List[str]] = []
        for line in lines[1:]:
            tokens = re.split(r'\s{2,}', line)
            tokens = [t.strip() for t in tokens if t.strip()]
            if not tokens:
                continue
            # Completa con celle vuote per allineare alla lunghezza header
            if len(tokens) < len(header_tokens):
                tokens += [''] * (len(header_tokens) - len(tokens))
            data_rows.append(tokens[: len(header_tokens)])

        # Crea DataFrame con le intestazioni originali
        pdf_df = pd.DataFrame(data_rows, columns=header_tokens)
        # Rimuove eventuali spazi extra nelle intestazioni
        pdf_df.columns = [col.strip() for col in pdf_df.columns]
        return pdf_df
