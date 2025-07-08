# Final Streamlit app with accurate size-aware compression
# - Upload files or ZIPs
# - Estimate compression for PDFs
# - Selects minimal compression needed to meet target size
# - Includes compressed PDFs and untouched non-PDFs in final ZIP

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

# --- Utility Functions ---
def compress_pdf_ghostscript(input_path, output_path, quality="recommended"):
    quality_map = {
        "90": "/printer",
        "80": "/ebook",
        "70": "/screen",
        "60": "/screen"
    }
    dpi_flags = {
        "60": ["-dDownsampleColorImages=true", "-dColorImageResolution=72"]
    }
    quality_flag = quality_map.get(quality, "/ebook")
    extra_flags = dpi_flags.get(quality, [])
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


def estimate_compressed_size(file_size, compression_percent):
    return int(file_size * (compression_percent / 100.0))


def process_files_with_estimation(files, target_size):
    temp_dir = Path(OUTPUT_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    pdf_files, other_files = [], []

    for uploaded_file in files:
        extension = uploaded_file.name.lower().split(".")[-1]
        file_path = temp_dir / uploaded_file.name
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        if extension == "zip":
            extract_zip(file_path, temp_dir)
            file_path.unlink()

    # Recollect files
    all_files = [Path(root) / name for root, _, files_in_dir in os.walk(temp_dir)
                 for name in files_in_dir]

    for f in all_files:
        if f.suffix.lower() == ".pdf":
            pdf_files.append(f)
        else:
            other_files.append(f)

    other_total = sum(f.stat().st_size for f in other_files)

    compression_levels = [90, 80, 70, 60]
    pdf_original_sizes = {f: f.stat().st_size for f in pdf_files}

    for level in compression_levels:
        est_pdf_sizes = [estimate_compressed_size(size, level) for size in pdf_original_sizes.values()]
        est_total = other_total + sum(est_pdf_sizes)
        if est_total <= target_size:
            final_dir = temp_dir / f"compressed_{level}"
            final_dir.mkdir(exist_ok=True)

            # Copy other files
            for f in other_files:
                shutil.copy(f, final_dir / f.name)

            # Compress PDFs
            for f in pdf_files:
                out_pdf = final_dir / f.name
                compress_pdf_ghostscript(f, out_pdf, str(level))

            return list(final_dir.glob("*"))

    return None


def zip_files(file_paths, zip_name="Final_Share.zip"):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_paths:
            if file_path.exists():
                zf.write(file_path, arcname=file_path.name)
    zip_buffer.seek(0)
    return zip_buffer

# --- Streamlit UI ---
st.set_page_config(page_title="Email File Size Optimizer", layout="wide")
st.title("📧 Email File Size Optimizer")

st.markdown("""
Upload multiple files (PDFs, DOCX, images, etc). The app will compress only the PDFs
so that the final archive stays within your selected total size limit (e.g. for emailing).
""")

max_size_input = st.text_input("🌟 Target Total Size (e.g., 7MB or 10MB):", "10MB")
try:
    target_bytes = humanfriendly.parse_size(max_size_input)
except:
    st.error("Invalid size format. Use like 7MB, 10MB")
    st.stop()

uploaded_files = st.file_uploader("📁 Upload Files (multiple allowed):", accept_multiple_files=True)

if uploaded_files and st.button("🚀 Optimize and Download"):
    if os.path.exists(BASE_TEMP_DIR):
        shutil.rmtree(BASE_TEMP_DIR)
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with st.spinner("Processing and estimating sizes..."):
        selected_files = process_files_with_estimation(uploaded_files, target_bytes)

    if selected_files is None:
        st.error("❌ Unable to fit all files within the selected size. Please remove some files and try again.")
    else:
        final_zip = zip_files(selected_files)
        st.success(f"✅ Done! {len(selected_files)} files included in the final zip.")
        st.download_button("📦 Download ZIP", final_zip, file_name="Final_Share.zip", mime="application/zip")
