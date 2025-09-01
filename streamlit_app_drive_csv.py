from __future__ import annotations
import io
import re
import tempfile
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from rapidfuzz import process, fuzz

# ============ UTIL ============

NUMERIC_COL_HINTS = {"€ cf", "€ cl", "€ cf.", "€ cl.", "prezzo", "price", "costo", "costo standard", "iva", "qty", "q.tà", "quantità", "quantity"}
CODE_COL_HINTS = {"cod", "codice", "code", "sku", "articolo", "id"}
DESC_COL_HINTS = {"descrizione", "description", "articolo", "nome", "prodotto"}
EAN_COL_HINTS = {"ean", "barcode", "bar code", "gtin"}
BRAND_COL_HINTS = {"brand", "marca"}
QTY_COL_HINTS = {"qty", "qtà", "qta", "quantità", "quantity"}
HEADER_MAX_PEEK = 15  # righe da mostrare per scegliere l'intestazione


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).strip().lower())


def _best_guess(target: str, candidates: List[str], scorer=fuzz.WRatio, cutoff: int = 72) -> Optional[str]:
    if not candidates:
        return None
    res = process.extractOne(target, candidates, scorer=scorer)
    if res and res[1] >= cutoff:
        return res[0]
    return None


def _guess_by_vocab(cands: List[str], vocab: set[str]) -> Optional[str]:
    cands_n = {c: _normalize(c) for c in cands}
    for col, n in cands_n.items():
        tokens = set(n.split())
        if tokens & vocab:
            return col
    return None


def _to_number(s):
    if pd.isna(s):
        return None
    # rimuove euro, spazi, punti migliaia, converte virgola in punto
    x = str(s).replace("€", "").replace(" ", "")
    # punto come separatore decimale/ migliaia misti: toglie . se usato come migliaia
    x = re.sub(r"\.(?=\d{3}(?:\D|$))", "", x)
    x = x.replace(",", ".")
    try:
        return float(x)
    except Exception:
        return None


def _read_any_table(uploaded_file, sheet: Optional[str | int], header_row_idx: Optional[int]) -> Tuple[pd.DataFrame, List[str]]:
    """Legge Excel o CSV. sheet può essere nome o indice. header_row_idx è 0-based all'interno del file (post skiprows)."""
    name = uploaded_file.name.lower()
    notes: List[str] = []

    if name.endswith(".csv"):
        raw = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        df_peek = pd.read_csv(io.StringIO(raw), header=None)
        # preview + scelta header fuori da qui, ma se già nota header_row_idx:
        if header_row_idx is None:
            header_row_idx = 0
        df = pd.read_csv(io.StringIO(raw), header=header_row_idx)
        return df, notes

    # Excel
    xls = pd.ExcelFile(uploaded_file)
    sheets = xls.sheet_names
    if sheet is None:
        sheet = sheets[0]
    if isinstance(sheet, str) and sheet not in sheets:
        sheet = sheets[0]

    # se header non specificato, metti None (pandas creerà 0..n)
    if header_row_idx is None:
        df = pd.read_excel(xls, sheet_name=sheet, header=None)
    else:
        df = pd.read_excel(xls, sheet_name=sheet, header=header_row_idx)

    return df, notes


def _make_header_selection(df_raw: pd.DataFrame, key_prefix: str) -> int:
    st.caption("Scegli la **riga di intestazione** (0-based nel preview) — le righe sopra verranno scartate")
    st.dataframe(df_raw.head(HEADER_MAX_PEEK))
    # Use a unique key for each header selector to avoid DuplicateWidgetID errors when multiple
    # number_input widgets are rendered (e.g., for both internal and supplier previews).
    header_idx = st.number_input(
        "Riga intestazione",
        min_value=0,
        max_value=max(0, len(df_raw) - 1),
        value=0,
        step=1,
        key=f"{key_prefix}_hdr_idx",
    )
    return int(header_idx)


def _reparse_with_header(uploaded_file, sheet_choice, header_row_idx) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        raw = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        return pd.read_csv(io.StringIO(raw), header=header_row_idx)
    xls = pd.ExcelFile(uploaded_file)
    return pd.read_excel(xls, sheet_name=sheet_choice, header=header_row_idx)


