import streamlit as st

st.set_page_config(page_title="D&B Tools", layout="wide")

st.title("D&B Data Tools")
st.markdown("Select a module from the sidebar to get started.")

st.markdown(
    """
    ### Available Modules

    1. **📊 Column Selector**  
       Upload a D&B data file, select columns, calculate a consolidated financial risk score,  
       remove duplicate Unique IDs, and download a cleaned Excel workbook.

    2. **➕ Append Additional Suppliers**  
       Combine existing suppliers from the D&B Full Output with new additional suppliers  
       into a single D&B Connect upload CSV, with duplicate D-U-N-S Number detection.
    """
)

st.info("Use the navigation menu on the left to switch between modules.")
