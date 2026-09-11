import streamlit as st
import pandas as pd

st.set_page_config(page_title="Append Additional Suppliers", layout="wide")

st.title("Append Additional Suppliers")
st.markdown(
    "Upload the latest D&B Full Output and an Additional Supplier list to generate a single "
    "D&B Connect upload CSV."
)

# Exact D&B Connect CSV Template columns (trailing spaces preserved)
TEMPLATE_COLS = [
    "Unique ID ",
    "D-U-N-S Number",
    "Registration Number",
    "Company Name ",
    "Street Address Line 1",
    "Street Address Line 2",
    "City / Town",
    "State / Province",
    "County ",
    "Postal Code",
    "Country ",
    "Telephone Number",
    "URL ",
    "Email",
    " D&B Contact ID",
    " First Name",
    " Family Name",
    " Custom Field 1",
    "Custom Field 2",
    "Custom Field 3 ",
    "Custom Field 4 ",
    "Custom Field 5 ",
]

DUNS_COL = "D-U-N-S Number"
MATCHED_DUNS_COL = "Matched D-U-N-S Number"


def read_uploaded_file(file):
    """Read an uploaded CSV or Excel file into a DataFrame."""
    file_name = file.name.lower()
    if file_name.endswith(".csv"):
        return pd.read_csv(file, dtype=str)
    elif file_name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file, dtype=str)
    else:
        raise ValueError("Unsupported file type. Please upload a CSV or Excel file.")


def normalize_col_name(col):
    """Strip whitespace for matching purposes while preserving the original."""
    return col.strip() if isinstance(col, str) else col


def find_column(df, target):
    """Return the actual column name in df whose stripped name matches target."""
    target_clean = normalize_col_name(target)
    for col in df.columns:
        if normalize_col_name(col) == target_clean:
            return col
    return None


def convert_full_output_to_template(df_full, template_cols):
    """Map Full Output columns to the exact D&B Connect template format.

    Uses Matched D-U-N-S Number (Column W) as the D-U-N-S Number in the template.
    Returns the converted DataFrame and a boolean indicating whether the matched
    D-U-N-S Number was found and used.
    """
    df_out = pd.DataFrame(columns=template_cols)

    full_cols_normalized = {normalize_col_name(c): c for c in df_full.columns}

    for template_col in template_cols:
        key = normalize_col_name(template_col)
        if key in full_cols_normalized:
            source_col = full_cols_normalized[key]
            df_out[template_col] = df_full[source_col]

    # Override D-U-N-S Number with Matched D-U-N-S Number (Column W)
    matched_duns_col = find_column(df_full, MATCHED_DUNS_COL)
    used_matched_duns = matched_duns_col is not None

    if used_matched_duns:
        df_out[DUNS_COL] = df_full[matched_duns_col]

    return df_out, used_matched_duns


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


# Use the embedded D&B Connect template columns
template_cols = TEMPLATE_COLS

st.subheader("Step 1: Upload D&B Full Output")
full_output_file = st.file_uploader(
    "Upload the D&B Full Output file (CSV or Excel)",
    type=["csv", "xlsx", "xls"],
    key="full_output_uploader",
)

st.subheader("Step 2: Upload Additional Suppliers")
additional_file = st.file_uploader(
    "Upload the Additional Supplier file (CSV or Excel)",
    type=["csv", "xlsx", "xls"],
    key="additional_supplier_uploader",
)

if full_output_file is not None and additional_file is not None:
    # Read Full Output
    try:
        df_full_output = read_uploaded_file(full_output_file)
    except Exception as e:
        st.error(f"Error reading Full Output file: {e}")
        st.stop()

    st.write(f"Full Output loaded: **{len(df_full_output)}** rows")

    # Convert Full Output to template format
    df_existing, used_matched_duns = convert_full_output_to_template(df_full_output, template_cols)

    if not used_matched_duns:
        st.warning(
            f"Column '{MATCHED_DUNS_COL}' (Column W) was not found in the Full Output. "
            f"The '{DUNS_COL}' field may not be populated correctly."
        )
    else:
        st.success(f"Used '{MATCHED_DUNS_COL}' (Column W) as the D-U-N-S Number.")

    st.write(f"Existing suppliers converted: **{len(df_existing)}** rows")

    existing_duns = set(
        df_existing[DUNS_COL].apply(clean_duns).replace("", pd.NA).dropna()
    )

    # Read Additional Suppliers
    try:
        df_additional_raw = read_uploaded_file(additional_file)
    except Exception as e:
        st.error(f"Error reading Additional Supplier file: {e}")
        st.stop()

    st.write(f"Additional suppliers uploaded: **{len(df_additional_raw)}** rows")

    # Align to template format
    df_additional = align_to_template(df_additional_raw, template_cols)

    # Validate that we have the key DUNS column
    if DUNS_COL not in df_additional.columns:
        st.error(f"Uploaded Additional Supplier file is missing the required '{DUNS_COL}' column.")
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
elif full_output_file is None and additional_file is None:
    st.info("Upload both the D&B Full Output and the Additional Supplier file to get started.")
elif full_output_file is None:
    st.info("Please upload the D&B Full Output file.")
else:
    st.info("Please upload the Additional Supplier file.")
