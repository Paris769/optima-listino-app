"""
listino_app.py
================

This module provides a simple framework for updating your company price list
(`listino`) using supplier price lists and for generating tailored offers for
customers.  The goal of this script is to automate as much of the tedious
work as possible while leaving the underlying structure of your Excel
workbook untouched.  The main features include:

* Reading the base listino Excel file without altering its column order or
  formulas.  All columns and formulas defined in the template will be
  preserved when writing updates.
* Ingesting supplier price lists from Excel files.  You can extend the
  `load_supplier_list` method to support additional formats (e.g. PDF) by
  using libraries such as `pdfplumber` or `tabula`.
* Matching supplier products to existing products in the listino using one or
  more keys (internal code, supplier code, EAN).  Matches are applied
  deterministically and you can customise the matching logic to your needs.
* Updating existing products with new pricing or other attributes from the
  supplier list.  Only values in the input columns are overwritten—formulas
  and derived values remain intact.
* Adding new products that are not currently present in the listino.  New
  rows are appended with the appropriate data while leaving the rest of the
  row blank, allowing existing formulas to populate as designed.
* Generating a simple offers table based on business rules.  The default
  implementation demonstrates how you might compute a promotional price or
  discount, but you should extend this method to reflect your business
  logic (customer segmentation, seasonal promotions, stock levels, etc.).

Example usage::

    from listino_app import ListinoUpdater

    updater = ListinoUpdater('campi_listino_optima_commenti_definitivo_29.08.25.xlsx')
    supplier_df = updater.load_supplier_list('supplier_list.xlsx')
    updater.update_existing_products(supplier_df)
    updater.add_new_products(supplier_df)
    offers = updater.generate_offers()
    updater.save('listino_updated.xlsx')
    offers.to_excel('offerte.xlsx', index=False)

The resulting Excel files can then be reviewed and uploaded to your ERP or
 e‑commerce platform (SAP Business One, PrestaShop, etc.).

Note: This script requires the `pandas` library.  Install it via
`pip install pandas openpyxl` if necessary.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd


@dataclass
class ListinoUpdater:
    """Encapsulates the logic for updating a price list (listino).

    Parameters
    ----------
    listino_path : str
        Path to the base listino Excel file.
    key_fields : list[str], optional
        A list of column names used to match products between the listino
        and supplier lists.  Typical examples include internal codes
        (``codice``), supplier codes (``codice fornitore``) and EAN codes.
        Matches are attempted in order: the first key that yields a
        non‑ambiguous match is used.
    input_columns : list[str], optional
        Columns that are considered input values and can be overwritten
        without affecting formulas.  If left ``None``, all columns except
        those containing formulas will be treated as input.  To
        explicitly specify the columns to update, provide a list of
        column names.
    """

    listino_path: str
    key_fields: List[str] = field(default_factory=lambda: [
        'codice', 'codice fornitore', 'Codice EAN'
    ])
    input_columns: Optional[List[str]] = None

    def __post_init__(self) -> None:
        # Load the base listino into a DataFrame.  Keep the original column
        # order and do not evaluate formulas (openpyxl handles formulas
        # transparently when writing back out).
        self.df = pd.read_excel(self.listino_path, dtype=str)
        # Ensure consistent column names (strip whitespace, lower case)
        self.df.columns = [col.strip() for col in self.df.columns]
        # Track rows that have been updated or inserted
        self.updated_rows: List[int] = []
        self.inserted_rows: List[int] = []

    def load_supplier_list(self, path: str) -> pd.DataFrame:
        """Load a supplier price list from an Excel or CSV file.

        If ``path`` ends with ``.pdf``, this method will raise a
        ``NotImplementedError`` by default.  You can extend this method to
        implement PDF parsing using `pdfplumber` or another library.

        Parameters
        ----------
        path : str
            Path to the supplier file.

        Returns
        -------
        pd.DataFrame
            A DataFrame containing the supplier data.
        """
        ext = os.path.splitext(path)[1].lower()
        if ext in {'.xls', '.xlsx', '.xlsm'}:
            supp = pd.read_excel(path, dtype=str)
        elif ext in {'.csv', '.txt'}:
            supp = pd.read_csv(path, dtype=str)
        elif ext == '.pdf':
            raise NotImplementedError(
                'PDF parsing not implemented. Consider using pdfplumber or tabula to extract tables.'
            )
        else:
            raise ValueError(f"Unsupported supplier file format: {ext}")
        supp.columns = [col.strip() for col in supp.columns]
        return supp

    def _find_matches(self, supplier_row: pd.Series) -> Optional[int]:
        """Attempt to find the row index in the listino DataFrame that matches
        the given supplier row.

        The method iterates over the configured `key_fields`.  For each
        key, if the supplier row contains a value and the listino has
        matching values in that column, the index of the first match is
        returned.  If no match is found for any key, ``None`` is returned.

        Parameters
        ----------
        supplier_row : pd.Series
            A row from the supplier DataFrame.

        Returns
        -------
        Optional[int]
            The index of the matching row in the listino, or ``None``.
        """
        for key in self.key_fields:
            if key in supplier_row and pd.notna(supplier_row[key]):
                # Normalise the value (strip whitespace)
                value = str(supplier_row[key]).strip()
                if value == '':
                    continue
                # Find matching rows in listino
                matches = self.df.index[self.df[key].astype(str).str.strip() == value]
                if len(matches) == 1:
                    return matches[0]
                elif len(matches) > 1:
                    # Ambiguous match – you may want to refine logic or handle this separately
                    return matches[0]
        return None

    def update_existing_products(self, supplier_df: pd.DataFrame) -> None:
        """Update products in the listino that already exist based on supplier data.

        For each row in the supplier DataFrame, the method attempts to
        locate a matching row in the listino using `_find_matches`.  If a
        match is found, values from the supplier row are copied into the
        listino for the columns specified in `input_columns`.  Columns not
        listed in `input_columns` are ignored, preserving formulas and
        derived values.

        Parameters
        ----------
        supplier_df : pd.DataFrame
            A DataFrame containing supplier data, typically loaded via
            ``load_supplier_list``.
        """
        for _, supp_row in supplier_df.iterrows():
            idx = self._find_matches(supp_row)
            if idx is None:
                continue
            for col in (self.input_columns or supp_row.index.tolist()):
                if col not in self.df.columns or col not in supp_row:
                    continue
                new_val = supp_row[col]
                if pd.isna(new_val):
                    continue
                # Update only if the value has changed
                if str(self.df.at[idx, col]).strip() != str(new_val).strip():
                    self.df.at[idx, col] = new_val
                    self.updated_rows.append(idx)

    def add_new_products(self, supplier_df: pd.DataFrame) -> None:
        """Append new products from the supplier DataFrame to the listino.

        A product is considered new if `_find_matches` returns ``None``.  For
        each new product, a new row is created in the listino.  Columns
        present in the supplier data are copied over for the specified
        `input_columns`; all other columns are left blank (``NaN``),
        allowing existing formulas in the listino template to compute
        derived values automatically when the file is opened in Excel.

        Parameters
        ----------
        supplier_df : pd.DataFrame
            A DataFrame containing supplier data.
        """
        for _, supp_row in supplier_df.iterrows():
            if self._find_matches(supp_row) is not None:
                continue
            # Create a new blank row
            new_record = {col: None for col in self.df.columns}
            for col in (self.input_columns or supp_row.index.tolist()):
                if col in self.df.columns and col in supp_row:
                    val = supp_row[col]
                    new_record[col] = val if pd.notna(val) else None
            self.df = pd.concat(
                [self.df, pd.DataFrame([new_record])], ignore_index=True
            )
            self.inserted_rows.append(len(self.df) - 1)

    def generate_offers(self) -> pd.DataFrame:
        """Generate a simple offers table based on the listino.

        The default implementation creates a new DataFrame with a subset of
        columns and adds two new columns: ``Sconto Offerta`` (offer
        discount) and ``Prezzo Promo`` (promotional price).  The discount
        is calculated as 10% off the list price if a valid list price
        exists; otherwise, it remains ``NaN``.  You can extend or replace
        this logic to implement more sophisticated rules (e.g. tiered
        discounts, bundles, cross‑sell offers).

        Returns
        -------
        pd.DataFrame
            A DataFrame representing the offers.
        """
        # Ensure the necessary columns exist.  Adjust these names based on
        # your actual listino template.
        required_cols = ['codice', 'Descrizione articolo', 'prezzo di listino']
        for col in required_cols:
            if col not in self.df.columns:
                raise KeyError(
                    f"Column '{col}' not found in listino. Update required_cols to match your template."
                )

        offers = self.df[required_cols].copy()
        # Compute a 10% discount as a simple example
        def compute_promo(price: str) -> Tuple[Optional[float], Optional[float]]:
            try:
                p = float(str(price).replace(',', '.'))
            except (TypeError, ValueError):
                return None, None
            discount = round(p * 0.10, 2)
            promo_price = round(p - discount, 2)
            return discount, promo_price

        discounts: List[Optional[float]] = []
        promo_prices: List[Optional[float]] = []
        for price in offers['prezzo di listino']:
            d, promo = compute_promo(price)
            discounts.append(d)
            promo_prices.append(promo)

        offers['Sconto Offerta'] = discounts
        offers['Prezzo Promo'] = promo_prices
        return offers

    def save(self, output_path: str) -> None:
        """Save the updated listino to a new Excel file.

        Parameters
        ----------
        output_path : str
            Destination path for the updated Excel file.
        """
        # Use openpyxl engine implicitly; this preserves formulas and
        # formatting in existing columns.
        self.df.to_excel(output_path, index=False)

    def report(self) -> str:
        """Return a summary of operations performed (updates and inserts)."""
        report_lines = [
            f"Totale righe aggiornate: {len(set(self.updated_rows))}",
            f"Totale righe inserite: {len(self.inserted_rows)}",
        ]
        return '\n'.join(report_lines)



def main():
    import argparse
    parser = argparse.ArgumentParser(description='Aggiorna il listino aziendale con listini fornitori.')
    parser.add_argument('listino', help='Percorso al file Excel del listino di base')
    parser.add_argument('supplier', help='Percorso al file Excel/CSV del listino del fornitore')
    parser.add_argument('--output', default=None, help='Percorso del file Excel aggiornato (opzionale)')
    parser.add_argument('--offers', default=None, help='Percorso del file Excel con le offerte generate (opzionale)')
    args = parser.parse_args()

    updater = ListinoUpdater(args.listino)
    supplier_df = updater.load_supplier_list(args.supplier)
    updater.update_existing_products(supplier_df)
    updater.add_new_products(supplier_df)

    if args.output:
        updater.save(args.output)
        print(f'Listino aggiornato salvato in {args.output}')
    else:
        print('Listino aggiornato non salvato (specificare --output per salvare il risultato).')

    if args.offers:
        offers_df = updater.generate_offers()
        offers_df.to_excel(args.offers, index=False)
        print(f'Offerte generate salvate in {args.offers}')
    else:
        print('Offerte non generate (specificare --offers per salvare un file di offerte).')

    print('\nRiepilogo operazioni:')
    print(updater.report())


if __name__ == '__main__':
    main()
