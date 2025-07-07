# Final Streamlit app with full functionality
# - Intelligent chunking
# - Separate handling for large files
# - Rejoinable vs Independent zips
# - Flat structure in final ALL_CHUNKS.zip with README

# --- STREAMLIT APP START ---

import streamlit as st
import os
import zipfile
import shutil
from pathlib import Path
import humanfriendly
import uuid
from io import BytesIO
import PyPDF2

# --- Setup persistent session directory ---
SESSION_ID = st.session_state.get("session_id", str(uuid.uuid4()))
st.session_state["session_id"] = SESSION_ID
BASE_TEMP_DIR = f"temp_storage_{SESSION_ID}"
INPUT_DIR = os.path.join(BASE_TEMP_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_TEMP_DIR, "output")
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Utility Functions ---
def split_pdf_by_pages(file_path, max_size, output_dir):
    reader = PyPDF2.PdfReader(file_path)
    total_pages = len(reader.pages)
    filename = file_path.stem
    target_dir = Path(output_dir) / filename
    target_dir.mkdir(parents=True, exist_ok=True)

    writer = PyPDF2.PdfWriter()
    part_num = 1
    parts = []

    for i, page in enumerate(reader.pages):
        writer.add_page(page)
        temp_path = target_dir / f"{filename}_part{part_num}.pdf"
        with open(temp_path, "wb") as f:
            writer.write(f)

        size = temp_path.stat().st_size
        if size > max_size and len(writer.pages) > 1:
            writer.remove_page(-1)
            with open(temp_path, "wb") as f:
                writer.write(f)
            parts.append(temp_path)
            part_num += 1
            writer = PyPDF2.PdfWriter()
            writer.add_page(page)
        else:
            parts.append(temp_path)
            part_num += 1
            writer = PyPDF2.PdfWriter()

    return target_dir

def split_folder_intelligently(input_folder, max_chunk_size, output_dir, mode_pdf="compress", mode_office="none"):
    rejoinable_dirs, independent = [], []
    temp_independent = []

    for file_path in Path(input_folder).rglob("*"):
        if file_path.is_file():
            extension = file_path.suffix.lower()
            size = file_path.stat().st_size

            if extension in [".pptx", ".docx", ".xlsx", ".zip"]:
                continue

            if extension == ".pdf":
                if mode_pdf == "split" and size > max_chunk_size:
                    part_dir = split_pdf_by_pages(file_path, max_chunk_size, Path(output_dir))
                    rejoinable_dirs.append(part_dir)
                elif mode_pdf == "compress" and size > (3 * max_chunk_size):
                    part_dir = split_pdf_by_pages(file_path, max_chunk_size, Path(output_dir))
                    rejoinable_dirs.append(part_dir)
                else:
                    dest = Path(output_dir) / file_path.name
                    shutil.copy(file_path, dest)
                    temp_independent.append(dest)
            elif size > max_chunk_size:
                dest = Path(output_dir) / file_path.name
                shutil.copy(file_path, dest)
                temp_independent.append(dest)
            else:
                dest = Path(output_dir) / file_path.name
                shutil.copy(file_path, dest)
                temp_independent.append(dest)

    zip_parts = []
    current_chunk, current_size, part_num = [], 0, 1
    for file in temp_independent:
        f_size = file.stat().st_size
        if current_size + f_size > max_chunk_size and current_chunk:
            zip_name = f"independent_part{part_num}.zip"
            zip_path = Path(output_dir) / zip_name
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for f in current_chunk:
                    zipf.write(f, arcname=f.name)
            zip_parts.append(zip_path.name)
            for f in current_chunk:
                f.unlink()
            current_chunk, current_size, part_num = [], 0, part_num + 1

        current_chunk.append(file)
        current_size += f_size

    if current_chunk:
        zip_name = f"independent_part{part_num}.zip"
        zip_path = Path(output_dir) / zip_name
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for f in current_chunk:
                zipf.write(f, arcname=f.name)
        zip_parts.append(zip_path.name)
        for f in current_chunk:
            f.unlink()

    return rejoinable_dirs, zip_parts

# Keep rest of the code unchanged for Streamlit setup and UI
