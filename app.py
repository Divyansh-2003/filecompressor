# Smart File Compressor App
# Version 1.0 - Initial version with base UI and structure

import streamlit as st
import os
import zipfile
import shutil
from pathlib import Path
from io import BytesIO
import humanfriendly
import uuid
import tempfile

# --- Setup persistent session directory ---
SESSION_ID = st.session_state.get("session_id", str(uuid.uuid4()))
st.session_state["session_id"] = SESSION_ID
BASE_TEMP_DIR = Path(f"temp_compress_{SESSION_ID}")
INPUT_DIR = BASE_TEMP_DIR / "input"
OUTPUT_DIR = BASE_TEMP_DIR / "output"
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- File type categories ---
IMAGE_EXTS = [".jpg", ".jpeg", ".png"]
VIDEO_EXTS = [".mp4", ".mov", ".avi"]
PDF_EXTS = [".pdf"]

# --- Streamlit UI Setup ---
st.set_page_config(page_title="Smart File Compressor", layout="wide")
st.markdown("""
    <style>
    .stApp {
        background-color: #a2a1a2;
    }
    .css-1d391kg {
        border: 3px solid #000000;
        padding: 20px;
        border-radius: 6px;
    }
    .stButton > button {
        background-color: #1f1f23;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 8px 16px;
        font-size: 16px;
        font-weight: bold;
        cursor: pointer;
    }
    .stButton > button:hover {
        background-color: #5f5f5f;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📉 Smart File Compressor")

# Sidebar options
st.sidebar.header("Compression Settings")
if "max_size" not in st.session_state:
    st.session_state.max_size = "10MB"

def update_max_size(option):
    st.session_state.max_size = option

for size in ["7MB", "10MB"]:
    if st.sidebar.button(size):
        update_max_size(size)

size_input = st.sidebar.text_input("Max target size per file:", value=st.session_state.max_size)
try:
    target_size = humanfriendly.parse_size(size_input)
    st.sidebar.success(f"Target max: {humanfriendly.format_size(target_size)}")
except:
    st.sidebar.error("Invalid format, use e.g., 7MB or 10MB")
    target_size = 10 * 1024 * 1024

# Upload block
uploaded_files = st.file_uploader("Upload files (images/videos/PDFs or a ZIP folder)", accept_multiple_files=True)

# --- Placeholder compressor (real logic in next versions) ---
def dummy_compress(file_path: Path, output_path: Path, max_size_bytes: int):
    """Simulates compression by copying or truncating."""
    if file_path.stat().st_size > max_size_bytes:
        with open(file_path, 'rb') as f_in:
            data = f_in.read(max_size_bytes)
        with open(output_path, 'wb') as f_out:
            f_out.write(data)
    else:
        shutil.copy(file_path, output_path)

# Process button
if uploaded_files and st.button("🚀 Compress Files"):
    shutil.rmtree(BASE_TEMP_DIR, ignore_errors=True)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    st.info("Processing started...")
    progress = st.progress(0)
    log_area = st.empty()
    log = []

    all_uploaded_paths = []
    for file in uploaded_files:
        file_path = INPUT_DIR / file.name
        with open(file_path, "wb") as f:
            f.write(file.getbuffer())

        if file.name.endswith(".zip"):
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(INPUT_DIR)
            file_path.unlink()
        else:
            all_uploaded_paths.append(file_path)

    all_files = list(INPUT_DIR.rglob("*"))
    total = len(all_files)

    for idx, fpath in enumerate(all_files):
        if fpath.is_file():
            out_path = OUTPUT_DIR / fpath.name
            dummy_compress(fpath, out_path, target_size)
            orig_size = fpath.stat().st_size
            final_size = out_path.stat().st_size
            log.append(f"{fpath.name}: {humanfriendly.format_size(orig_size)} → {humanfriendly.format_size(final_size)}")
            progress.progress((idx + 1) / total)
            log_area.code("\n".join(log[-10:]))

    # Final ZIP
    final_zip_io = BytesIO()
    with zipfile.ZipFile(final_zip_io, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in OUTPUT_DIR.iterdir():
            z.write(f, arcname=f.name)
    final_zip_io.seek(0)

    st.success("✅ Compression complete!")
    st.download_button("📦 Download Compressed Files (ZIP)", data=final_zip_io, file_name="compressed_files.zip", mime="application/zip")
