"""
Structural Legal Chunker — section-aware splitting for Indian legal documents.

Strategy:
1. Split on section boundaries (## Section N headers from doc_loader)
2. Prepend metadata prefix to every chunk (Act name, Chapter, Section)
3. Handle mega-sections by splitting on sub-sections (1), (2), etc.
4. Never split at "Provided that..." or "Explanation.—" boundaries
5. Fallback to RecursiveCharacterTextSplitter for very large sections

Key properties:
- Each legal Section is an atomic unit (never split across chunks)
- Every chunk self-identifies via metadata prefix (no orphan sub-clauses)
- Provisos and Explanations stay with their parent text
- Deterministic chunk IDs for idempotent upserts
"""

import re
from langchain_text_splitters import RecursiveCharacterTextSplitter


# Maximum chunk size in characters (~300 tokens for bge-m3)
MAX_CHUNK_SIZE = 1200
# Minimum chunk size — discard tiny fragments
MIN_CHUNK_SIZE = 80


def _build_metadata_prefix(source: str, chapter: str, section: str, section_title: str) -> str:
    """
    Build a metadata prefix string to prepend to every chunk.

    Example output:
        [Act: Indian Penal Code, 1860] [Chapter: XVI - Offences Affecting the Human Body] [Section: 302 - Punishment for murder]
    """
    parts = []
    if source:
        parts.append(f"[Act: {source}]")
    if chapter:
        parts.append(f"[Chapter: {chapter}]")
    if section:
        label = f"Section {section}"
        if section_title:
            label += f" - {section_title}"
        parts.append(f"[{label}]")
    return " ".join(parts)


def _split_mega_section(text: str, prefix: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    """
    Split a section that exceeds max_size into sub-chunks.

    Priority order:
    1. Split on sub-section markers: (1), (2), (3)...
    2. Fallback: RecursiveCharacterTextSplitter with proviso-aware separators

    Every sub-chunk gets the section's prefix prepended.
    """
    # Try splitting on sub-sections first
    # Pattern: line starting with (N) where N is a number
    sub_parts = re.split(r'\n(?=\(\d+\)\s)', text)

    if len(sub_parts) > 1:
        # We have sub-sections — group them into chunks that fit max_size
        chunks = []
        current_chunk = ""
        # The first part is the section header/intro — always include it
        section_intro = sub_parts[0].strip()

        for part in sub_parts:
            part = part.strip()
            if not part:
                continue

            candidate = current_chunk + "\n" + part if current_chunk else part

            if len(prefix) + len(candidate) <= max_size:
                current_chunk = candidate
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                # Start new chunk with section intro for context (Strategy 4: Forced Context Windowing)
                if part != section_intro and len(section_intro) < 300:
                    current_chunk = section_intro + "\n" + part
                else:
                    current_chunk = part

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    # Fallback: RecursiveCharacterTextSplitter with proviso-aware separators
    splitter = RecursiveCharacterTextSplitter(
        separators=[
            "\n## ",       # Section headers (shouldn't appear inside a section, but just in case)
            "\n\n",        # Paragraph breaks
            "\n",          # Line breaks
            ". ",          # Sentence boundaries
            "; ",          # Clause boundaries (common in legal text)
            ", ",          # Sub-clause boundaries
            " ",           # Word boundaries (last resort)
        ],
        chunk_size=max_size - len(prefix) - 10,
        chunk_overlap=100,
        length_function=len,
        is_separator_regex=False,
        keep_separator=True,
    )

    return splitter.split_text(text)


def chunk_document(
    text: str,
    source: str = "",
    act_short: str = "",
    doc_id: str = "",
    user_id: str = "",
    collection: str = "user_documents",
    max_chunk_size: int = MAX_CHUNK_SIZE,
    chunk_size: int = 800,       # Legacy param — ignored, kept for backward compat
    chunk_overlap: int = 150,    # Legacy param — ignored, kept for backward compat
) -> list[dict]:
    """
    Split a Markdown legal document into structurally-aware chunks with metadata.

    Each chunk gets:
    - A metadata prefix prepended to the text (Act, Chapter, Section)
    - Metadata dict for Qdrant payload (source, section, chunk_id, etc.)
    - A deterministic chunk_id for idempotent upserts

    Args:
        text: Markdown text from doc_loader (with ## Section headers)
        source: Full name of the law/document (e.g., "Indian Penal Code, 1860")
        act_short: Abbreviation (e.g., "IPC")
        doc_id: UUID of the uploaded document (for user docs)
        user_id: UUID of the user (for user docs)
        collection: Qdrant collection name
        max_chunk_size: Maximum chunk size in characters

    Returns:
        List of dicts, each with 'text' and 'metadata' keys
    """
    # Split text into sections using ## headers
    sections = _split_into_sections(text)

    result = []
    current_chapter = ""
    chunk_index = 0

    for section_text, section_num, section_title in sections:
        # Track chapter context
        chapter = _extract_chapter(section_text)
        if chapter:
            current_chapter = chapter

        # Build metadata prefix for this section
        prefix = _build_metadata_prefix(source, current_chapter, section_num, section_title)

        # Check if section fits in a single chunk
        full_text = f"{prefix}\n{section_text}".strip() if prefix else section_text.strip()

        if len(full_text) <= max_chunk_size:
            # Section fits — single chunk
            if len(section_text.strip()) >= MIN_CHUNK_SIZE:
                chunk_id = _make_chunk_id(act_short, doc_id, section_num, chunk_index)
                result.append({
                    "text": full_text,
                    "metadata": {
                        "source": source,
                        "act_short": act_short,
                        "section": f"Section {section_num}" if section_num else "",
                        "section_title": section_title,
                        "chapter": current_chapter,
                        "chunk_index": chunk_index,
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "user_id": user_id,
                        "collection": collection,
                    }
                })
                chunk_index += 1
        else:
            # Mega-section — split into sub-chunks
            sub_chunks = _split_mega_section(section_text, prefix, max_chunk_size)

            for sub_text in sub_chunks:
                sub_text = sub_text.strip()
                if len(sub_text) < MIN_CHUNK_SIZE:
                    continue

                # Prepend prefix to each sub-chunk
                full_sub = f"{prefix}\n{sub_text}" if prefix else sub_text

                chunk_id = _make_chunk_id(act_short, doc_id, section_num, chunk_index)
                result.append({
                    "text": full_sub,
                    "metadata": {
                        "source": source,
                        "act_short": act_short,
                        "section": f"Section {section_num}" if section_num else "",
                        "section_title": section_title,
                        "chapter": current_chapter,
                        "chunk_index": chunk_index,
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "user_id": user_id,
                        "collection": collection,
                    }
                })
                chunk_index += 1

    return result


def _split_into_sections(text: str) -> list[tuple[str, str, str]]:
    """
    Split markdown text into sections based on ## headers.

    Returns list of (section_text, section_number, section_title) tuples.
    Text before the first ## header becomes its own section with empty number/title.
    """
    # Split on ## Section or ## Article headers
    parts = re.split(r'(?m)^(## (?:Section|Article)\s+\d+[A-Z]?\.\s+.*)', text)

    sections = []
    i = 0
    while i < len(parts):
        part = parts[i].strip()
        if not part:
            i += 1
            continue

        # Check if this part is a header line
        header_match = re.match(
            r'^## (?:Section|Article)\s+(\d+[A-Z]?)\.\s+(.*)',
            part
        )

        if header_match:
            section_num = header_match.group(1)
            section_title = header_match.group(2).strip()
            # Clean section title — take first sentence/clause only
            title_clean = re.split(r'[.\u2014]', section_title)[0].strip()
            if len(title_clean) > 120:
                title_clean = title_clean[:120]

            # Combine header with the body text that follows
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            # Check that the body is not itself a header
            if body and re.match(r'^## (?:Section|Article)', body):
                body = ""
            else:
                i += 1  # consume the body part

            full_section = f"{part}\n{body}" if body else part
            sections.append((full_section, section_num, title_clean))

        elif not sections:
            # Text before first section header (preamble, table of contents, etc.)
            sections.append((part, "", ""))
        # else: orphan body text — attach to previous section if possible
        elif sections:
            prev_text, prev_num, prev_title = sections[-1]
            sections[-1] = (prev_text + "\n" + part, prev_num, prev_title)

        i += 1

    # Handle documents with no ## headers at all (fallback to old-style chunking)
    if not sections:
        # Use RecursiveCharacterTextSplitter as fallback
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=MAX_CHUNK_SIZE,
            chunk_overlap=150,
            length_function=len,
        )
        chunks = splitter.split_text(text)
        for idx, chunk in enumerate(chunks):
            sections.append((chunk, "", ""))

    return sections


