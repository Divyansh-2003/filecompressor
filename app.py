import streamlit as st
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from io import BytesIO
import uuid

# Session-based temp directories
SESSION_ID = st.session_state.get("session_id", str(uuid.uuid4()))
st.session_state["session_id"] = SESSION_ID
BASE_TEMP_DIR = f"temp_storage_{SESSION_ID}"
INPUT_DIR = os.path.join(BASE_TEMP_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_TEMP_DIR, "output")
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Ghostscript compression
def compress_pdf_ghostscript(input_path, output_path, quality="recommended"):
    quality_map = {
        "recommended": "/ebook",
        "high": "/screen",
        "low": "/printer"
    }
    quality_flag = quality_map.get(quality.lower(), "/ebook")
    try:
        subprocess.run([
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS={quality_flag}",
            "-dNOPAUSE", "-dQUIET", "-dBATCH",
            f"-sOutputFile={output_path}",
            str(input_path)
        ], check=True)
    except subprocess.CalledProcessError:
        shutil.copy(input_path, output_path)

# Handle ZIP
def extract_zip(file_path, dest):
    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        zip_ref.extractall(dest)

# Save uploads
def save_uploaded_files(uploaded_files, save_dir):
    for uploaded_file in uploaded_files:
        save_path = Path(save_dir) / uploaded_file.name
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        if uploaded_file.name.endswith(".zip"):
            extract_zip(save_path, save_dir)
            os.remove(save_path)

# Walk all files
def get_all_files(folder_path):
    return [Path(root) / f for root, _, files in os.walk(folder_path) for f in files]

# Create ZIP preserving structure
def preserve_zip_structure(file_list, base_folder):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in file_list:
            rel_path = Path(file).relative_to(base_folder)
            zipf.write(file, arcname=str(rel_path))
    zip_buffer.seek(0)
    return zip_buffer

# UI
st.set_page_config(page_title="📄 PDF Compressor", layout="wide")
st.title("📄 Ghostscript PDF Compressor (Folder-preserving)")

st.sidebar.header("Compression Settings")
quality = st.sidebar.selectbox("Choose compression quality:", ["recommended", "high", "low"])

uploaded_files = st.file_uploader("📁 Upload files or ZIPs", accept_multiple_files=True)

if uploaded_files and st.button("🚀 Compress and Download"):
    shutil.rmtree(BASE_TEMP_DIR, ignore_errors=True)
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    save_uploaded_files(uploaded_files, INPUT_DIR)
    all_files = get_all_files(INPUT_DIR)

    processed_files = []
    progress = st.progress(0)

    for idx, file_path in enumerate(all_files):
        rel_path = file_path.relative_to(INPUT_DIR)
        out_path = Path(OUTPUT_DIR) / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if file_path.suffix.lower() == ".pdf":
            compress_pdf_ghostscript(file_path, out_path, quality)
        else:
            shutil.copy(file_path, out_path)

        processed_files.append(out_path)
        progress.progress((idx + 1) / len(all_files))

    st.success(f"✅ Done! {len(processed_files)} files processed.")
    zip_file = preserve_zip_structure(processed_files, OUTPUT_DIR)
    st.download_button("📦 Download Compressed ZIP", zip_file, file_name="compressed_output.zip", mime="application/zip")
