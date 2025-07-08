import streamlit as st
import os
import shutil
import subprocess
from pathlib import Path
import humanfriendly
import uuid
from io import BytesIO
import zipfile

# --- Setup session directories ---
SESSION_ID = st.session_state.get("session_id", str(uuid.uuid4()))
st.session_state["session_id"] = SESSION_ID
BASE_TEMP_DIR = f"temp_storage_{SESSION_ID}"
INPUT_DIR = os.path.join(BASE_TEMP_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_TEMP_DIR, "output")
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Compression Estimation Table ---
COMPRESSION_FACTORS = {
    "95": 0.95,
    "90": 0.90,
    "85": 0.85,
    "80": 0.80,
    "75": 0.75,
    "70": 0.70,
    "65": 0.65,
    "60": 0.60,
    "55": 0.55,
    "50": 0.50,
    "45": 0.45,
    "40": 0.40,
    "35": 0.35,
    "30": 0.30
}
COMPRESSION_ORDER = list(COMPRESSION_FACTORS.items())

# --- Ghostscript PDF compression ---
def compress_pdf_ghostscript(input_path, output_path, level):
    quality_map = {
        "95": "/prepress",  # least compression
        "90": "/printer",
        "85": "/printer",
        "80": "/ebook",
        "75": "/ebook",
        "70": "/screen",
        "65": "/screen",
        "60": "/screen",
        "55": "/screen",
        "50": "/screen",
        "45": "/screen",
        "40": "/screen",
        "35": "/screen",
        "30": "/screen"
    }
    quality_flag = quality_map.get(level, "/screen")
    try:
        subprocess.run([
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS={quality_flag}",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={output_path}",
            str(input_path)
        ], check=True)
    except:
        shutil.copy(input_path, output_path)

# --- Extract ZIP ---
def extract_zip(file, destination):
    with zipfile.ZipFile(file, 'r') as zip_ref:
        zip_ref.extractall(destination)

# --- Collect files ---
def gather_all_files(directory):
    return [Path(root) / f for root, _, files in os.walk(directory) for f in files]

# --- Simulate compression to pick right level ---
def estimate_and_compress(files, target_size):
    temp_dir = Path(OUTPUT_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)

    for uploaded in files:
        ext = uploaded.name.lower().split(".")[-1]
        path = temp_dir / uploaded.name
        with open(path, "wb") as f:
            f.write(uploaded.getbuffer())
        if ext == "zip":
            extract_zip(path, temp_dir)
            path.unlink()

    all_files = gather_all_files(temp_dir)
    pdf_files = [f for f in all_files if f.suffix.lower() == ".pdf"]
    other_files = [f for f in all_files if f.suffix.lower() != ".pdf"]
    other_size = sum(f.stat().st_size for f in other_files)
    pdf_sizes = [f.stat().st_size for f in pdf_files]

    for level, factor in COMPRESSION_ORDER:
        total_estimated = other_size + sum([s * factor for s in pdf_sizes])
        if total_estimated <= target_size:
            return level, pdf_files, other_files

    return None, pdf_files, other_files

# --- Compress selected PDFs ---
def apply_selected_compression(pdf_files, compression_level):
    compressed_files = []
    for f in pdf_files:
        output = f.parent / f"compressed_{f.name}"
        compress_pdf_ghostscript(f, output, compression_level)
        compressed_files.append(output)
    return compressed_files

# --- Zip utility ---
def zip_files(file_paths):
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
Upload multiple files (PDFs, DOCX, ZIPs, etc). The app will:
- Compress PDFs just enough to fit your target size.
- Return all files (compressed + untouched) in a ZIP.
""")

max_size_input = st.text_input("🎯 Target Total Size (e.g., 7MB or 10MB):", "7MB")
try:
    target_bytes = humanfriendly.parse_size(max_size_input)
except:
    st.error("Invalid size format. Try '5MB', '10MB' etc.")
    st.stop()

uploaded_files = st.file_uploader("📁 Upload Files (multiple allowed):", accept_multiple_files=True)

if uploaded_files and st.button("🚀 Optimize and Download"):
    shutil.rmtree(BASE_TEMP_DIR, ignore_errors=True)
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    level, pdfs, others = estimate_and_compress(uploaded_files, target_bytes)

    if not level:
        st.error("❌ Cannot compress enough to meet size target. Try removing some files.")
    else:
        st.info(f"Selected Compression Level: {level}%")
        with st.spinner("Compressing PDFs..."):
            compressed = apply_selected_compression(pdfs, level)
            final_files = compressed + others
            zip_data = zip_files(final_files)

        st.success(f"✅ Done! Total files: {len(final_files)}")
        st.download_button("📦 Download Optimized ZIP", zip_data, file_name="Optimized_Files.zip", mime="application/zip")
