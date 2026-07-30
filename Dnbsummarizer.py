import streamlit as st
import pandas as pd
import json
from io import BytesIO, StringIO

st.set_page_config(page_title="D&B Column Selector", layout="wide")

st.title("D&B Data Column Selector")
st.markdown(
    "Upload a file, choose the columns you want to keep, remove duplicate **Unique IDs**, "
    "and download the cleaned output. You can also save your column selection so you don't have to pick it every time."
)


def read_file(file):
    """Read an uploaded CSV or Excel file into a DataFrame."""
    file_name = file.name.lower()
    if file_name.endswith(".csv"):
        return pd.read_csv(file, dtype=str)
    elif file_name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file, dtype=str)
    else:
        raise ValueError("Unsupported file type. Please upload a CSV or Excel file.")


def to_csv_bytes(df):
    """Convert DataFrame to CSV bytes for download."""
    return df.to_csv(index=False).encode("utf-8")


def risk_level_from_ssi_ser(value):
    """Map SSI/SER numeric score (1-9) to risk level 1-4."""
    try:
        v = float(value)
    except (ValueError, TypeError):
        return 0
    if v == 0:
        return 0
    if 1 <= v <= 2:
        return 1  # Low
    if 3 <= v <= 5:
        return 2  # Medium
    if 6 <= v <= 7:
        return 3  # High
    if 8 <= v <= 9:
        return 4  # Critical
    return 0


def risk_level_from_dnb_rating(value):
    """Map D&B Rating numeric score (1-4) to risk level 1-4."""
    try:
        v = float(value)
    except (ValueError, TypeError):
        return 0
    if v == 0:
        return 0
    if 1 <= v <= 4:
        return int(v)
    return 0


def calculate_consolidated_score(row, ssi_col, ser_col, dnb_col):
    """Return the maximum risk level across SSI, SER, and D&B Rating."""
    levels = [
        risk_level_from_ssi_ser(row.get(ssi_col)),
        risk_level_from_ssi_ser(row.get(ser_col)),
        risk_level_from_dnb_rating(row.get(dnb_col)),
    ]
    non_zero = [lvl for lvl in levels if lvl != 0]
    return max(non_zero) if non_zero else 0


# Sidebar: saved config management
st.sidebar.header("Saved Configurations")

uploaded_config = st.sidebar.file_uploader(
    "Load a saved column config (JSON)", type=["json"], key="config_uploader"
)

saved_columns = []
if uploaded_config is not None:
    try:
        config = json.load(uploaded_config)
        saved_columns = config.get("columns", [])
        st.sidebar.success(f"Loaded {len(saved_columns)} columns from config.")
    except Exception as e:
        st.sidebar.error(f"Failed to load config: {e}")


# Main: file upload
uploaded_file = st.file_uploader(
    "Upload your data file", type=["csv", "xlsx", "xls"], key="data_uploader"
)

