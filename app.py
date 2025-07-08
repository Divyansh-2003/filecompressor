# Streamlit PDF Compressor App with Smart Sampling
import streamlit as st
import os, shutil, subprocess
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

# --- Compression Settings ---
COMPRESSION_LEVELS = {
    "95": ("/screen", 0.30),
    "90": ("/screen", 0.35),
    "85": ("/ebook", 0.45),
    "80": ("/ebook", 0.55),
    "75": ("/printer", 0.65),
    "70": ("/printer", 0.70),
    "65": ("/prepress", 0.75),
    "60": ("/prepress", 0.80)
}

# --- Utility Functions ---
def compress_pdf(input_path, output_path, quality_flag, ocr=False):
    temp_input = input_path
    if ocr:
        temp_path = str(output_path).replace(".pdf", "_ocr.pdf")
        try:
            subprocess.run(["ocrmypdf", str(input_path), temp_path], check=True)
            temp_input = temp_path
        except:
            temp_input = input_path
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
            str(temp_input)
        ], check=True)
    except subprocess.CalledProcessError:
        shutil.copy(input_path, output_path)

def extract_zip(file, destination):
    with zipfile.ZipFile(file, 'r') as zip_ref:
        zip_ref.extractall(destination)

def gather_all_files(directory):
    return [Path(root) / f for root, _, files in os.walk(directory) for f in files]

def process_files_to_target_size(files, target_size, ocr_enabled=False):
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
    pdf_files = [f for f in all_files if f.suffix.lower() == ".pdf"]
    non_pdf_files = [f for f in all_files if f.suffix.lower() != ".pdf"]
    non_pdf_total_size = sum(f.stat().st_size for f in non_pdf_files)

    available_for_pdfs = target_size - non_pdf_total_size
    if available_for_pdfs <= 0:
        return None, None, "📂 Non-PDF files exceed target size."

    pdf_info = [(f, f.stat().st_size) for f in pdf_files]
    pdf_info.sort(key=lambda x: x[1], reverse=True)

    for level, (gs_flag, factor) in COMPRESSION_LEVELS.items():
        total_estimated = non_pdf_total_size
        temp_level_dir = temp_dir / f"_try_{level}"
        if temp_level_dir.exists():
            shutil.rmtree(temp_level_dir)
        shutil.copytree(temp_dir, temp_level_dir, dirs_exist_ok=True)

        compressed_files = []
        progress = st.progress(0.0)

        for idx, (pdf_path, _) in enumerate(pdf_info):
            out_path = temp_level_dir / f"compressed_{pdf_path.name}"
            compress_pdf(pdf_path, out_path, gs_flag, ocr=ocr_enabled)
            actual_size = out_path.stat().st_size
            total_estimated += actual_size
            compressed_files.append(out_path)
            progress.progress((idx + 1) / len(pdf_info))

        if total_estimated <= target_size:
            for original in pdf_files:
                original.unlink()
            for compressed in compressed_files:
                compressed.rename(temp_dir / compressed.name)
            progress.empty()
            return gather_all_files(temp_dir), [], None

        progress.empty()

    return None, None, "❌ Even max compression couldn't meet target size."

def zip_files(file_paths, zip_name="Optimized_Files.zip"):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_paths:
            file_path = Path(file_path)
            if file_path.exists():
                zf.write(file_path, arcname=file_path.name)
    zip_buffer.seek(0)
    return zip_buffer

# --- Streamlit UI ---
st.set_page_config(page_title="PDF Compression Optimizer", layout="wide")
st.title("📧 Smart File Size Optimizer")

st.markdown("""
Upload your PDFs or folders (ZIP), choose a target file size like **7MB** or **10MB**, and we will:
- Try compressing PDFs just enough to meet your size limit
- Use OCR for scanned PDFs if needed
- Return a ZIP with all optimized files
""")

max_size_input = st.text_input("🎯 Target Size for ZIP Output (e.g., 7MB, 10MB):", "7MB")
ocr_toggle = st.checkbox("🔍 Enable OCR for scanned PDFs (slower, better for Aadhaar etc.)", value=False)

try:
    target_bytes = humanfriendly.parse_size(max_size_input)
except:
    st.error("❌ Invalid size format. Use 5MB, 7MB, etc.")
    st.stop()

uploaded_files = st.file_uploader("📁 Upload your files or ZIPs", accept_multiple_files=True)

if uploaded_files and st.button("🚀 Optimize and Download"):
    if os.path.exists(BASE_TEMP_DIR):
        shutil.rmtree(BASE_TEMP_DIR)
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    selected_files, _, error_msg = process_files_to_target_size(uploaded_files, target_bytes, ocr_enabled=ocr_toggle)

    if selected_files is None:
        st.error(error_msg)
    else:
        zip_data = zip_files(selected_files)
        st.success("✅ Optimization complete!")
        st.download_button("📦 Download Optimized ZIP", zip_data, file_name="Optimized_Files.zip", mime="application/zip")
