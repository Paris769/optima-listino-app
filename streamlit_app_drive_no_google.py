import streamlit as st
import pandas as pd
import requests
import tempfile
from typing import Optional

# Optional import of pypdf if available
try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

"""
This Streamlit application provides a simplified interface for updating product price lists.

Key features:
  * Uses `requests` to download files from Google Drive via a public link (no Google API).
  * Supports reading Excel files via `pandas`/`openpyxl`.
  * Supports reading simple PDF price lists via `pypdf` if installed (optional).
  * Allows users to upload their own internal price list and a supplier price list, preview them,
    and download the updated list as a CSV.

The code has been designed to be compatible with Python 3.13 and avoids using any
libraries not available in Streamlit Cloud by default. If you need to parse complex
PDF tables, consider adding a custom adapter in the `adapters/` directory.
"""


def download_drive_file_simple(file_id: str, suffix: str = ".xlsx") -> str:
    """Download a file from Google Drive using a simple HTTP request.

    This function avoids using the Google API client, which is incompatible with
    Python 3.13 on Streamlit Cloud. Instead, it constructs a direct download
    URL and retrieves the content using `requests`. The downloaded content is
    written to a temporary file and the path to that file is returned.

    Args:
        file_id: The ID of the file on Google Drive (the long string after `id=`
            in a share link).
        suffix: Optional suffix for the temporary filename (default: `.xlsx`).

    Returns:
        Path to the temporary file containing the downloaded content.
    """
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(url)
    response.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(response.content)
    tmp.flush()
    return tmp.name


def to_tempfile(uploaded_file, suffix: str = "") -> Optional[str]:
    """Save a Streamlit UploadedFile to a temporary file and return its path.

    Args:
        uploaded_file: A file-like object returned by `st.file_uploader`.
        suffix: Optional suffix for the temporary file (e.g. `.xlsx` or `.pdf`).

    Returns:
        Path to a temporary file if `uploaded_file` is not None; otherwise None.
    """
    if uploaded_file is None:
        return None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.read())
    tmp.flush()
    return tmp.name


def parse_pdf_to_dataframe(pdf_path: str) -> pd.DataFrame:
    """Attempt to extract lines of text from a PDF into a DataFrame.

    This is a very basic PDF parser using `pypdf.PdfReader`. It reads each page,
    splits the extracted text into lines, and returns a DataFrame with a single
    column called "text". For more robust table extraction, you should implement
    a custom adapter (see `adapters/pdf_generic_adapter_pypdf.py`).
    """
    if not HAS_PYPDF:
        return pd.DataFrame()
    reader = pypdf.PdfReader(pdf_path)
    lines = []
    for page in reader.pages:
        text = page.extract_text() or ""
        lines.extend(text.splitlines())
    return pd.DataFrame({"text": lines})


def main() -> None:
    """Main entry point for the Streamlit app."""
    st.set_page_config(page_title="Optima – Aggiornamento Listino", layout="wide")
    st.title("Aggiornamento Listino Prezzi")

    st.write(
        """
        Questa applicazione permette di confrontare il tuo listino interno con il listino
        di un fornitore. Puoi caricare un file Excel per il listino interno e un file Excel
        o PDF per il listino del fornitore. L'app mostrerà un'anteprima dei dati caricati.
        """
    )

    # Section: Download listino from Google Drive if ID is provided
    with st.expander("Scarica listino da Google Drive (opzionale)"):
        file_id = st.text_input(
            "Inserisci l'ID del file di Google Drive (facoltativo):",
            placeholder="e.g. 1AbCdEfGhIjK...",
        )
        if file_id:
            suffix = st.text_input("Estensione del file (includere il punto)", value=".xlsx")
            if st.button("Scarica da Drive"):
                try:
                    path = download_drive_file_simple(file_id, suffix=suffix)
                    st.success(f"File scaricato in: {path}")
                except Exception as e:
                    st.error(f"Errore nel download: {e}")

    # Upload internal price list
    st.header("Carica listino interno (Excel)")
    internal_file = st.file_uploader(
        "Seleziona il file Excel del tuo listino interno", type=["xlsx", "xls"], key="internal"
    )
    df_internal = None
    if internal_file:
        internal_path = to_tempfile(internal_file, suffix=".xlsx")
        try:
            df_internal = pd.read_excel(internal_path)
            st.subheader("Anteprima listino interno")
            st.dataframe(df_internal.head())
        except Exception as e:
            st.error(f"Impossibile leggere il file Excel: {e}")

    # Upload vendor price list
    st.header("Carica listino fornitore (Excel o PDF)")
    vendor_file = st.file_uploader(
        "Seleziona il file del fornitore (Excel o PDF)",
        type=["xlsx", "xls", "pdf"],
        key="vendor",
    )
    df_vendor = None
    if vendor_file:
        if vendor_file.name.lower().endswith(".pdf"):
            pdf_path = to_tempfile(vendor_file, suffix=".pdf")
            df_vendor = parse_pdf_to_dataframe(pdf_path)
        else:
            vendor_path = to_tempfile(vendor_file, suffix=".xlsx")
            try:
                df_vendor = pd.read_excel(vendor_path)
            except Exception:
                df_vendor = None
        if df_vendor is not None:
            st.subheader("Anteprima listino fornitore")
            st.dataframe(df_vendor.head())

    # Placeholder for further comparison logic (e.g. fuzzy matching, column mapping, updating prices)
    if df_internal is not None and df_vendor is not None:
        st.header("Prossimi passi")
        st.info(
            "Le funzionalità di confronto e aggiornamento del listino non sono ancora implementate in questa versione semplificata."
        )


if __name__ == "__main__":
    main()
