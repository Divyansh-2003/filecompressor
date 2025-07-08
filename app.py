import streamlit as st
import os
import shutil
import subprocess
from pathlib import Path
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

def zip_files_with_structure(base_folder):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(base_folder):
            for f in files:
                full_path = Path(root) / f
                relative_path = full_path.relative_to(base_folder)
                zf.write(full_path, arcname=str(relative_path))
    zip_buffer.seek(0)
    return zip_buffer

def process_files(files, level):
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

    for root, _, files_in_dir in os.walk(temp_dir):
        for name in files_in_dir:
            fpath = Path(root) / name
            if fpath.suffix.lower() == ".pdf":
                out_path = fpath.parent / f"compressed_{fpath.name}"
                compress_pdf(fpath, out_path, level)
                fpath.unlink()
                out_path.rename(fpath)

    return temp_dir

# Streamlit UI
st.set_page_config(page_title="Smart File Compressor", layout="wide")
st.title("📂 Compress Files (PDFs, ZIPs, etc.)")

st.sidebar.header("Compression Settings")
level = st.sidebar.selectbox("Choose PDF Compression Level", ["Recommended", "High", "Ultra"])

st.markdown("Upload files to compress all PDFs according to the selected level and retain folder structure.")

uploaded = st.file_uploader("📁 Upload files", accept_multiple_files=True)

if uploaded and st.button("🚀 Compress & Download"):
    with st.spinner("Processing..."):
        output_folder = process_files(uploaded, level)

    zip_buffer = zip_files_with_structure(output_folder)
    st.success("✅ Done! Your compressed files are ready.")
    st.download_button("📦 Download ZIP", zip_buffer, file_name="Compressed_Structured.zip", mime="application/zip")
