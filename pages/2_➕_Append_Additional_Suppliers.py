import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Append Additional Suppliers", layout="wide")

st.title("Append Additional Suppliers")
st.markdown(
    "Combine existing D&B suppliers from the Full Output with new additional suppliers "
    "into a single D&B Connect upload CSV."
)

TEMPLATE_FILE = "DnB Connect Sample CSV Template.xlsx"
EXISTING_FILE = "DBTemplateSJ20260911_Full_Output.csv"

DUNS_COL = "D-U-N-S Number"


def read_uploaded_file(file):
    """Read an uploaded CSV or Excel file into a DataFrame."""
    file_name = file.name.lower()
    if file_name.endswith(".csv"):
        return pd.read_csv(file, dtype=str)
    elif file_name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file, dtype=str)
    else:
        raise ValueError("Unsupported file type. Please upload a CSV or Excel file.")


def load_template_columns():
    """Read the D&B Connect Sample CSV Template and return its exact column headers."""
    df = pd.read_excel(TEMPLATE_FILE, nrows=0)
    return df.columns.tolist()


def normalize_col_name(col):
    """Strip whitespace for matching purposes while preserving the original."""
    return col.strip() if isinstance(col, str) else col


def convert_full_output_to_template(df_full, template_cols):
    """Map Full Output columns to the exact D&B Connect template format."""
    df_out = pd.DataFrame(columns=template_cols)

    full_cols_normalized = {normalize_col_name(c): c for c in df_full.columns}

    for template_col in template_cols:
        key = normalize_col_name(template_col)
        if key in full_cols_normalized:
            source_col = full_cols_normalized[key]
            df_out[template_col] = df_full[source_col]

    return df_out


def align_to_template(df_in, template_cols):
    """Align an already-template-formatted file to the exact template column order/spelling."""
    df_out = pd.DataFrame(columns=template_cols)

    in_cols_normalized = {normalize_col_name(c): c for c in df_in.columns}

    for template_col in template_cols:
        key = normalize_col_name(template_col)
        if key in in_cols_normalized:
            source_col = in_cols_normalized[key]
            df_out[template_col] = df_in[source_col]

    return df_out


def clean_duns(value):
    """Return a stripped string for DUNS comparison; empty/NaN returns empty string."""
    if pd.isna(value):
        return ""
    return str(value).strip()


# Load template columns (exact spelling including trailing spaces)
try:
    template_cols = load_template_columns()
except Exception as e:
    st.error(f"Could not read D&B Connect template file '{TEMPLATE_FILE}': {e}")
    st.stop()

st.subheader("Step 1: Existing Suppliers")
st.markdown(
    f"Loading existing suppliers from **{EXISTING_FILE}** and converting them to the D&B Connect template format."
)

try:
    df_existing_full = pd.read_csv(EXISTING_FILE, dtype=str)
    df_existing = convert_full_output_to_template(df_existing_full, template_cols)
except Exception as e:
    st.error(f"Could not read existing Full Output file '{EXISTING_FILE}': {e}")
    st.stop()

st.write(f"Existing suppliers loaded: **{len(df_existing)}** rows")

existing_duns = set(
    df_existing[DUNS_COL].apply(clean_duns).replace("", pd.NA).dropna()
)

st.subheader("Step 2: Upload Additional Suppliers")
uploaded_file = st.file_uploader(
    "Upload the Additional Supplier file (CSV or Excel)",
    type=["csv", "xlsx", "xls"],
    key="additional_supplier_uploader",
)

if uploaded_file is not None:
    try:
        df_additional_raw = read_uploaded_file(uploaded_file)
    except Exception as e:
        st.error(f"Error reading uploaded file: {e}")
        st.stop()

    st.write(f"Additional suppliers uploaded: **{len(df_additional_raw)}** rows")

    # Align to template format
    df_additional = align_to_template(df_additional_raw, template_cols)

    # Validate that we have the key DUNS column
    if DUNS_COL not in df_additional.columns:
        st.error(f"Uploaded file is missing the required '{DUNS_COL}' column.")
        st.stop()

    # Show preview
    st.subheader("Preview of Additional Suppliers")
    st.dataframe(df_additional.head(50), use_container_width=True)

    # Deduplicate
    df_additional["_duns_clean"] = df_additional[DUNS_COL].apply(clean_duns)

    empty_duns_mask = df_additional["_duns_clean"] == ""
    empty_duns_count = empty_duns_mask.sum()

    duplicate_mask = df_additional["_duns_clean"].isin(existing_duns)
    duplicate_count = duplicate_mask.sum()

    df_new = df_additional[~(empty_duns_mask | duplicate_mask)].copy()
    df_skipped_empty = df_additional[empty_duns_mask].copy()
    df_skipped_dupes = df_additional[duplicate_mask].copy()

    # Remove helper column
    df_new = df_new.drop(columns=["_duns_clean"])
    if not df_skipped_empty.empty:
        df_skipped_empty = df_skipped_empty.drop(columns=["_duns_clean"])
    if not df_skipped_dupes.empty:
        df_skipped_dupes = df_skipped_dupes.drop(columns=["_duns_clean"])

    st.subheader("Step 3: Duplicate Check")

    if empty_duns_count > 0:
        st.warning(
            f"Found **{empty_duns_count}** additional supplier row(s) with an empty D-U-N-S Number. "
            "These will be kept in the output (D&B Connect will attempt to match them), "
            "but they cannot be checked for duplicates."
        )

    if duplicate_count > 0:
        st.warning(
            f"Found **{duplicate_count}** additional supplier row(s) whose D-U-N-S Number already exists in the existing dataset. "
            "These duplicates will be skipped."
        )
        with st.expander("Show skipped duplicate D-U-N-S Numbers"):
            st.dataframe(df_skipped_dupes[[DUNS_COL, "Company Name "]].reset_index(drop=True), use_container_width=True)
    else:
        st.success("No duplicate D-U-N-S Numbers found.")

    # Combine
    df_combined = pd.concat([df_existing, df_new], ignore_index=True)

    st.subheader("Step 4: Combined Output")
    st.write(
        f"**Existing suppliers:** {len(df_existing)} | "
        f"**New suppliers added:** {len(df_new)} | "
        f"**Total rows:** {len(df_combined)}"
    )

    st.dataframe(df_combined.head(50), use_container_width=True)

    # Download
    csv_bytes = df_combined.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download D&B Connect Upload CSV",
        data=csv_bytes,
        file_name="D&B_Connect_Upload.csv",
        mime="text/csv",
    )
else:
    st.info("Upload an Additional Supplier file to generate the combined D&B Connect CSV.")
