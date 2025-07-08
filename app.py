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
# Reordered to go from lowest compression (best quality) to highest
COMPRESSION_LEVELS = {
    "60": ("/prepress", 0.80), # Least compression, highest quality
    "65": ("/prepress", 0.75),
    "70": ("/printer", 0.70),
    "75": ("/printer", 0.65),
    "80": ("/ebook", 0.55),
    "85": ("/ebook", 0.45),
    "90": ("/screen", 0.35),
    "95": ("/screen", 0.30)  # Most compression, lowest quality
}

# --- Utility Functions ---
def compress_pdf(input_path, output_path, quality_flag, ocr=False):
    temp_input = input_path
    if ocr:
        temp_path = str(output_path).replace(".pdf", "_ocr.pdf")
        try:
            # ocrmypdf will put the OCR'd PDF at temp_path
            subprocess.run(["ocrmypdf", str(input_path), temp_path], check=True, capture_output=True, text=True)
            temp_input = temp_path
        except subprocess.CalledProcessError as e:
            st.warning(f"OCR failed for {input_path.name}: {e.stderr.strip()}. Proceeding without OCR.")
            temp_input = input_path
        except FileNotFoundError:
            st.error("OCRmyPDF not found. Please ensure it's installed and in your PATH if you enable OCR.")
            temp_input = input_path # Fallback if ocrmypdf isn't installed

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
        ], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        st.error(f"Ghostscript compression failed for {input_path.name} with flag {quality_flag}: {e.stderr.strip()}. Copying original.")
        shutil.copy(input_path, output_path)
    finally:
        if ocr and temp_input != input_path and Path(temp_input).exists():
            # Clean up the temporary OCR'd file
            Path(temp_input).unlink()


def extract_zip(file, destination):
    with zipfile.ZipFile(file, 'r') as zip_ref:
        zip_ref.extractall(destination)

def gather_all_files(directory):
    return [Path(root) / f for root, _, files in os.walk(directory) for f in files]

def process_files_to_target_size(uploaded_files, target_size, ocr_enabled=False):
    """
    Optimized function to process files to meet a target size.
    It iterates through compression levels from lowest to highest quality,
    stopping as soon as the target size is met.
    """
    processing_temp_dir = Path(BASE_TEMP_DIR) / "processing_temp"
    if processing_temp_dir.exists():
        shutil.rmtree(processing_temp_dir)
    processing_temp_dir.mkdir(parents=True, exist_ok=True)

    st.info("Unpacking uploaded files...")
    # Unpack all uploaded files into a temporary directory first
    for uploaded_file in uploaded_files:
        file_path = processing_temp_dir / uploaded_file.name
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        if file_path.suffix.lower() == ".zip":
            extract_zip(file_path, processing_temp_dir)
            file_path.unlink() # Delete the original zip file after extraction

    all_initial_files = gather_all_files(processing_temp_dir)
    pdf_files_initial = [f for f in all_initial_files if f.suffix.lower() == ".pdf"]
    non_pdf_files_initial = [f for f in all_initial_files if f.suffix.lower() != ".pdf"]
    
    non_pdf_total_size = sum(f.stat().st_size for f in non_pdf_files_initial)

    # If non-PDFs already exceed target, no need to proceed
    if non_pdf_total_size >= target_size:
        return None, None, f"📂 Non-PDF files alone ({humanfriendly.format_size(non_pdf_total_size)}) exceed the target size ({humanfriendly.format_size(target_size)})."

    # Estimate compression impact (optional but optimal)
    # This is a rough estimate; actual compression will vary.
    # The current COMPRESSION_LEVELS values already have an estimated factor.
    # We will use these factors for ordering the attempts.

    st.info("Starting compression attempts...")
    # Iterate through compression levels from lowest (best quality) to highest (worst quality)
    for level, (gs_flag, _) in COMPRESSION_LEVELS.items():
        st.write(f"Attempting compression level: **{level}%** (Quality setting: `{gs_flag}`)")
        current_attempt_dir = Path(BASE_TEMP_DIR) / f"attempt_{level}"
        
        # Copy initial non-PDF files to the current attempt directory
        if current_attempt_dir.exists():
            shutil.rmtree(current_attempt_dir)
        current_attempt_dir.mkdir(parents=True, exist_ok=True)
        
        for non_pdf_file in non_pdf_files_initial:
            shutil.copy(non_pdf_file, current_attempt_dir / non_pdf_file.name) # Copy to root of attempt dir

        compressed_pdf_paths = []
        total_current_size = non_pdf_total_size
        
        progress_bar = st.progress(0.0)
        
        for idx, pdf_path_initial in enumerate(pdf_files_initial):
            # Define output path for the compressed PDF within the current attempt's directory
            compressed_pdf_name = f"compressed_{pdf_path_initial.name}"
            output_path = current_attempt_dir / compressed_pdf_name
            
            # Use original file for compression
            compress_pdf(pdf_path_initial, output_path, gs_flag, ocr=ocr_enabled)
            
            # Check if the compressed file exists and add its size
            if output_path.exists():
                actual_size = output_path.stat().st_size
                total_current_size += actual_size
                compressed_pdf_paths.append(output_path)
            else:
                # If compression failed, add the original file's size and path to maintain content
                st.warning(f"Compression failed for {pdf_path_initial.name}. Adding original file to total size.")
                total_current_size += pdf_path_initial.stat().st_size
                compressed_pdf_paths.append(pdf_path_initial) # Keep original if compression fails
                
            progress_bar.progress((idx + 1) / len(pdf_files_initial))
        
        progress_bar.empty()
        
        st.info(f"Total size for level {level}: {humanfriendly.format_size(total_current_size)}")

        # Check if target size is met
        if total_current_size <= target_size:
            st.success(f"✅ Target size met with compression level {level}!")
            # Consolidate all files (compressed PDFs + non-PDFs) to the OUTPUT_DIR
            final_output_files = []
            if Path(OUTPUT_DIR).exists():
                shutil.rmtree(OUTPUT_DIR)
            Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

            for file_to_copy in non_pdf_files_initial + compressed_pdf_paths:
                # Ensure unique names if multiple files have the same name (e.g., from different subdirs in a zip)
                # For simplicity, we'll just copy the file name. If there are duplicates in the original set,
                # this will overwrite, which might be a desired behavior for the use case.
                # A more robust solution would involve preserving directory structure or renaming.
                destination_path = Path(OUTPUT_DIR) / file_to_copy.name
                shutil.copy(file_to_copy, destination_path)
                final_output_files.append(destination_path)
            
            # Clean up all temporary attempt directories
            shutil.rmtree(processing_temp_dir)
            for attempt_dir in Path(BASE_TEMP_DIR).glob("attempt_*"):
                shutil.rmtree(attempt_dir)

            return final_output_files, [], None

    # If no level met the target size
    shutil.rmtree(processing_temp_dir)
    for attempt_dir in Path(BASE_TEMP_DIR).glob("attempt_*"):
        shutil.rmtree(attempt_dir)
    return None, None, f"❌ Even with maximum compression, the total size could not be reduced to {humanfriendly.format_size(target_size)}. Smallest achieved was {humanfriendly.format_size(total_current_size)}."


