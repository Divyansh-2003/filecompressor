import streamlit as st
import os
import shutil
import subprocess
import zipfile
import fitz  # PyMuPDF
from pathlib import Path
from io import BytesIO
import uuid

# --- Setup persistent session directory ---
SESSION_ID = st.session_state.get("session_id", str(uuid.uuid4()))
st.session_state["session_id"] = SESSION_ID
BASE_TEMP_DIR = f"temp_storage_{SESSION_ID}"
INPUT_DIR = os.path.join(BASE_TEMP_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_TEMP_DIR, "output")
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Utility Functions ---
def is_image_heavy_pdf(path, threshold=0.3):
    try:
        with fitz.open(path) as doc:
            image_pages = 0
            for page in doc:
                images = page.get_images()
                if images:
                    image_pages += 1
            return (image_pages / len(doc)) >= threshold
    except:
        return False

def compress_pdf_ghostscript(input_path, output_path, quality="recommended"):
    quality_map = {
        "recommended": "/ebook",
        "high": "/screen",
        "low": "/printer"
    }
    gs_quality = quality_map.get(quality, "/ebook")
    try:
        subprocess.run([
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS={gs_quality}",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={output_path}",
            str(input_path)
        ], check=True)
    except subprocess.CalledProcessError:
        shutil.copy(input_path, output_path)

def compress_pdf_pymupdf(input_path, output_path, dpi=100):
    doc = fitz.open(input_path)
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        images.append(img_bytes)
    doc.close()

    # Create new PDF with rasterized images
    pdf_doc = fitz.open()
    for img_data in images:
        img_pdf = fitz.open("pdf", fitz.open("png", img_data).convert_to_pdf())
        pdf_doc.insert_pdf(img_pdf)
    pdf_doc.save(output_path)
    pdf_doc.close()

def hybrid_compress_pdf(input_path, output_path, ghostscript_level="recommended", pymupdf_dpi=100):
    if is_image_heavy_pdf(input_path):
        compress_pdf_pymupdf(input_path, output_path, dpi=pymupdf_dpi)
    else:
        compress_pdf_ghostscript(input_path, output_path, quality=ghostscript_level)

def extract_zip(file_path, dest):
    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        zip_ref.extractall(dest)

def save_uploaded_files(uploaded_files, save_dir):
    for uploaded_file in uploaded_files:
        save_path = Path(save_dir) / uploaded_file.name
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        if uploaded_file.name.endswith(".zip"):
            extract_zip(save_path, save_dir)
            os.remove(save_path)

def get_all_files(folder_path):
    return [Path(root) / f for root, _, files in os.walk(folder_path) for f in files]

def preserve_zip_structure(file_list, base_folder):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in file_list:
            rel_path = Path(file).relative_to(base_folder)
            zipf.write(file, arcname=str(rel_path))
    zip_buffer.seek(0)
    return zip_buffer

# --- Streamlit UI ---
st.set_page_config(page_title="📄 Smart PDF Compressor", layout="wide")
st.title("📄 Smart PDF Compressor & Folder Zipper")

st.sidebar.header("🔧 Compression Settings")
compression_level = st.sidebar.selectbox("Compression Level", ["recommended", "high", "low"])
pymupdf_dpi = st.sidebar.slider("Image DPI (for image-heavy PDFs)", 50, 150, 100)

uploaded_files = st.file_uploader("📁 Upload your files/folders (ZIP, PDF, etc)", accept_multiple_files=True)

if uploaded_files and st.button("🚀 Compress & Download"):
    # Reset session directories
    shutil.rmtree(BASE_TEMP_DIR, ignore_errors=True)
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with st.spinner("Processing files..."):
        save_uploaded_files(uploaded_files, INPUT_DIR)
        all_files = get_all_files(INPUT_DIR)

        processed_files = []
        progress = st.progress(0)
        for idx, file_path in enumerate(all_files):
            out_path = Path(OUTPUT_DIR) / file_path.relative_to(INPUT_DIR)
            out_path.parent.mkdir(parents=True, exist_ok=True)

            if file_path.suffix.lower() == ".pdf":
                hybrid_compress_pdf(file_path, out_path, ghostscript_level=compression_level, pymupdf_dpi=pymupdf_dpi)
            else:
                shutil.copy(file_path, out_path)

            processed_files.append(out_path)
            progress.progress((idx + 1) / len(all_files))

    st.success(f"✅ Done! {len(processed_files)} files processed.")
    zip_data = preserve_zip_structure(processed_files, OUTPUT_DIR)
    st.download_button("📦 Download Compressed Folder as ZIP", zip_data, file_name="Compressed_Output.zip", mime="application/zip")
