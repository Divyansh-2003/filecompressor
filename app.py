import streamlit as st
import os
import shutil
import zipfile
import fitz  # PyMuPDF
from pathlib import Path
from io import BytesIO
import uuid

# Setup session-based folders
SESSION_ID = st.session_state.get("session_id", str(uuid.uuid4()))
st.session_state["session_id"] = SESSION_ID
BASE_TEMP_DIR = f"temp_storage_{SESSION_ID}"
INPUT_DIR = os.path.join(BASE_TEMP_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_TEMP_DIR, "output")
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Compress PDF using PyMuPDF (image-based)
def compress_pdf_pymupdf(input_path, output_path, dpi=100):
    doc = fitz.open(input_path)
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        images.append(img_bytes)
    doc.close()

    pdf_doc = fitz.open()
    for img_data in images:
        img_pdf = fitz.open("pdf", fitz.open("png", img_data).convert_to_pdf())
        pdf_doc.insert_pdf(img_pdf)
    pdf_doc.save(output_path)
    pdf_doc.close()

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

# UI
st.set_page_config(page_title="📄 PDF Compressor (Cloud)", layout="wide")
st.title("📄 PDF Compressor & Folder Zipper (Cloud-Ready)")

st.sidebar.header("🛠️ Compression Settings")
pymupdf_dpi = st.sidebar.slider("Image DPI (lower = smaller size)", 50, 150, 100)

uploaded_files = st.file_uploader("📁 Upload files or ZIPs", accept_multiple_files=True)

if uploaded_files and st.button("🚀 Compress & Download"):
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
            compress_pdf_pymupdf(file_path, out_path, dpi=pymupdf_dpi)
        else:
            shutil.copy(file_path, out_path)

        processed_files.append(out_path)
        progress.progress((idx + 1) / len(all_files))

    st.success(f"✅ Done! {len(processed_files)} files processed.")
    zip_file = preserve_zip_structure(processed_files, OUTPUT_DIR)
    st.download_button("📦 Download Compressed ZIP", zip_file, file_name="compressed_output.zip", mime="application/zip")
