# Final Streamlit app with user-selected compression level and size target
import streamlit as st
import os
import shutil
import subprocess
from pathlib import Path
import humanfriendly
import uuid
from io import BytesIO
import zipfile

# Setup persistent session directory
SESSION_ID = st.session_state.get("session_id", str(uuid.uuid4()))
st.session_state["session_id"] = SESSION_ID
BASE_TEMP_DIR = f"temp_storage_{SESSION_ID}"
INPUT_DIR = os.path.join(BASE_TEMP_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_TEMP_DIR, "output")
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

COMPRESSION_ESTIMATES = {
    "Recommended": 0.7,
    "High": 0.5,
    "Ultra": 0.35
}

QUALITY_MAP = {
    "Recommended": "/ebook",
    "High": "/screen",
    "Ultra": "/screen"
}

DPI_FLAGS = {
    "Ultra": ["-dDownsampleColorImages=true", "-dColorImageResolution=50"]
}

def compress_pdf(input_path, output_path, quality="Recommended"):
    quality_flag = QUALITY_MAP.get(quality, "/ebook")
    extra_flags = DPI_FLAGS.get(quality, [])
    try:
        subprocess.run([
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS={quality_flag}",
            *extra_flags,
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={output_path}",
            str(input_path)
        ], check=True)
    except subprocess.CalledProcessError:
        shutil.copy(input_path, output_path)

def extract_zip(file, destination):
    with zipfile.ZipFile(file, 'r') as zip_ref:
        zip_ref.extractall(destination)

def estimate_total_size(files, pdfs, level):
    factor = COMPRESSION_ESTIMATES.get(level, 0.7)
    return sum(f.stat().st_size * (factor if f in pdfs else 1) for f in files)

def zip_files(file_paths):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in file_paths:
            zf.write(f, arcname=f.name)
    zip_buffer.seek(0)
    return zip_buffer

def process_files(files, target_size, level):
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    temp_dir = Path(OUTPUT_DIR)

    for file in files:
        ext = file.name.split(".")[-1].lower()
        path = temp_dir / file.name
        with open(path, "wb") as f:
            f.write(file.getbuffer())
        if ext == "zip":
            extract_zip(path, temp_dir)
            path.unlink()

    all_files = [Path(root) / f for root, _, files in os.walk(temp_dir) for f in files]
    pdfs = [f for f in all_files if f.suffix.lower() == ".pdf"]

    if estimate_total_size(all_files, pdfs, level) > target_size:
        return None

    final_files = []
    for f in all_files:
        if f.suffix.lower() == ".pdf":
            out_path = f.parent / f"compressed_{f.name}"
            compress_pdf(f, out_path, level)
            final_files.append(out_path)
        else:
            final_files.append(f)

    return final_files

# Streamlit UI
st.set_page_config(page_title="Smart File Compression for Email", layout="wide")
st.title("📧 Smart Email File Compressor")

st.sidebar.header("Compression Settings")
level = st.sidebar.selectbox("Choose PDF Compression Level", ["Recommended", "High", "Ultra"])
size_input = st.sidebar.text_input("Target Total ZIP Size", "7MB")

st.markdown("Upload any combination of files. PDFs will be compressed based on your selected level.")
uploaded = st.file_uploader("📁 Upload files (PDF, ZIP, DOCX, etc.)", accept_multiple_files=True)

try:
    target_bytes = humanfriendly.parse_size(size_input)
except:
    st.error("Invalid size format (e.g. 7MB, 10MB)")
    st.stop()

if uploaded and st.button("🚀 Compress & Download"):
    with st.spinner("Processing..."):
        result = process_files(uploaded, target_bytes, level)
    if result is None:
        st.error("❌ Could not fit files within the specified size. Try higher compression or remove files.")
    else:
        zip_file = zip_files(result)
        st.success(f"✅ Files compressed and ready!")
        st.download_button("📦 Download ZIP", zip_file, file_name="Email_Ready.zip", mime="application/zip")
