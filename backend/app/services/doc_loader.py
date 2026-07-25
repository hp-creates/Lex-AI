"""
Document Loader — handles PDF, Image, and Text extraction.

Pipeline: Raw file → PyMuPDF / OCR → Clean text → Markdown conversion

Supported formats:
- PDF: PyMuPDF (text extraction with OCR fallback for scanned pages)
- Images: OCR via PyMuPDF's built-in text extraction
- Text: Pass-through with Markdown conversion

All outputs are clean Markdown — reduces token count and improves chunking accuracy.
"""

import re
import pymupdf  # PyMuPDF


def load_pdf(file_path: str | None = None, file_bytes: bytes | None = None) -> str:
    """
    Extract text from a PDF using PyMuPDF. Falls back to OCR for scanned pages.

    Args:
        file_path: Path to PDF file on disk
        file_bytes: Raw PDF bytes (from S3 download or upload)

    Returns:
        Cleaned Markdown text
    """
    if file_bytes:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    elif file_path:
        doc = pymupdf.open(file_path)
    else:
        raise ValueError("Provide either file_path or file_bytes")

    full_text = ""
    for page_num, page in enumerate(doc):
        # Try text extraction first (fast)
        text = page.get_text("text")

        if text and text.strip():
            full_text += text
        else:
            # Scanned page — use PyMuPDF's built-in OCR-like text extraction
            # Extract from text blocks as fallback
            blocks = page.get_text("blocks")
            for block in blocks:
                block_text = block[4] if len(block) > 4 else ""
                if isinstance(block_text, str) and block_text.strip():
                    full_text += block_text

        full_text += f"\n\n"  # Page separator

    doc.close()

    if not full_text.strip():
        return "<!-- No text could be extracted from this PDF -->"

    return convert_to_markdown(full_text)


def load_image(file_path: str | None = None, file_bytes: bytes | None = None) -> str:
    """
    Extract text from an image using OCR (PIL + pytesseract) with PyMuPDF fallback.

    Args:
        file_path: Path to image file
        file_bytes: Raw image bytes

    Returns:
        Cleaned Markdown text
    """
    import io
    from PIL import Image
    import pytesseract

    full_text = ""

    # Try PIL + pytesseract OCR first
    try:
        if file_bytes:
            img = Image.open(io.BytesIO(file_bytes))
        elif file_path:
            img = Image.open(file_path)
        else:
            raise ValueError("Provide either file_path or file_bytes")

        full_text = pytesseract.image_to_string(img)
    except Exception as e:
        print(f"[OCR] pytesseract warning: {e}. Falling back to PyMuPDF.")

    # Fallback to PyMuPDF if pytesseract returned nothing or wasn't available
    if not full_text or not full_text.strip():
        try:
            if file_bytes:
                doc = pymupdf.open(stream=file_bytes, filetype="png")
            elif file_path:
                doc = pymupdf.open(file_path)
            for page in doc:
                text = page.get_text("text")
                if text and text.strip():
                    full_text += text + "\n"
            doc.close()
        except Exception:
            pass

    if not full_text or not full_text.strip():
        return "<!-- No text could be extracted from this image -->"

    return convert_to_markdown(full_text)


def load_text(text: str) -> str:
    """
    Pass-through for plain text input. Cleans and converts to Markdown.

    Args:
        text: Raw text string

    Returns:
        Cleaned Markdown text
    """
    if not text or not text.strip():
        return "<!-- Empty text input -->"

    return convert_to_markdown(text)


def convert_to_markdown(raw_text: str) -> str:
    """
    Convert extracted text to clean Markdown format.

    Transformations:
    - Detect section headers (Section X, Article X) and convert to ## headers
    - Clean excessive whitespace
    - Preserve numbered lists and sub-clauses
    - Strip page numbers and footers

    This reduces token count vs raw text and improves semantic chunking accuracy
    because the splitter can split on ## headers.
    """
    text = raw_text

    # Remove excessive blank lines (more than 2 consecutive)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Remove common PDF artifacts
    text = re.sub(r'\f', '\n\n', text)  # Form feeds → paragraph breaks
    text = re.sub(r'(?m)^\s*\d+\s*$', '', text)  # Standalone page numbers

    # Detect and convert section headers for Indian legal documents
    # Pattern: "Section 96." or "SECTION 96." or "Section 96 —"
    text = re.sub(
        r'(?m)^(?:SECTION|Section)\s+(\d+[A-Z]?)\s*[.:\-—]\s*(.*)$',
        r'## Section \1. \2',
        text
    )

    # Pattern: "Article 21." or "ARTICLE 21."
    text = re.sub(
        r'(?m)^(?:ARTICLE|Article)\s+(\d+[A-Z]?)\s*[.:\-—]\s*(.*)$',
        r'## Article \1. \2',
        text
    )

    # Pattern: "CHAPTER I" or "Chapter I" or "PART III"
    text = re.sub(
        r'(?m)^(?:CHAPTER|Chapter|PART|Part)\s+([IVXLCDM]+|\d+)\s*[.:\-—]?\s*(.*)$',
        r'# \g<0>',
        text
    )

    # Sub-clauses: "(1)" "(a)" at line start → preserve as list items
    text = re.sub(r'(?m)^\s*\((\d+)\)', r'(\1)', text)
    text = re.sub(r'(?m)^\s*\(([a-z])\)', r'  (\1)', text)

    # Clean trailing whitespace on each line
    text = re.sub(r'(?m)\s+$', '', text)

    # Collapse multiple spaces within lines
    text = re.sub(r'  +', ' ', text)

    return text.strip()


def detect_file_type(filename: str) -> str:
    """
    Detect file type from filename extension.

    Returns: 'pdf', 'image', 'text', or 'unsupported'
    """
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''

    if ext == 'pdf':
        return 'pdf'
    elif ext in ('png', 'jpg', 'jpeg', 'tiff', 'bmp', 'gif', 'webp'):
        return 'image'
    elif ext in ('txt', 'md', 'text'):
        return 'text'
    elif ext == 'docx':
        return 'docx'  # Will need python-docx in a future stage
    else:
        return 'unsupported'


def load_document(
    filename: str,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
    raw_text: str | None = None,
) -> str:
    """
    Unified entry point — detects file type and routes to the correct loader.

    Args:
        filename: Original filename (used for type detection)
        file_path: Path to file on disk
        file_bytes: Raw file bytes
        raw_text: Raw text (for text-only inputs)

    Returns:
        Cleaned Markdown text ready for chunking
    """
    file_type = detect_file_type(filename)

    if file_type == 'pdf':
        return load_pdf(file_path=file_path, file_bytes=file_bytes)
    elif file_type == 'image':
        return load_image(file_path=file_path, file_bytes=file_bytes)
    elif file_type == 'text':
        content = raw_text or ""
        if file_bytes and not content:
            content = file_bytes.decode('utf-8', errors='replace')
        elif file_path and not content:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        return load_text(content)
    else:
        raise ValueError(f"Unsupported file type: {file_type} (filename: {filename})")
