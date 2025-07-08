# Final Streamlit app with email-size optimization functionality
# - Accepts multiple files including ZIPs
# - Users define max total output size
# - Compresses PDFs using Ghostscript
# - Returns both optimized and full output

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

def gather_all_files(directory):
    return [Path(root) / f for root, _, files in os.walk(directory) for f in files]

def process_files_to_target_size(files, target_size):
    temp_dir = Path(OUTPUT_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Save and extract uploads
    for uploaded_file in files:
        ext = uploaded_file.name.lower().split(".")[-1]
        file_path = temp_dir / uploaded_file.name
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        if ext == "zip":
            extract_zip(file_path, temp_dir)
            file_path.unlink()

    compression_levels = ["ultra", "high", "recommended", "low"]

    for level in compression_levels:
        working_dir = temp_dir / f"_tmp_{level}"
        if working_dir.exists():
            shutil.rmtree(working_dir)
        shutil.copytree(temp_dir, working_dir, dirs_exist_ok=True)

        selected_files, total_size, skipped = [], 0, []
        all_files = gather_all_files(working_dir)

        progress = st.progress(0)
        for i, file_path in enumerate(all_files):
            file_path = Path(file_path)
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
                    else:
                        skipped.append(file_path)
                    compressed_path.rename(file_path)
            elif total_size + file_size <= target_size:
                selected_files.append(file_path)
                total_size += file_size
            else:
                skipped.append(file_path)

            progress.progress((i + 1) / len(all_files))

        if total_size <= target_size:
            progress.empty()
            return selected_files, skipped, gather_all_files(working_dir)

    progress.empty()
    return None, None, None

def zip_files(file_paths, zip_name="Final_Share.zip"):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_paths:
            file_path = Path(file_path)
            if file_path.exists():
                zf.write(file_path, arcname=file_path.name)
    zip_buffer.seek(0)
    return zip_buffer

# --- Streamlit UI ---
st.set_page_config(page_title="Email File Set Optimizer", layout="wide")
st.title("📧 Email File Size Optimizer")

st.markdown("""
Upload multiple files (PDFs, DOCX, ZIPs, etc). The app will compress PDFs
only if needed to fit within your defined size limit. You will get:
- An optimized zip (compressed to fit size)
- A full zip (with all files)
- List of skipped files if any
""")

max_size_input = st.text_input("🎯 Target Total Size (e.g., 7MB or 10MB):", "7MB")
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

    selected_files, skipped_files, all_processed = process_files_to_target_size(uploaded_files, target_bytes)

    if selected_files is None:
        st.error("❌ Unable to meet the size requirement. Remove files and try again.")
    else:
        optimized_zip = zip_files(selected_files)
        full_zip = zip_files(all_processed)

        st.success(f"✅ Done! {len(selected_files)} files included in optimized zip.")

        st.download_button("📦 Download Optimized ZIP", optimized_zip, file_name="Optimized_Files.zip", mime="application/zip")
        st.download_button("📁 Download All Files ZIP", full_zip, file_name="All_Files.zip", mime="application/zip")

        if skipped_files:
            st.warning("Some files could not be included due to size constraints:")
            for file in skipped_files:
                st.text(f"❌ {file.name} ({humanfriendly.format_size(file.stat().st_size)})")