def zip_files(file_paths, zip_name="Optimized_Files.zip"):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_paths:
            file_path = Path(file_path)
            if file_path.exists():
                # arcname makes sure the file inside the zip is just its name, not full path
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

target_bytes = 0
try:
    target_bytes = humanfriendly.parse_size(max_size_input)
except Exception:
    st.error("❌ Invalid size format. Use 5MB, 7MB, etc.")
    st.stop()

uploaded_files = st.file_uploader("📁 Upload your files or ZIPs", accept_multiple_files=True)

if uploaded_files and st.button("🚀 Optimize and Download"):
    # Clean up previous session's temp directory if it exists, and recreate
    if os.path.exists(BASE_TEMP_DIR):
        st.info("Cleaning up previous session data...")
        shutil.rmtree(BASE_TEMP_DIR)
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True) # Ensure OUTPUT_DIR exists for final files

    with st.spinner("Optimizing your files... This may take a while for large files or many files."):
        selected_files, _, error_msg = process_files_to_target_size(uploaded_files, target_bytes, ocr_enabled=ocr_toggle)

    if selected_files is None:
        st.error(error_msg)
    else:
        zip_data = zip_files(selected_files)
        st.success("✅ Optimization complete!")
        
        # Display final size
        final_zip_size = humanfriendly.format_size(len(zip_data.getvalue()))
        st.info(f"The final optimized ZIP file size is: **{final_zip_size}**")

        st.download_button(
            "📦 Download Optimized ZIP",
            zip_data,
            file_name="Optimized_Files.zip",
            mime="application/zip"
        )

# Clean up session directory when done or on rerun
def cleanup_session_dir():
    if os.path.exists(BASE_TEMP_DIR):
        shutil.rmtree(BASE_TEMP_DIR)

# This might be tricky in Streamlit's rerun model.
# For a more robust cleanup, consider using st.experimental_singleton for resources
# or a mechanism that triggers on app close/tab close, which Streamlit doesn't directly expose.
# For now, we clean at the start of processing and rely on OS to clean temp dirs on restart.
# Alternatively, a button for manual cleanup can be added.
# st.sidebar.button("Clean up temporary files", on_click=cleanup_session_dir) # Optional: Add a cleanup button
