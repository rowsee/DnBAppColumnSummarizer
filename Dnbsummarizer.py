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


def to_excel_bytes(instructions_df, consolidated_df, full_df):
    """Create an Excel workbook with three sheets and return as bytes."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        instructions_df.to_excel(writer, sheet_name="Instructions", index=False)
        consolidated_df.to_excel(writer, sheet_name="Consolidated", index=False)
        full_df.to_excel(writer, sheet_name="Full Data", index=False)
    return output.getvalue()


def to_float(value):
    """Convert a value to float; return 0.0 for blanks/non-numeric."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def calculate_consolidated_score(row, ssi_col, ser_col, dnb_col):
    """Return weighted-average score using 40% SSI, 40% SER, 20% D&B Rating.

    The raw numeric values from each selected column are used directly.
    A selected column with 0, blank, or non-numeric data contributes 0 with its
    full weight. Only columns that are not selected at all are excluded, and their
    weights are re-normalized across the selected columns.
    """
    components = {
        "ssi": {
            "weight": 0.4,
            "selected": ssi_col is not None,
            "value": to_float(row.get(ssi_col)) if ssi_col else 0.0,
        },
        "ser": {
            "weight": 0.4,
            "selected": ser_col is not None,
            "value": to_float(row.get(ser_col)) if ser_col else 0.0,
        },
        "dnb": {
            "weight": 0.2,
            "selected": dnb_col is not None,
            "value": to_float(row.get(dnb_col)) if dnb_col else 0.0,
        },
    }
    selected = {k: v for k, v in components.items() if v["selected"]}
    if not selected:
        return 0
    weight_sum = sum(v["weight"] for v in selected.values())
    weighted = sum(v["value"] * v["weight"] for v in selected.values()) / weight_sum
    return round(weighted, 2)


def risk_level_from_weighted_score(score):
    """Map a weighted consolidated score to a Low/Medium/High/Critical label.

    Uses continuous SSI/SER-style bands on the consolidated raw-score scale:
    Low < 2.5, Medium 2.5-5.5, High 5.5-7.5, Critical > 7.5.
    """
    if score == 0:
        return "No Data"
    if score < 2.5:
        return "Low"
    if score < 5.5:
        return "Medium"
    if score < 7.5:
        return "High"
    return "Critical"


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

    # Remove suffix after "_" from Unique ID
    if unique_id_col in df.columns:
        st.subheader("Clean Unique ID")
        remove_suffix = st.checkbox(
            "Remove suffix from Unique ID (e.g., 0000399155_1 → 0000399155)",
            value=True,
            help="Strips everything from the last underscore onward.",
        )

        if remove_suffix:
            original_sample = df[unique_id_col].head(3).tolist()
            df[unique_id_col] = df[unique_id_col].astype(str).str.rsplit("_", n=1).str[0]
            cleaned_sample = df[unique_id_col].head(3).tolist()
            st.write("Example:")
            st.write(dict(zip(original_sample, cleaned_sample)))
    else:
        st.info(f"Column '{unique_id_col}' not found. Skipping Unique ID cleaning.")

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
        "The raw numeric values from each selected column are combined with weighted averaging: "
        "**40% SSI + 40% SER + 20% D&B Rating**. "
        "A selected column with 0, blank, or non-numeric data contributes 0 with its full weight. "
        "Only columns that are not selected at all are excluded, and their weights are re-normalized."
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

    # Prepare two output dataframes:
    # - df_filled: selected columns, blanks filled with 0, plus consolidated score
    # - df_full: all original columns, plus consolidated score
    df_full = df.copy()

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
                risk_level_from_weighted_score
            )

            df_full["Consolidated Financial Risk Score"] = df_full.apply(
                lambda row: calculate_consolidated_score(row, ssi_col, ser_col, dnb_col),
                axis=1,
            )
            df_full["Risk Level"] = df_full["Consolidated Financial Risk Score"].map(
                risk_level_from_weighted_score
            )
            # Keep both new columns at the end of each dataframe
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
        if unique_id_col in df_full.columns:
            df_full = df_full.drop_duplicates(subset=[unique_id_col], keep="first")
    else:
        st.info(f"Column '{unique_id_col}' not found in the uploaded file. Skipping duplicate check.")

    # Build the Instructions sheet
    instructions_data = {
        "Instructions": [
            "D&B Column Selector - Output Workbook",
            "",
            "This workbook contains three tabs:",
            "  1. Instructions - overview and methodology",
            "  2. Consolidated - selected columns with the consolidated financial risk score",
            "  3. Full Data - all input columns with the consolidated financial risk score",
            "",
            "Consolidated Financial Risk Score calculation:",
            "  - 40% Third Party Risk Supplier Stability Index Class Score",
            "  - 40% Third Party Risk Supplier Risk Score Raw Score",
            "  - 20% D&B Assessment Standard Rating Risk Segment",
            "",
            "Notes:",
            "  - A selected column with 0, blank, or non-numeric data contributes 0 with its full weight.",
            "  - Only columns that are not selected at all are excluded, and their weights are re-normalized.",
            "  - Duplicate Unique IDs are removed, keeping the first occurrence.",
            "",
            "Risk Level bands:",
            "  - Low: score < 2.5",
            "  - Medium: 2.5 <= score < 5.5",
            "  - High: 5.5 <= score < 7.5",
            "  - Critical: score >= 7.5",
            "  - No Data: score = 0",
        ]
    }
    instructions_df = pd.DataFrame(instructions_data)

    # Preview
    st.subheader("Preview")
    st.dataframe(filtered_df.head(50), use_container_width=True)

    st.write(f"**Output rows:** {len(filtered_df)} | **Output columns:** {len(filtered_df.columns)}")

    # Download as multi-sheet Excel
    output_excel = to_excel_bytes(instructions_df, filtered_df, df_full)
    output_file_name = uploaded_file.name.rsplit(".", 1)[0] + "_selected.xlsx"

    st.download_button(
        label="Download as Excel (3 tabs)",
        data=output_excel,
        file_name=output_file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Upload a file to get started.")
