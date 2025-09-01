import pandas as pd
import streamlit as st
import requests
import tempfile
from pypdf import PdfReader


def download_drive_file_simple(file_id, suffix=".xlsx"):
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(url)
    response.raise_for_status()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(response.content)
        tmp.flush()
        return tmp.name


def to_tempfile(uploaded_file, suffix=".xlsx"):
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.read())
        tmp.flush()
        return tmp.name


def parse_pdf_to_dataframe(pdf_path):
    reader = PdfReader(pdf_path)
    lines = []
    for page in reader.pages:
        text = page.extract_text() or ""
        lines.extend(text.splitlines())
    return pd.DataFrame({"text": lines})


def main() -> None:
    st.set_page_config(page_title="Optima - Aggiornamento Listino Prezzi")
    st.title("Aggiornamento Listino Prezzi")
    st.write(
        """
        Questa applicazione permette di confrontare il tuo listino interno con il listino di un fornitore.
        Puoi caricare un file Excel o CSV per il listino interno e un file Excel, CSV o PDF per il listino del fornitore.
        L'app mostrerà una prima anteprima dei dati caricati.
        """
    )

    # Sezione download opzionale da Google Drive
    with st.expander("Scarica listino da Google Drive (opzionale):"):
        file_id = st.text_input(
            "Inserisci l'ID del file di Google Drive (facoltativo)",
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

    # Carica listino interno
    st.header("Carica listino interno (Excel o CSV)")
    internal_file = st.file_uploader(
        "Seleziona il file del tuo listino interno",
        type=["xlsx", "xls", "csv"],
        key="internal",
    )

    df_internal = None
    if internal_file:
        name = internal_file.name.lower()
        if name.endswith(".csv"):
            internal_path = to_tempfile(internal_file, suffix=".csv")
            try:
                df_internal = pd.read_csv(internal_path)
            except Exception as e:
                st.error(f"Errore nel caricamento del listino interno: {e}")
        else:
            internal_path = to_tempfile(internal_file, suffix=".xlsx")
            try:
                df_internal = pd.read_excel(internal_path)
            except Exception:
                try:
                    df_internal = pd.read_csv(internal_path)
                except Exception as e:
                    st.error(f"Errore nel caricamento del listino interno: {e}")
        if df_internal is not None:
            st.subheader("Anteprima listino interno")
            st.dataframe(df_internal.head())

    # Carica listino fornitore
    st.header("Carica listino fornitore (Excel, CSV o PDF)")
    vendor_file = st.file_uploader(
        "Seleziona il file del fornitore",
        type=["xlsx", "xls", "csv", "pdf"],
        key="vendor",
    )

    df_vendor = None
    if vendor_file:
        vname = vendor_file.name.lower()
        if vname.endswith(".pdf"):
            pdf_path = to_tempfile(vendor_file, suffix=".pdf")
            try:
                df_vendor = parse_pdf_to_dataframe(pdf_path)
            except Exception as e:
                st.error(f"Errore nel caricamento del PDF del fornitore: {e}")
        elif vname.endswith(".csv"):
            vendor_path = to_tempfile(vendor_file, suffix=".csv")
            try:
                df_vendor = pd.read_csv(vendor_path)
            except Exception as e:
                st.error(f"Errore nel caricamento del listino fornitore: {e}")
        else:
            vendor_path = to_tempfile(vendor_file, suffix=".xlsx")
            try:
                df_vendor = pd.read_excel(vendor_path)
            except Exception:
                try:
                    df_vendor = pd.read_csv(vendor_path)
                except Exception as e:
                    st.error(f"Errore nel caricamento del listino fornitore: {e}")
        if df_vendor is not None:
            st.subheader("Anteprima listino fornitore")
            st.dataframe(df_vendor.head())

    # Placeholder per la logica di confronto
    if df_internal is not None and df_vendor is not None:
        st.header("Prossimi passi")
        st.info(
            "Le funzionalità di confronto e aggiornamento del listino non sono ancora implementate in questa versione semplificata."
        )


if __name__ == "__main__":
    main()