if uploaded_file is not None:
    try:
        df = read_file(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        st.stop()

    st.subheader("File Overview")
    st.write(f"**Rows:** {len(df)} | **Columns:** {len(df.columns)}")

    unique_id_col = "Unique ID"

    # Filter by suffix after "_" in Unique ID
    if unique_id_col in df.columns:
        st.subheader("Filter by Unique ID Suffix")
        st.markdown(
            "Select which suffix values (the part after the underscore in **Unique ID**) you want to keep."
        )

        def extract_suffix(uid):
            if pd.isna(uid):
                return "(blank)"
            uid = str(uid)
            if "_" in uid:
                return uid.rsplit("_", 1)[-1]
            return "(no suffix)"

        df["_tmp_unique_id_suffix"] = df[unique_id_col].apply(extract_suffix)
        suffix_counts = df["_tmp_unique_id_suffix"].value_counts().sort_index()
        suffix_options = suffix_counts.index.tolist()
        suffix_option_labels = [
            f"{suffix} ({suffix_counts[suffix]} rows)" for suffix in suffix_options
        ]

        selected_suffixes = st.multiselect(
            "Unique ID suffixes to include",
            options=suffix_options,
            default=suffix_options,
            format_func=lambda x: f"{x} ({suffix_counts[x]} rows)",
            help="e.g., '1' from IDs like '0000399155_1'. '(no suffix)' means no underscore in the ID.",
        )

        if not selected_suffixes:
            st.warning("Please select at least one suffix.")
            st.stop()

        df = df[df["_tmp_unique_id_suffix"].isin(selected_suffixes)].copy()
        df = df.drop(columns=["_tmp_unique_id_suffix"])
        st.write(f"**Filtered rows:** {len(df)}")
    else:
        st.info(f"Column '{unique_id_col}' not found. Skipping suffix filter.")

    all_columns = df.columns.tolist()

    # Determine default selected columns
    default_columns = saved_columns if saved_columns else all_columns
    # Only keep columns that actually exist in the current file
    default_columns = [c for c in default_columns if c in all_columns]
    if not default_columns:
        default_columns = all_columns

    # Column selection
    st.subheader("Select Columns to Include")
    selected_columns = st.multiselect(
        "Choose columns",
        options=all_columns,
        default=default_columns,
        help="Select the columns you want in the output file.",
    )

    if not selected_columns:
        st.warning("Please select at least one column.")
        st.stop()

    # Optional JSON config download (separate from CSV download)
    st.subheader("Save Column Selection (Optional)")
    save_config = st.checkbox(
        "I want to download my column selection as a JSON config file",
        value=False,
        help="Check this box if you want to save the selected columns and reuse them later.",
    )
    if save_config:
        config_json = json.dumps({"columns": selected_columns}, indent=2)
        st.download_button(
            label="Download column config (JSON)",
            data=config_json,
            file_name="column_config.json",
            mime="application/json",
            help="Save this selection so you can load it again next time.",
        )

    # Consolidated Financial Risk Score
    st.subheader("Consolidated Financial Risk Score")
    st.markdown(
        "Map SSI / SER / D&B Rating columns to a single risk score. "
        "Scores are calculated using the Low/Medium/High/Critical ranges from the table."
    )

    enable_consolidated_score = st.checkbox(
        "Add 'Consolidated Financial Risk Score' column",
        value=True,
        help="Uncheck if you do not want this extra column in the export.",
    )

    ssi_col = None
    ser_col = None
    dnb_col = None
    if enable_consolidated_score:
        default_ssi = "Third Party Risk Supplier Stability Index Class Score"
        default_ser = "Third Party Risk Supplier Risk Score Raw Score"
        default_dnb = "D&B Assessment Standard Rating Risk Segment"

        ssi_col = st.selectbox(
            "SSI column",
            options=["(none)"] + all_columns,
            index=(["(none)"] + all_columns).index(default_ssi)
            if default_ssi in all_columns
            else 0,
            help="Values 1-9: Low=1-2, Medium=3-5, High=6-7, Critical=8-9.",
        )
        ssi_col = None if ssi_col == "(none)" else ssi_col

        ser_col = st.selectbox(
            "SER column",
            options=["(none)"] + all_columns,
            index=(["(none)"] + all_columns).index(default_ser)
            if default_ser in all_columns
            else 0,
            help="Values 1-9: Low=1-2, Medium=3-5, High=6-7, Critical=8-9.",
        )
        ser_col = None if ser_col == "(none)" else ser_col

        dnb_col = st.selectbox(
            "D&B Rating column",
            options=["(none)"] + all_columns,
            index=(["(none)"] + all_columns).index(default_dnb)
            if default_dnb in all_columns
            else 0,
            help="Values 1-4: Low=1, Medium=2, High=3, Critical=4.",
        )
        dnb_col = None if dnb_col == "(none)" else dnb_col

    # Replace blank cells in selected columns with 0
    df_filled = df[selected_columns].copy()
    df_filled = df_filled.replace(r"^\s*$", "0", regex=True)
    df_filled = df_filled.fillna("0")

    if enable_consolidated_score:
        score_cols = [c for c in [ssi_col, ser_col, dnb_col] if c is not None]
        if score_cols:
            df_filled["Consolidated Financial Risk Score"] = df_filled.apply(
                lambda row: calculate_consolidated_score(row, ssi_col, ser_col, dnb_col),
                axis=1,
            )
            df_filled["Risk Level"] = df_filled["Consolidated Financial Risk Score"].map(
                {0: "No Data", 1: "Low", 2: "Medium", 3: "High", 4: "Critical"}
            )
            # Keep both new columns at the end of the dataframe
        else:
            st.warning("No SSI/SER/D&B Rating columns selected. Skipping consolidated score.")
            enable_consolidated_score = False

    # Duplicate Unique ID handling
    filtered_df = df_filled.copy()

    if unique_id_col in filtered_df.columns:
        st.subheader("Duplicate 'Unique ID' Check")
        duplicate_count = filtered_df[unique_id_col].duplicated().sum()

        if duplicate_count > 0:
            st.warning(
                f"Found **{duplicate_count}** duplicate row(s) based on '{unique_id_col}'. "
                "These will be removed from the output, keeping the first occurrence."
            )
            duplicate_ids = filtered_df[filtered_df[unique_id_col].duplicated(keep=False)][
                unique_id_col
            ].unique()
            with st.expander("Show duplicate Unique IDs"):
                st.write(duplicate_ids)
        else:
            st.success(f"No duplicate '{unique_id_col}' values found.")

        filtered_df = filtered_df.drop_duplicates(subset=[unique_id_col], keep="first")
    else:
        st.info(f"Column '{unique_id_col}' not found in the uploaded file. Skipping duplicate check.")

    # Preview
    st.subheader("Preview")
    st.dataframe(filtered_df.head(50), use_container_width=True)

    st.write(f"**Output rows:** {len(filtered_df)} | **Output columns:** {len(filtered_df.columns)}")

    # Download
    output_csv = to_csv_bytes(filtered_df)
    output_file_name = uploaded_file.name.rsplit(".", 1)[0] + "_selected.csv"

    st.download_button(
        label="Download selected columns as CSV",
        data=output_csv,
        file_name=output_file_name,
        mime="text/csv",
    )
else:
    st.info("Upload a file to get started.")
