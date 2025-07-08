# Final Streamlit app with dual download buttons
# - Compresses PDFs only when needed
# - Preserves other file types
# - Supports ZIP uploads
# - Returns optimized + full zip files

import streamlit as st
import os
import shutil
import subprocess
from pathlib import Path
import humanfriendly
import uuid
from io import BytesIO
import zipfile

# --- Setup persistent session directory ---
SESSION_ID = st.session_state.get("session_id", str(uuid.uuid4()))
st.session_state["session_id"] = SESSION_ID
BASE_TEMP_DIR = f"temp_storage_{SESSION_ID}"
INPUT_DIR = os.path.join(BASE_TEMP_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_TEMP_DIR, "output")
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Compression Estimation Factors ---
COMPRESSION_ESTIMATES = {
    "recommended": 0.7,
    "high": 0.5,
    "ultra": 0.35
}

def compress_pdf_ghostscript(input_path, output_path, quality="recommended"):
    quality_map = {
        "recommended": "/ebook",
        "high": "/screen",
        "ultra": "/screen"
    }
    dpi_flags = {
        "ultra": ["-dDownsampleColorImages=true", "-dColorImageResolution=50"]
    }
    quality_flag = quality_map.get(quality.lower(), "/ebook")
    extra_flags = dpi_flags.get(quality.lower(), [])
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

def gather_all_files(directory):
    return [Path(root) / f for root, _, files in os.walk(directory) for f in files]

def estimate_total_size(files, pdfs_only, level):
    total = 0
    factor = COMPRESSION_ESTIMATES.get(level, 0.7)
    for f in files:
        if f in pdfs_only:
            total += f.stat().st_size * factor
        else:
            total += f.stat().st_size
    return total

def process_files_to_target_size(files, target_size):
    temp_dir = Path(OUTPUT_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)

    for uploaded_file in files:
        ext = uploaded_file.name.lower().split(".")[-1]
        file_path = temp_dir / uploaded_file.name
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        if ext == "zip":
            extract_zip(file_path, temp_dir)
            file_path.unlink()

    all_files = gather_all_files(temp_dir)
    pdfs_only = [f for f in all_files if f.suffix.lower() == ".pdf"]

    for level in ["recommended", "high", "ultra"]:
        est_size = estimate_total_size(all_files, pdfs_only, level)
        if est_size <= target_size:
            selected_files = []
            for file_path in all_files:
                if file_path.suffix.lower() == ".pdf":
                    compressed_path = file_path.parent / f"compressed_{file_path.name}"
                    compress_pdf_ghostscript(file_path, compressed_path, level)
                    selected_files.append(compressed_path)
                else:
                    selected_files.append(file_path)
            return selected_files, all_files
    return None, all_files

def zip_files(file_paths, zip_name="Final_Share.zip"):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_paths:
            if Path(file_path).exists():
                zf.write(file_path, arcname=Path(file_path).name)
    zip_buffer.seek(0)
    return zip_buffer

# --- Streamlit UI ---
st.set_page_config(page_title="Email File Size Optimizer", layout="wide")
st.title("📧 Email File Size Optimizer")

st.markdown("""
Upload multiple files (PDFs, DOCX, ZIPs, etc). The app compresses PDFs
only when needed to meet your target size. You’ll get:
- ✅ Optimized zip (compressed PDFs if needed + all other files)
- 📁 Full zip with all files (no size check)
""")

max_size_input = st.text_input("🎯 Target Total Size (e.g., 7MB or 10MB):", "10MB")
try:
    target_bytes = humanfriendly.parse_size(max_size_input)
except:
    st.error("Invalid size format. Try 5MB, 10MB, etc.")
    st.stop()

uploaded_files = st.file_uploader("📁 Upload Files (multiple allowed):", accept_multiple_files=True)

if uploaded_files and st.button("🚀 Optimize and Download"):
    if os.path.exists(BASE_TEMP_DIR):
        shutil.rmtree(BASE_TEMP_DIR)
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with st.spinner("🔧 Optimizing files..."):
        selected_files, all_files = process_files_to_target_size(uploaded_files, target_bytes)

    if selected_files is None:
        st.error("❌ Cannot compress enough to meet size target. Try removing some files.")
    else:
        optimized_zip = zip_files(selected_files)
        full_zip = zip_files(all_files)

        st.success(f"✅ Optimization Complete! {len(selected_files)} files included.")
        st.download_button("📦 Download Optimized ZIP", optimized_zip, file_name="Optimized_Files.zip", mime="application/zip")
        st.download_button("📁 Download All Files ZIP", full_zip, file_name="All_Files.zip", mime="application/zip")
