import io
import os
import json
import tempfile
from typing import Dict, List, Tuple, Optional

import pandas as pd
import requests
import streamlit as st



from listino_app import ListinoUpdater
from adapters.base_adapter import BaseAdapter
from adapters.fornitore_essebidue import FornitoreEssebiDueAdapter
from adapters.pdf_generic_adapter import PDFGenericAdapter
from adapters.fornitore_xyz import FornitoreXYZAdapter

"""
Streamlit application for updating the corporate price list and generating
customer‑specific offers.

This extended version exposes two important improvements over the base
implementation:

1) **Column Mapping Confirmation** – When a supplier list is uploaded
   the app will prompt you to confirm which columns in that list
   correspond to the key fields expected by the listino.  For example,
   you can map the supplier's product code column to the internal
   ``codice`` column and the supplier's quantity column to
   ``L`` (quantità per unità di vendita).  If the adapter already
   recognises a column name, the default selection will be pre‑filled.

2) **Selective Import/Update** – After the supplier list is parsed and
   matched against the existing listino, the app shows two tables:
   one for new products not currently in the listino and one for
   existing products that would be updated.  You can select which rows
   to import or update using multi‑select controls.  Only the selected
   rows will be applied to the listino.

To activate these features, use this file as the main entry point
(`streamlit_app_drive_extended.py`) when deploying your app on
Streamlit Cloud.  The app still supports loading the master listino
directly from Google Drive if no file is uploaded.
"""

# Mapping of adapter names to their classes. Extend this dict to register
# additional supplier formats.
ADAPTERS: Dict[str, BaseAdapter] = {
    "EssebiDue (Excel/CSV)": FornitoreEssebiDueAdapter,
    "PDF generico (tabella)": PDFGenericAdapter,
    "XYZ di esempio": FornitoreXYZAdapter,
}


def _get_drive_service() -> any:
    """Create a Google Drive API service using credentials stored in st.secrets.

    Expects a dictionary or JSON string at st.secrets['gdrive']['service_account_json'].
    Returns an authorised service for the Drive v3 API with read‑only scope.
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
            url = f"https://drive.google.com/uc?export=download&id={file_id}"
          response = requests.get(url)
          response.raise_for_status()
          tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
          tmp.write(response.content)
         tmp.flush()
    return tmp.nam      


def to_tempfile(uploaded_file: any, suffix: str) -> str:
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


def confirm_column_mapping(supp_df: pd.DataFrame, defaults: Dict[str, List[str]]) -> Dict[str, str]:
    """Interactive column mapping confirmation.

    Given a supplier DataFrame and a dictionary of essential fields with
    possible default matches, prompt the user to select which column in
    the supplier data corresponds to each essential field.  If a default
    match is present in the DataFrame, it is selected by default.

    Parameters
    ----------
    supp_df : pd.DataFrame
        The supplier data as loaded by the adapter.
    defaults : Dict[str, List[str]]
        A mapping from internal field name to a list of potential column
        names expected in the supplier data.  The first matching
        element, if present, will be used as the default selection.

    Returns
    -------
    Dict[str, str]
        A mapping from internal field name to the actual column name
        chosen by the user.
    """
    mappings: Dict[str, str] = {}
    columns = supp_df.columns.tolist()
    with st.expander("Conferma mappatura colonne", expanded=True):
        st.write(
            "Per favore conferma a quali colonne del listino fornitore corrispondono i campi chiave del listino aziendale."
        )
        for field, options in defaults.items():
            # Determine default option if present in DataFrame columns
            default_option = None
            for opt in options:
                if opt in columns:
                    default_option = opt
                    break
            # Build select box label in Italian
            label = f"Colonna per {field}"
            mappings[field] = st.selectbox(
                label,
                options=columns,
                index=columns.index(default_option) if default_option else 0,
                key=f"mapping_{field}"
            )
    return mappings


def save_mapping(supplier_name: str, mapping: Dict[str, str]) -> None:
    """Persist a column mapping for a given supplier.

    The mapping will be saved to ``mappings/<supplier_name>/mapping.json``
    relative to the current working directory.  The parent
    directories are created if they do not exist.

    Parameters
    ----------
    supplier_name : str
        Identifier for the supplier, typically derived from the file name.
    mapping : Dict[str, str]
        The column mapping to persist.
    """
    dir_path = os.path.join('mappings', supplier_name)
    os.makedirs(dir_path, exist_ok=True)
    filepath = os.path.join(dir_path, 'mapping.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def load_mapping(supplier_name: str) -> Optional[Dict[str, str]]:
    """Load a previously saved column mapping for a supplier.

    If the mapping file exists, its contents are returned as a dictionary.
    Otherwise, ``None`` is returned.

    Parameters
    ----------
    supplier_name : str
        Identifier for the supplier.

    Returns
    -------
    Optional[Dict[str, str]]
        The loaded mapping dictionary, or ``None`` if not found.
    """
    filepath = os.path.join('mappings', supplier_name, 'mapping.json')
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None


def get_changes_for_confirmation(
    updater: ListinoUpdater, supplier_df: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Separate supplier rows into updates and inserts for confirmation.

    Parameters
    ----------
    updater : ListinoUpdater
        The price list updater instance (already initialised with the
        master listino).
    supplier_df : pd.DataFrame
        The supplier data after column mapping.

    Returns
    -------
    Tuple[pd.DataFrame, pd.DataFrame]
        A tuple containing two DataFrames: (updates_df, inserts_df).
        ``updates_df`` includes rows that match an existing product in
        the listino.  ``inserts_df`` includes rows that do not match
        any product in the listino.  Both DataFrames retain all
        columns from the supplier data.
    """
    update_rows: List[pd.Series] = []
    insert_rows: List[pd.Series] = []
    for _, row in supplier_df.iterrows():
        idx = updater._find_matches(row)
        if idx is None:
            insert_rows.append(row)
        else:
            update_rows.append(row)
    updates_df = pd.DataFrame(update_rows)
    inserts_df = pd.DataFrame(insert_rows)
    return updates_df, inserts_df