def _suggest_mapping(cols: List[str], role: str) -> Dict[str, str]:
    """Suggerisce mappature per i campi canonici."""
    suggestions: Dict[str, str] = {}

    def guess(vocab, fallback_best_of=None):
        m = _guess_by_vocab(cols, vocab)
        if not m and fallback_best_of:
            m = _best_guess(fallback_best_of, cols, cutoff=70)
        return m

    if role == "internal":
        suggestions["code"] = guess(CODE_COL_HINTS, "codice")
        suggestions["desc"] = guess(DESC_COL_HINTS, "descrizione")
        suggestions["ean"] = guess(EAN_COL_HINTS, "ean")
        suggestions["price"] = guess(NUMERIC_COL_HINTS, "prezzo")
        suggestions["qty"] = guess(QTY_COL_HINTS, "quantità")
        suggestions["vat"] = guess({"iva"}, "iva")
    else:
        suggestions["code"] = guess(CODE_COL_HINTS, "cod")
        suggestions["desc"] = guess(DESC_COL_HINTS, "articolo")
        # in molti listini fornitore i prezzi sono € Cf (costo fornitore) / € Cl (prezzo al cliente)
        suggestions["price_cost"] = _best_guess("€ cf", cols) or guess(NUMERIC_COL_HINTS, "costo")
        suggestions["price_list"] = _best_guess("€ cl", cols) or guess(NUMERIC_COL_HINTS, "prezzo")
        suggestions["ean"] = guess(EAN_COL_HINTS, "ean")
        suggestions["brand"] = guess(BRAND_COL_HINTS, "marca")
        suggestions["qty"] = guess(QTY_COL_HINTS, "quantità")
        suggestions["vat"] = guess({"iva"}, "iva")
    # rimuovi None
    return {k: v for k, v in suggestions.items() if v}


