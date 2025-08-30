# streamlit_app.py
import io, tempfile, os
import pandas as pd
import streamlit as st

from listino_app import ListinoUpdater
from adapters.base_adapter import BaseAdapter
from adapters.fornitore_essebidue import FornitoreEssebiDueAdapter
from adapters.pdf_generic_adapter import PDFGenericAdapter
from adapters.fornitore_xyz import FornitoreXYZAdapter  # demo

ADAPTERS = {
    "EssebiDue (Excel/CSV)": FornitoreEssebiDueAdapter,
    "PDF generico (tabella)": PDFGenericAdapter,
    "XYZ di esempio": FornitoreXYZAdapter,
}

st.set_page_config(page_title="Optima – Aggiornamento Listino", layout="wide")
st.title("\U0001F3E3 Optima – Aggiornamento Listino & Offerte")

with st.sidebar:
    st.header("Impostazioni")
    adapter_name = st.selectbox("Scegli adapter fornitore", list(ADAPTERS.keys()), index=0)
    st.caption("Gli adapter personalizzati sono in /adapters. Possiamo aggiungerne altri in seguito.")

st.subheader("1) Carica file")
c1, c2 = st.columns(2)
with c1:
    master_file = st.file_uploader("Listino aziendale (Excel)", type=["xlsx", "xlsm", "xls"])
with c2:
    suppliers_files = st.file_uploader(
        "Listini fornitori (Excel/CSV/PDF) – puoi selezionare più file",
        type=["xlsx", "xlsm", "xls", "csv", "txt", "pdf"], accept_multiple_files=True
    )

run = st.button("\u25B6\uFE0F Esegui aggiornamento")

def to_tempfile(uploaded, suffix):
    """Scrive l'UploadedFile su un temporaneo e ritorna il path."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded.read())
    tmp.flush()
    return tmp.name

def save_excel_download(df: pd.DataFrame, filename: str) -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return bio.getvalue()

if run:
    if not master_file or not suppliers_files:
        st.error("Carica sia il **listino aziendale** sia almeno **un listino fornitore**.")
        st.stop()

    master_path = to_tempfile(master_file, ".xlsx")
    updater = ListinoUpdater(master_path)

    adapter_cls = ADAPTERS[adapter_name]
    adapter: BaseAdapter = adapter_cls()

    updated = 0
    inserted = 0

    for up in suppliers_files:
        suffix = os.path.splitext(up.name)[1].lower() or ".bin"
        supplier_path = to_tempfile(up, suffix)
        try:
            supp_df = adapter.parse_supplier_file(supplier_path)
        except Exception as e:
            st.warning(f"Impossibile leggere **{up.name}** con l'adapter selezionato: {e}")
            continue
        before_u = len(set(updater.updated_rows))
        before_i = len(updater.inserted_rows)
        try:
            updater.update_existing_products(supp_df)
            updater.add_new_products(supp_df)
        except Exception as e:
            st.error(f"Errore durante l'applicazione di **{up.name}**: {e}")
            continue
        after_u = len(set(updater.updated_rows))
        after_i = len(updater.inserted_rows)
        updated += (after_u - before_u)
        inserted += (after_i - before_i)

    st.subheader("2) Risultati")
    c3, c4, c5 = st.columns(3)
    c3.metric("Righe aggiornate", f"{updated}")
    c4.metric("Nuove righe inserite", f"{inserted}")
    c5.metric("Totale righe", f"{len(updater.df)}")

    st.write("**Anteprima listino aggiornato**")
    st.dataframe(updater.df.head(50), use_container_width=True)

    try:
        offers_df = updater.generate_offers()
        st.write("**Anteprima offerte**")
        st.dataframe(offers_df.head(50), use_container_width=True)
    except Exception as e:
        st.warning(f"Offerte non generate: {e}")
        offers_df = None

    st.subheader("3) Download")
    updated_bytes = save_excel_download(updater.df, "listino_aggiornato.xlsx")
    st.download_button("\u2B07\uFE0F Scarica listino_aggiornato.xlsx",
                       data=updated_bytes, file_name="listino_aggiornato.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if offers_df is not None:
        offers_bytes = save_excel_download(offers_df, "offerte.xlsx")
        st.download_button("\u2B07\uFE0F Scarica offerte.xlsx",
                           data=offers_bytes, file_name="offerte.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.info(updater.report())