# Page configuration must be set before any other Streamlit command
st.set_page_config(page_title="Optima – Aggiornamento Listino", layout="wide")

st.title("🧾 Optima – Aggiornamento Listino & Offerte")

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

master_file = st.file_uploader(
    "Listino aziendale (Excel)",
    type=["xlsx", "xlsm", "xls"],
    help="Se lasci vuoto, l'app scaricherà il listino da Google Drive usando l'ID configurato nei secrets."
)

suppliers_files = st.file_uploader(
    "Listini fornitori (Excel/CSV/PDF) – puoi selezionare più file",
    type=["xlsx", "xlsm", "xls", "csv", "txt", "pdf"],
    accept_multiple_files=True,
)

if st.button("▶️ Esegui aggiornamento"):
    if not suppliers_files:
        st.error("Carica almeno **un listino fornitore** per procedere.")
        st.stop()
    # Determine master listino path
    if master_file is not None:
        master_path = to_tempfile(master_file, ".xlsx")
    else:
        gconf = st.secrets.get("gdrive", {})
        file_id_default = gconf.get("file_id_listino", "")
        if not file_id_default:
            st.error("File ID del listino mancante nei secrets (imposta gdrive.file_id_listino).")
            st.stop()
        try:
            master_path = download_drive_file(file_id_default, ".xlsx")
            st.success("Listino aziendale caricato da Google Drive.")
        except Exception as e:
            st.error(f"Errore durante il download del listino da Google Drive: {e}")
            st.stop()
    # Initialiser updater
    updater = ListinoUpdater(master_path)
    adapter_cls = ADAPTERS[adapter_name]
    adapter: BaseAdapter = adapter_cls()
    total_updated = 0
    total_inserted = 0
    # We'll accumulate updated and inserted counts across all suppliers
    for supp_file in suppliers_files:
        suffix = os.path.splitext(supp_file.name)[1].lower() or ".bin"
        supp_path = to_tempfile(supp_file, suffix)
        try:
            supp_df = adapter.parse_supplier_file(supp_path)
        except Exception as e:
            st.warning(f"Impossibile leggere **{supp_file.name}** con l'adapter selezionato: {e}")
            continue
        # Prepare list of essential fields and default column names for mapping
        essential_fields: Dict[str, List[str]] = {
            'codice': ['codice', 'Codice', 'Cod.', 'Cod'],
            'codice fornitore': ['codice fornitore', 'Cod.Fornitore', 'Codice Fornitore', 'CodiceForn', 'Fornitore'],
            'L': ['L', 'Quantità', 'Q', "quantità in base all'unità"],
            'prezzo di listino': ['prezzo di listino', 'Prezzo', 'Listino', 'Prezzo listino'],
            'Descrizione articolo': ['Descrizione articolo', 'Descrizione', 'Articolo']
        }
        # Determine supplier name from file (without extension) for mapping persistence
        supplier_name = os.path.splitext(os.path.basename(supp_file.name))[0]
        # Attempt to load a previously saved mapping for this supplier
        saved_mapping = load_mapping(supplier_name)
        if saved_mapping:
            st.info(f"È stata trovata una mappatura salvata per **{supplier_name}**. Verrà usata automaticamente.")
            # Apply saved mapping by renaming supplier columns to internal names
            rename_map = {saved_mapping[field]: field for field in saved_mapping if saved_mapping[field] in supp_df.columns}
            supp_df = supp_df.rename(columns=rename_map)
        else:
            # Check if any essential field is missing; if so, ask for mapping interactively
            missing_fields = [f for f in essential_fields if f not in supp_df.columns]
            if missing_fields:
                st.info(f"Mappatura colonne per **{supp_file.name}** (verrà salvata per usi futuri):")
                mapping = confirm_column_mapping(supp_df, essential_fields)
                # Save the mapping for future runs
                save_mapping(supplier_name, mapping)
                # Rename columns according to the mapping
                # Invert the mapping (internal field -> selected column) to (selected column -> internal field)
                inv_map = {v: k for k, v in mapping.items()}
                supp_df = supp_df.rename(columns=inv_map)
        # Split into updates/inserts for user confirmation
        updates_df, inserts_df = get_changes_for_confirmation(updater, supp_df)
        # Display tables and let user select rows
        # New products
        if not inserts_df.empty:
            st.subheader(f"Prodotti NUOVI da {supp_file.name}")
            st.write("Seleziona i prodotti da importare nel listino.")
            new_codes = inserts_df['codice'].tolist() if 'codice' in inserts_df.columns else inserts_df.index.astype(str).tolist()
            selected_new = st.multiselect(
                "Seleziona codici nuovi da importare", new_codes, default=new_codes, key=f"sel_new_{supp_file.name}"
            )
        else:
            selected_new = []
        # Existing products
        if not updates_df.empty:
            st.subheader(f"Prodotti ESISTENTI da {supp_file.name}")
            st.write("Seleziona i prodotti da aggiornare nel listino.")
            update_codes = updates_df['codice'].tolist() if 'codice' in updates_df.columns else updates_df.index.astype(str).tolist()
            selected_update = st.multiselect(
                "Seleziona codici esistenti da aggiornare", update_codes, default=update_codes, key=f"sel_upd_{supp_file.name}"
            )
        else:
            selected_update = []
        # Apply selected updates and inserts
        # Filter supplier dataframe to only rows with selected codes
        if selected_update:
            df_update_sel = updates_df[updates_df['codice'].isin(selected_update)] if 'codice' in updates_df.columns else updates_df.loc[updates_df.index.astype(str).isin(selected_update)]
        else:
            df_update_sel = pd.DataFrame(columns=supp_df.columns)
        if selected_new:
            df_insert_sel = inserts_df[inserts_df['codice'].isin(selected_new)] if 'codice' in inserts_df.columns else inserts_df.loc[inserts_df.index.astype(str).isin(selected_new)]
        else:
            df_insert_sel = pd.DataFrame(columns=supp_df.columns)
        # Apply updates/inserts to updater
        before_u = len(set(updater.updated_rows))
        before_i = len(updater.inserted_rows)
        if not df_update_sel.empty:
            updater.update_existing_products(df_update_sel)
        if not df_insert_sel.empty:
            updater.add_new_products(df_insert_sel)
        total_updated += len(set(updater.updated_rows)) - before_u
        total_inserted += len(updater.inserted_rows) - before_i
    # Display results
    st.subheader("Risultati complessivi")
    c1, c2, c3 = st.columns(3)
    c1.metric("Righe aggiornate", f"{total_updated}")
    c2.metric("Nuove righe inserite", f"{total_inserted}")
    c3.metric("Totale righe", f"{len(updater.df)}")
    st.write("**Anteprima listino aggiornato**")
    st.dataframe(updater.df.head(50), use_container_width=True)
    # Generate offers and preview
    try:
        offers_df = updater.generate_offers()
        st.write("**Anteprima offerte**")
        st.dataframe(offers_df.head(50), use_container_width=True)
    except Exception as e:
        st.warning(f"Offerte non generate: {e}")
        offers_df = None
    # Download buttons
    st.subheader("Download")
    upd_bytes = save_excel_download(updater.df, "listino_aggiornato.xlsx")
    st.download_button(
        "⬇️ Scarica listino_aggiornato.xlsx",
        data=upd_bytes,
        file_name="listino_aggiornato.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    if offers_df is not None:
        off_bytes = save_excel_download(offers_df, "offerte.xlsx")
        st.download_button(
            "⬇️ Scarica offerte.xlsx",
            data=off_bytes,
            file_name="offerte.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
