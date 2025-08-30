import io
import os
import tempfile

import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from listino_app import ListinoUpdater
from adapters.base_adapter import BaseAdapter
from adapters.fornitore_essebidue import FornitoreEssebiDueAdapter
from adapters.pdf_generic_adapter import PDFGenericAdapter
from adapters.fornitore_xyz import FornitoreXYZAdapter

# Set page configuration for Streamlit
st.set_page_config(page_title="Optima – Aggiornamento Listino", layout="wide")


"""
Streamlit application for updating the corporate price list and generating
 
directly from Google Drive when no file is uploaded by the user. A service
account credential and a default file ID must be stored in st.secrets under
the key `gdrive` (see README for details).

Features:
  • Upload one or more supplier lists (Excel/CSV/PDF) and update the
    corporate listino accordingly.
  • Automatically download the master listino from Google Drive if no file
    is uploaded via the UI. The file ID can be configured via
    st.secrets['gdrive']['file_id_listino'].
  • Preview the first 50 rows of the updated listino and generated offers.
  • Download the updated listino and offers as Excel files.

Adapters for supplier lists live in the `adapters` package. To add a new
supplier format, implement a new adapter class inheriting from BaseAdapter.
"""

# Mapping of adapter names to their classes. Extend this dict to register
# additional supplier formats.
ADAPTERS = {
    "EssebiDue (Excel/CSV)": FornitoreEssebiDueAdapter,
    "PDF generico (tabella)": PDFGenericAdapter,
    "XYZ di esempio": FornitoreXYZAdapter,
}


def _get_drive_service():
    """Create a Google Drive API service using credentials stored in st.secrets.

    Expects a dictionary or JSON string at st.secrets['gdrive']['service_account_json'].
    Returns an authorized service for the Drive v3 API with read‑only scope.
    """
    gconf = st.secrets.get("gdrive", {})
    sa_json = gconf.get("service_account_json")
    if not sa_json:
        raise RuntimeError(
            "gdrive.service_account_json mancante nei secrets. Configura le credenziali del service account."
        )
    # service_account accepts either a dict or a JSON string
    if isinstance(sa_json, str):
        import json
        creds_info = json.loads(sa_json)
    else:
        creds_info = sa_json
    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds)


def download_drive_file(file_id: str, suffix: str = ".xlsx") -> str:
    """Download a file from Google Drive and write it to a temporary file.

    Parameters
    ----------
    file_id: str
        The ID of the file in Google Drive to download.
    suffix: str
        The file suffix used for the temporary file (e.g. `.xlsx`).

    Returns
    -------
    str
        The path to the downloaded temporary file on the local filesystem.
    """
    service = _get_drive_service()
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(fh.getvalue())
    tmp.flush()
    return tmp.name


def to_tempfile(uploaded_file, suffix: str) -> str:
    """Save an UploadedFile from Streamlit to a temporary file and return its path."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.read())
    tmp.flush()
    return tmp.name


def save_excel_download(df: pd.DataFrame, filename: str) -> bytes:
    """Serialize a pandas DataFrame to an Excel file and return the bytes."""
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return bio.getvalue()


# Streamlit UI setup

st.title("🗖 Optima – Aggiornamento Listino & Offerte")

with st.sidebar:
    st.header("Origine dati")
    adapter_name = st.selectbox(
        "Adapter listino fornitore",
        list(ADAPTERS.keys()),
        index=0,
        help="Scegli il formato del listino fornitore. Gli adapter si trovano in /adapters."
    )
    st.caption(
        "Carica almeno un listino fornitore. Se non carichi il listino aziendale, verrà scaricato da Google Drive tramite l'ID configurato nei secrets."
    )

# File uploader for the master listino (optional). If omitted, we will download it from Drive.
master_file = st.file_uploader(
    "Listino aziendale (Excel)",
    type=["xlsx", "xlsm", "xls"],
    help="Se lasci vuoto, l'app scaricherà il listino da Google Drive usando l'ID configurato nei secrets."
)

# Multiple file uploader for supplier lists (required)
suppliers_files = st.file_uploader(
    "Listini fornitori (Excel/CSV/PDF) – puoi selezionare più file",
    type=["xlsx", "xlsm", "xls", "csv", "txt", "pdf"],
    accept_multiple_files=True,
)


if st.button("▶️ Esegui aggiornamento"):
    # Validate at least one supplier file
    if not suppliers_files:
        st.error("Carica almeno **un listino fornitore** per procedere.")
        st.stop()

    # Determine the path to the master listino
    if master_file is not None:
        # Use the uploaded file
        master_path = to_tempfile(master_file, ".xlsx")
    else:
        # Load from Google Drive using the file ID in secrets
        gconf = st.secrets.get("gdrive", {})
        file_id_default = gconf.get("file_id_listino", "")
        if not file_id_default:
            st.error(
                "File ID del listino mancante nei secrets (imposta gdrive.file_id_listino)."
            )
            st.stop()
        try:
            master_path = download_drive_file(file_id_default, ".xlsx")
            st.success("Listino aziendale caricato da Google Drive.")
        except Exception as e:
            st.error(f"Errore durante il download del listino da Google Drive: {e}")
            st.stop()

    # Initialize updater and adapter
    updater = ListinoUpdater(master_path)
    adapter_cls = ADAPTERS[adapter_name]
    adapter: BaseAdapter = adapter_cls()
    updated = 0
    inserted = 0

    # Process each supplier file
    for up in suppliers_files:
        suffix = os.path.splitext(up.name)[1].lower() or ".bin"
        supplier_path = to_tempfile(up, suffix)
        try:
            supp_df = adapter.parse_supplier_file(supplier_path)
        except Exception as e:
            st.warning(
                f"Impossibile leggere **{up.name}** con l'adapter selezionato: {e}"
            )
            continue
        before_u = len(set(updater.updated_rows))
        before_i = len(updater.inserted_rows)
        try:
            updater.update_existing_products(supp_df)
            updater.add_new_products(supp_df)
        except Exception as e:
            st.error(f"Errore durante l'applicazione di **{up.name}**: {e}")
            continue
        updated += len(set(updater.updated_rows)) - before_u
        inserted += len(updater.inserted_rows) - before_i

    # Display metrics and preview of updated listino
    st.subheader("Risultati")
    c1, c2, c3 = st.columns(3)
    c1.metric("Righe aggiornate", f"{updated}")
    c2.metric("Nuove righe inserite", f"{inserted}")
    c3.metric("Totale righe", f"{len(updater.df)}")

    st.write("**Anteprima listino aggiornato**")
    st.dataframe(updater.df.head(50), use_container_width=True)

    # Generate offers and display preview
    try:
        offers_df = updater.generate_offers()
        st.write("**Anteprima offerte**")
        st.dataframe(offers_df.head(50), use_container_width=True)
    except Exception as e:
        st.warning(f"Offerte non generate: {e}")
        offers_df = None

    # Provide download buttons for updated list and offers
    st.subheader("Download")
    updated_bytes = save_excel_download(updater.df, "listino_aggiornato.xlsx")
    st.download_button(
        "⬇️ Scarica listino_aggiornato.xlsx",
        data=updated_bytes,
        file_name="listino_aggiornato.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    if offers_df is not None:
        offers_bytes = save_excel_download(offers_df, "offerte.xlsx")
        st.download_button(
            "⬇️ Scarica offerte.xlsx",
            data=offers_bytes,
            file_name="offerte.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