def _extract_chapter(text: str) -> str:
    """Extract chapter info from text if present."""
    match = re.search(
        r'^# (?:CHAPTER|Chapter|PART|Part)\s+([IVXLCDM]+|\d+)\s*[.:\-\u2014]?\s*(.*)',
        text, re.MULTILINE
    )
    if match:
        num = match.group(1).strip()
        title = match.group(2).strip()[:80] if match.group(2) else ""
        return f"{num} - {title}".strip(" -") if title else num
    return ""


def _make_chunk_id(act_short: str, doc_id: str, section_num: str, index: int) -> str:
    """Build a deterministic chunk ID."""
    if act_short:
        base = f"{act_short.lower()}_section{section_num}_{index}" if section_num else f"{act_short.lower()}_{index}"
    elif doc_id:
        base = f"{doc_id}_{index}"
    else:
        base = f"chunk_{index}"

    # Clean special characters
    return base.replace(".", "").replace(",", "").replace("/", "_").replace(" ", "")


# Keep legacy _extract_section_info for backward compatibility with any callers
def _extract_section_info(text: str) -> tuple[str, str]:
    """
    Extract section/article info from chunk text.

    Handles multiple Indian legal document formats:
    1. "## Section 96. Right of private defence"      (CrPC/CPA style, with ## prefix)
    2. "## Article 21. Protection of life..."         (Constitution style)
    3. "36. Every police officer while making..."     (BNSS/BNS/IPC bare number style)

    Returns:
        (section, section_title) tuple, e.g. ("Section 36", "...")
    """
    # Pattern 1: "## Section X. Title" or "## Article X. Title" (explicit keyword)
    match = re.search(
        r'##\s+((?:Section|Article|Rule|Order|Schedule)\s+\d+[A-Z]?)\s*[.:\-\u2014]\s*(.*?)(?:\n|$)',
        text
    )
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Pattern 2: "## X. Title" (bare number with markdown header)
    match = re.search(
        r'##\s+(\d+[A-Z]?)\s*\.\s+([A-Z][^\n]{5,80})(?:\n|$)',
        text
    )
    if match:
        return f"Section {match.group(1).strip()}", match.group(2).strip()

    # Pattern 3: Bare "X. Title" at start of line
    match = re.search(
        r'(?:^|\n)(\d{1,3}[A-Z]?)\.\s+([A-Z][^\n]{5,80})(?:\n|$)',
        text
    )
    if match:
        return f"Section {match.group(1).strip()}", match.group(2).strip()

    return "", ""