def _cast_numeric(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = df[c].map(_to_number)
    return df


def _download_excel(df: pd.DataFrame, filename="output.xlsx") -> None:
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="Aggiornato")
    st.download_button("⬇️ Scarica output Excel", data=buff.getvalue(),
                       file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ============ UI ============

st.set_page_config(page_title="Optima · Aggiornamento Listino", page_icon="💼", layout="wide")
st.title("Aggiornamento listino · Preview + Mappatura colonne")

with st.expander("ℹ️ Istruzioni rapide", expanded=False):
    st.markdown("""
- Carica **Listino di vendita (azienda)** e **Listino fornitore** (Excel/CSV; PDF supportato solo per anteprima con pypdf).
- Scegli **foglio** e **riga intestazione** se sopra ci sono righe di testo.
- **Mappa manualmente** le colonne (ti propongo suggerimenti automatici).
- Esegui il **matching** per *codice* (fallback su *EAN*) e scarica l'**output Excel**.
""")

colA, colB = st.columns(2, gap="large")

# --- Upload interno
with colA:
    st.subheader("Carica listino **vendita** (azienda)")
    file_int = st.file_uploader("Seleziona file aziendale (Excel/CSV)", type=["xlsx", "xls", "csv"], key="file_int")
    df_int = None
    if file_int:
        name = file_int.name.lower()
        if name.endswith(".csv"):
            df_raw, _ = _read_any_table(file_int, None, None)
            st.caption("Anteprima grezza (CSV, header assente finché non lo imposti sotto)")
            st.dataframe(df_raw.head(HEADER_MAX_PEEK))
            hdr_idx = _make_header_selection(df_raw, "intcsv")
            df_int = _reparse_with_header(file_int, None, hdr_idx)
        else:
            xls = pd.ExcelFile(file_int)
            sheet = st.selectbox("Foglio", options=xls.sheet_names, index=0, key="sheet_int")
            df_raw = pd.read_excel(xls, sheet_name=sheet, header=None)
            st.caption("Anteprima grezza (Excel senza header; scegli la riga intestazione sotto)")
            st.dataframe(df_raw.head(HEADER_MAX_PEEK))
            hdr_idx = _make_header_selection(df_raw, "intexc")
            df_int = _reparse_with_header(file_int, sheet, hdr_idx)

        st.success(f"Caricato listino interno • {df_int.shape[0]} righe × {df_int.shape[1]} colonne")
        st.dataframe(df_int.head(10), use_container_width=True)

# --- Upload fornitore
with colB:
    st.subheader("Carica listino **fornitore** (Excel, CSV o PDF)")
    file_sup = st.file_uploader("Seleziona file fornitore", type=["xlsx", "xls", "csv", "pdf"], key="file_sup")
    df_sup = None

    if file_sup:
        if file_sup.name.lower().endswith(".pdf"):
            st.warning("Supporto PDF di sola lettura (estrazione semplice). Converti in Excel/CSV per risultati robusti.")
            try:
                from pypdf import PdfReader
                text = []
                reader = PdfReader(io.BytesIO(file_sup.getvalue()))
                for page in reader.pages:
                    t = page.extract_text() or ""
                    text.append(t)
                preview = "\n".join(text[:2])[:2000]
                st.text_area("Anteprima testo PDF (prime pagine)", preview, height=200)
            except Exception as e:
                st.error(f"Impossibile leggere il PDF: {e}")
        else:
            name = file_sup.name.lower()
            if name.endswith(".csv"):
                df_raw, _ = _read_any_table(file_sup, None, None)
                st.caption("Anteprima grezza (CSV, header assente finché non lo imposti sotto)")
                st.dataframe(df_raw.head(HEADER_MAX_PEEK))
                hdr_idx = _make_header_selection(df_raw, "supcsv")
                df_sup = _reparse_with_header(file_sup, None, hdr_idx)
            else:
                xls = pd.ExcelFile(file_sup)
                sheet = st.selectbox("Foglio fornitore", options=xls.sheet_names, index=0, key="sheet_sup")
                df_raw = pd.read_excel(xls, sheet_name=sheet, header=None)
                st.caption("Anteprima grezza (Excel senza header; scegli la riga intestazione sotto)")
                st.dataframe(df_raw.head(HEADER_MAX_PEEK))
                hdr_idx = _make_header_selection(df_raw, "supexc")
                df_sup = _reparse_with_header(file_sup, sheet, hdr_idx)

            st.success(f"Caricato listino fornitore • {df_sup.shape[0]} righe × {df_sup.shape[1]} colonne")
            st.dataframe(df_sup.head(10), use_container_width=True)

st.divider()

# --- MAPPATURA COLONNE
if (file_int and df_int is not None) and (file_sup and df_sup is not None):
    st.header("🔗 Mappatura manuale colonne (con suggerimenti)")

    cols_int = list(map(str, df_int.columns))
    cols_sup = list(map(str, df_sup.columns))

    sugg_int = _suggest_mapping(cols_int, "internal")
    sugg_sup = _suggest_mapping(cols_sup, "supplier")

    with st.form("mapping"):
        st.subheader("Listino **vendita** (azienda)")
        c1, c2, c3, c4 = st.columns(4)
        mi_code = c1.selectbox("Colonna **CODICE**", cols_int, index=cols_int.index(sugg_int.get("code", cols_int[0])) if cols_int else 0)
        mi_desc = c2.selectbox("Colonna **DESCRIZIONE**", cols_int, index=cols_int.index(sugg_int.get("desc", cols_int[0])) if cols_int else 0)
        mi_price = c3.selectbox("Colonna **PREZZO VENDITA**", cols_int, index=cols_int.index(sugg_int.get("price", cols_int[0])) if cols_int else 0)
        mi_ean = c4.selectbox("Colonna **EAN** (opz.)", ["(nessuna)"] + cols_int, index=(cols_int.index(sugg_int["ean"]) + 1) if "ean" in sugg_int else 0)
        c5, c6 = st.columns(2)
        mi_qty = c5.selectbox("Colonna **QTY** (opz.)", ["(nessuna)"] + cols_int, index=(cols_int.index(sugg_int["qty"]) + 1) if "qty" in sugg_int else 0)
        mi_vat = c6.selectbox("Colonna **IVA** (opz.)", ["(nessuna)"] + cols_int, index=(cols_int.index(sugg_int["vat"]) + 1) if "vat" in sugg_int else 0)

        st.subheader("Listino **fornitore**")
        s1, s2, s3, s4 = st.columns(4)
        ms_code = s1.selectbox("Colonna **CODICE**", cols_sup, index=cols_sup.index(sugg_sup.get("code", cols_sup[0])) if cols_sup else 0)
        ms_desc = s2.selectbox("Colonna **DESCRIZIONE**", cols_sup, index=cols_sup.index(sugg_sup.get("desc", cols_sup[0])) if cols_sup else 0)
        ms_cost = s3.selectbox("Colonna **COSTO (es. € Cf)**", cols_sup, index=cols_sup.index(sugg_sup.get("price_cost", cols_sup[0])) if cols_sup else 0)
        ms_list = s4.selectbox("Colonna **LISTINO (es. € Cl)**", cols_sup, index=cols_sup.index(sugg_sup.get("price_list", cols_sup[0])) if cols_sup else 0)
        s5, s6, s7 = st.columns(3)
        ms_ean = s5.selectbox("Colonna **EAN** (opz.)", ["(nessuna)"] + cols_sup, index=(cols_sup.index(sugg_sup["ean"]) + 1) if "ean" in sugg_sup else 0)
        ms_brand = s6.selectbox("Colonna **BRAND** (opz.)", ["(nessuna)"] + cols_sup, index=(cols_sup.index(sugg_sup["brand"]) + 1) if "brand" in sugg_sup else 0)
        ms_vat = s7.selectbox("Colonna **IVA** (opz.)", ["(nessuna)"] + cols_sup, index=(cols_sup.index(sugg_sup["vat"]) + 1) if "vat" in sugg_sup else 0)

        how_match = st.radio("Chiave di matching primaria", options=["CODICE", "EAN"], horizontal=True)
        submit = st.form_submit_button("✅ Esegui matching e genera output")

    if submit:
        # normalizza e rinomina
        std_int = pd.DataFrame({
            "code": df_int[mi_code].astype(str).str.strip(),
            "desc": df_int[mi_desc].astype(str).str.strip(),
            "price_sell": _cast_numeric(df_int[[mi_price]].copy(), [mi_price])[mi_price],
        })
        if mi_ean != "(nessuna)":
            std_int["ean"] = df_int[mi_ean].astype(str).str.strip()
        if mi_qty != "(nessuna)":
            std_int["qty"] = _cast_numeric(df_int[[mi_qty]].copy(), [mi_qty])[mi_qty]
        if mi_vat != "(nessuna)":
            std_int["vat"] = _cast_numeric(df_int[[mi_vat]].copy(), [mi_vat])[mi_vat]

        std_sup = pd.DataFrame({
            "code": df_sup[ms_code].astype(str).str.strip(),
            "desc_sup": df_sup[ms_desc].astype(str).str.strip(),
            "cost_cf": _cast_numeric(df_sup[[ms_cost]].copy(), [ms_cost])[ms_cost],
            "price_cl": _cast_numeric(df_sup[[ms_list]].copy(), [ms_list])[ms_list],
        })
        if ms_ean != "(nessuna)":
            std_sup["ean"] = df_sup[ms_ean].astype(str).str.strip()
        if ms_brand != "(nessuna)":
            std_sup["brand"] = df_sup[ms_brand].astype(str).str.strip()
        if ms_vat != "(nessuna)":
            std_sup["vat"] = _cast_numeric(df_sup[[ms_vat]].copy(), [ms_vat])[ms_vat]

        # chiave di join
        key = "code" if how_match == "CODICE" else "ean"
        if key not in std_int.columns or key not in std_sup.columns:
            st.error(f"La chiave '{key}' non è presente in entrambi i dataset. Controlla la mappatura.")
            st.stop()

        # merge
        merged = pd.merge(std_int, std_sup, on=key, how="left", suffixes=("", "_sup"))

        # indicatori e output
        found = merged["cost_cf"].notna().sum()
        total = len(merged)
        st.success(f"Match su **{key}**: trovati {found} su {total} righe ({found/total:.0%}).")

        # suggerimento aggiornamento prezzo: mantengo price_sell, aggiungo nuove colonne di confronto
        merged["delta_vs_cf"] = merged["price_sell"] - merged["cost_cf"]
        merged["delta_vs_cl"] = merged["price_sell"] - merged["price_cl"]

        st.subheader("Anteprima output")
        st.dataframe(merged.head(30), use_container_width=True)

        st.subheader("Download")
        _download_excel(merged, filename="listino_aggiornato.xlsx")

else:
    st.info("Carica **entrambi** i file e definisci **foglio+intestazione** per attivare la mappatura.")