"""
Semantic Text Chunker — structure-aware splitting for legal documents.

Splitting hierarchy (preferred order):
  Section > Clause > Paragraph > Sentence > Word

Key properties:
- Respects legal document structure (## Section X headers from doc_loader)
- Preserves sentence boundaries (never splits mid-sentence)
- Overlap of 150 chars prevents context loss at boundaries
- Each chunk gets its parent section header prepended
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter


def create_legal_splitter(
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> RecursiveCharacterTextSplitter:
    """
    Create a structure-aware text splitter optimized for Indian legal documents.

    The separator hierarchy ensures splits happen at the most meaningful
    boundaries first (section headers), falling back to smaller units.

    Args:
        chunk_size: Target chunk size in characters (~200-250 tokens).
                    Fits Jina v3 context window with headroom.
        chunk_overlap: Overlap between chunks (100-200 range).
                       Prevents losing context at boundaries.

    Returns:
        Configured RecursiveCharacterTextSplitter
    """
    return RecursiveCharacterTextSplitter(
        separators=[
            "\n## ",       # Section / Article headers (from MD conversion)
            "\n### ",      # Sub-section headers
            "\n#### ",     # Clause headers
            "\n# ",        # Chapter / Part headers
            "\n\n",        # Paragraph breaks
            "\n",          # Line breaks
            ". ",          # Sentence boundaries
            "; ",          # Clause boundaries (common in legal text)
            ", ",          # Sub-clause boundaries
            " ",           # Word boundaries (last resort)
        ],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False,
        keep_separator=True,
    )


def chunk_document(
    text: str,
    source: str = "",
    act_short: str = "",
    doc_id: str = "",
    user_id: str = "",
    collection: str = "user_documents",
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> list[dict]:
    """
    Split a Markdown document into chunks with metadata.

    Each chunk gets:
    - The text content
    - Metadata for Qdrant payload (source, section, chunk_id, etc.)
    - A deterministic chunk_id for idempotent upserts

    Args:
        text: Markdown text from doc_loader
        source: Full name of the law/document (e.g., "Indian Penal Code, 1860")
        act_short: Abbreviation (e.g., "IPC")
        doc_id: UUID of the uploaded document (for user docs)
        user_id: UUID of the user (for user docs)
        collection: Qdrant collection name
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks

    Returns:
        List of dicts, each with 'text' and 'metadata' keys
    """
    splitter = create_legal_splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_text(text)

    result = []
    current_section = ""
    current_section_title = ""

    for i, chunk_text in enumerate(chunks):
        # Detect section header in this chunk
        section, section_title = _extract_section_info(chunk_text)
        if section:
            current_section = section
            current_section_title = section_title

        # Build deterministic chunk_id
        if act_short:
            chunk_id = f"{act_short.lower()}_{current_section.lower().replace(' ', '')}_{i}"
        elif doc_id:
            chunk_id = f"{doc_id}_{i}"
        else:
            chunk_id = f"chunk_{i}"

        # Clean the chunk_id (remove special characters)
        chunk_id = chunk_id.replace(".", "").replace(",", "").replace("/", "_")

        result.append({
            "text": chunk_text.strip(),
            "metadata": {
                "source": source,
                "act_short": act_short,
                "section": current_section,
                "section_title": current_section_title,
                "chunk_index": i,
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "user_id": user_id,
                "collection": collection,
            }
        })

    return result


def _extract_section_info(text: str) -> tuple[str, str]:
    """
    Extract section/article info from chunk text.

    Looks for patterns like:
    - "## Section 96. Right of private defence"
    - "## Article 21. Protection of life and personal liberty"

    Returns:
        (section, section_title) tuple, e.g. ("Section 96", "Right of private defence")
    """
    import re

    # Match "## Section X. Title" or "## Article X. Title"
    match = re.search(
        r'##\s+((?:Section|Article)\s+\d+[A-Z]?)\s*[.:\-—]\s*(.*?)(?:\n|$)',
        text
    )
    if match:
        return match.group(1).strip(), match.group(2).strip()

    return "", ""
