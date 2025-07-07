# Final Streamlit app with email-size optimization functionality
# - Accepts multiple files
# - Users define max total output size
# - Compresses PDFs selectively using Ghostscript for stronger compression
# - Accepts ZIPs and extracts their contents (including nested folders)

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
        "low": "/printer",
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

def process_files_to_target_size(files, target_size):
    temp_dir = Path(OUTPUT_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)

    for uploaded_file in files:
        extension = uploaded_file.name.lower().split(".")[-1]
        file_path = temp_dir / uploaded_file.name

        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        if extension == "zip":
            extract_zip(file_path, temp_dir)
            file_path.unlink()

    compression_levels = ["ultra", "high", "recommended", "low"]

    for level in compression_levels:
        working_dir = temp_dir / f"_tmp_{level}"
        if working_dir.exists():
            shutil.rmtree(working_dir)
        shutil.copytree(temp_dir, working_dir)

        selected_files, total_size = [], 0

        for root, _, files_in_dir in os.walk(working_dir):
            for fname in files_in_dir:
                file_path = Path(root) / fname
                extension = file_path.suffix.lower()
                file_size = file_path.stat().st_size

                if extension == ".pdf":
                    compressed_path = file_path.parent / f"compressed_{file_path.name}"
                    compress_pdf_ghostscript(file_path, compressed_path, level)
                    if compressed_path.exists():
                        compressed_size = compressed_path.stat().st_size
                        if total_size + compressed_size <= target_size:
                            selected_files.append(compressed_path)
                            total_size += compressed_size
                        compressed_path.rename(file_path)
                elif total_size + file_size <= target_size:
                    selected_files.append(file_path)
                    total_size += file_size

        if total_size <= target_size:
            return selected_files

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
st.set_page_config(page_title="Email File Set Optimizer", layout="wide")
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

    selected_files = process_files_to_target_size(uploaded_files, target_bytes)
    if selected_files is None:
        st.error("❌ Unable to fit all files within the selected size. Please remove some files and try again.")
    else:
        final_zip = zip_files(selected_files)
        st.success(f"✅ Done! {len(selected_files)} files included in the final zip.")
        st.download_button("📦 Download ZIP", final_zip, file_name="Final_Share.zip", mime="application/zip")
