"""
Corpus Ingestion Script -- bulk load legal PDFs into Qdrant + BM25.

Usage:
  uv run python scripts/ingest_corpus.py              # Fresh ingestion (21s delay/batch)
  uv run python scripts/ingest_corpus.py --resume     # Skip already-ingested PDFs
  uv run python scripts/ingest_corpus.py --fast        # No rate limit delay
  uv run python scripts/ingest_corpus.py --wipe        # Delete all vectors first, then ingest

Reads all PDFs from data/corpus/ and:
1. Extracts text via PyMuPDF
2. Chunks with semantic splitter
3. Embeds with BAAI/bge-3 model (local / HF-api)
4. Upserts to Qdrant (indian_law_corpus collection)
5. Adds to BM25 index

Expected corpus directory structure:
  data/corpus/
    IPC.pdf
    CrPC.pdf
    Constitution_of_India.pdf
    ...

Configure act metadata via the CORPUS_METADATA dict below.
"""

import sys
import os
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.doc_loader import load_pdf
from app.services.chunker import chunk_document
from app.services.embedder import embedder
from app.services.vector_store import vector_store
from app.services.bm25_search import bm25_index
from app.config import settings

from qdrant_client.http.models import Filter, FieldCondition, MatchValue


# === Corpus Metadata ===
# Map each PDF filename to its full name + abbreviation.
# Add new entries here when adding new law PDFs.
CORPUS_METADATA = {
    "IPC.pdf": {
        "source": "Indian Penal Code, 1860",
        "act_short": "IPC",
    },
    "CrPC.pdf": {
        "source": "Code of Criminal Procedure, 1973",
        "act_short": "CrPC",
    },
    "Constitution_of_India.pdf": {
        "source": "Constitution of India",
        "act_short": "COI",
    },
    "BNS.pdf": {
        "source": "Bharatiya Nyaya Sanhita, 2023",
        "act_short": "BNS",
    },
    "BNSS.pdf": {
        "source": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "act_short": "BNSS",
    },
    "MVA.pdf": {
        "source": "Motor Vehicles Act, 1988",
        "act_short": "MVA",
    },
    "ITA.pdf": {
        "source": "Information Technology Act, 2000",
        "act_short": "ITA",
    },
    "CPA.pdf": {
        "source": "Consumer Protection Act, 2019",
        "act_short": "CPA",
    },
    "POCSO.pdf": {
        "source": "Protection of Children from Sexual Offences Act, 2012",
        "act_short": "POCSO",
    },
    "DV.pdf": {
        "source": "Protection of Women from Domestic Violence Act, 2005",
        "act_short": "DV",
    },
    "RTI.pdf": {
        "source": "Right to Information Act, 2005",
        "act_short": "RTI",
    },
    "BSA.pdf": {
        "source": "Bharatiya Sakshya Adhiniyam, 2023",
        "act_short": "BSA",
    },
    "DPDA.pdf": {
        "source": "Digital Personal Data Protection Act, 2023",
        "act_short": "DPDPA",
    },
    "HMA.pdf": {
        "source": "Hindu Marriage Act, 1955",
        "act_short": "HMA",
    },
    "POSH.pdf": {
        "source": "Sexual Harassment of Women at Workplace Act, 2013",
        "act_short": "POSH",
    },
    "SMA.pdf": {
        "source": "Special Marriage Act, 1954",
        "act_short": "SMA",
    },
}

# Default metadata for PDFs not in the dict above
DEFAULT_META = lambda filename: {
    "source": filename.replace(".pdf", "").replace("_", " "),
    "act_short": filename.replace(".pdf", "").upper()[:6],
}


def ingest_corpus(
    corpus_dir: str = "data/corpus",
    rate_limit_delay: float = 21.0,
    resume: bool = False,
    wipe: bool = False,
):
    """
    Run the full corpus ingestion pipeline.

    Args:
        corpus_dir: Path to directory containing law PDFs
        rate_limit_delay: Seconds to wait between embedding API calls.
                         Set to 21s for Voyage free tier (3 RPM).
                         Set to 0 if you have a paid account (300 RPM).
        resume: If True, skip PDFs already present in Qdrant.
        wipe: If True, delete all existing vectors before ingesting.
    """
    corpus_path = Path(corpus_dir)

    if not corpus_path.exists():
        print(f"[ERROR] Corpus directory not found: {corpus_path.absolute()}")
        print(f"[INFO] Create {corpus_path.absolute()} and add PDF files to it.")
        sys.exit(1)

    pdf_files = sorted(corpus_path.glob("*.pdf"))
    if not pdf_files:
        print(f"[ERROR] No PDF files found in {corpus_path.absolute()}")
        sys.exit(1)

    print(f"\n[CORPUS] Found {len(pdf_files)} PDFs in {corpus_path.absolute()}")
    for f in pdf_files:
        print(f"  - {f.name} ({f.stat().st_size / 1024:.0f} KB)")

    # Initialize services
    print("\n[INIT] Loading embedding model...")
    embedder.load()

    print("[INIT] Connecting to Qdrant...")
    vector_store.init_client()
    vector_store.create_collections(vector_size=embedder.dimensions)

    # Wipe existing vectors if requested
    if wipe:
        print("[WIPE] Deleting ALL existing vectors from indian_law_corpus...")
        vector_store.client.delete_collection(settings.QDRANT_LAW_COLLECTION)
        vector_store.create_collections(vector_size=embedder.dimensions)
        print("[WIPE] Collection wiped and recreated.")

    # Clear BM25 for fresh rebuild (BM25 is always rebuilt — it's fast, no API calls)
    bm25_index.clear()

    total_chunks = 0
    total_time = 0
    results = []

    for pdf_file in pdf_files:
        print(f"\n{'=' * 60}")
        print(f"[PROCESS] {pdf_file.name}")
        print("=" * 60)
        start = time.time()

        # Get metadata
        meta = CORPUS_METADATA.get(pdf_file.name, DEFAULT_META(pdf_file.name))
        source = meta["source"]
        act_short = meta["act_short"]

        # --- Resume check: skip if already in Qdrant ---
        if resume:
            existing = vector_store.client.count(
                collection_name=settings.QDRANT_LAW_COLLECTION,
                count_filter=Filter(
                    must=[FieldCondition(key="act_short", match=MatchValue(value=act_short))]
                ),
            ).count
            if existing > 0:
                print(f"  [SKIP] Already in Qdrant ({existing} points). Use --wipe to re-ingest.")
                # Still add to BM25 (needs all docs for keyword search)
                print(f"  [1/4] Extracting text for BM25 index...")
                text = load_pdf(file_path=str(pdf_file))
                if len(text) >= 100:
                    chunks = chunk_document(text=text, source=source, act_short=act_short, collection="indian_law_corpus")
                    bm25_index.add_documents(chunks)
                    print(f"  [BM25] Added {len(chunks)} chunks to keyword index.")
                results.append({"file": pdf_file.name, "source": source, "chunks": existing, "time_s": 0, "status": "SKIP"})
                continue

        # Step 1: Extract text
        print(f"  [1/4] Extracting text from {pdf_file.name}...")
        text = load_pdf(file_path=str(pdf_file))
        print(f"        -> {len(text)} chars extracted")

        if len(text) < 100:
            print(f"  [SKIP] Too little text extracted ({len(text)} chars). Skipping.")
            results.append({"file": pdf_file.name, "status": "SKIPPED", "reason": "too little text"})
            continue

        # Step 2: Chunk
        print(f"  [2/4] Chunking ({source})...")
        chunks = chunk_document(
            text=text,
            source=source,
            act_short=act_short,
            collection="indian_law_corpus",
        )
        print(f"        -> {len(chunks)} chunks")

        # Step 3: Embed (batch)
        print(f"  [3/4] Embedding {len(chunks)} chunks...")
        chunk_texts = [c["text"] for c in chunks]

        # Batch size: local mode = 64 (limited by RAM only), API mode = 8 (rate limits)
        BATCH_SIZE = 64 if settings.EMBEDDING_MODE == "local" else 8
        all_embeddings = []
        total_batches = (len(chunk_texts) + BATCH_SIZE - 1) // BATCH_SIZE
        for i in range(0, len(chunk_texts), BATCH_SIZE):
            batch = chunk_texts[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1

            # Proactive rate limit delay (skip before first batch)
            if i > 0 and rate_limit_delay > 0:
                print(f"        -> Waiting {rate_limit_delay:.0f}s (rate limit)...")
                time.sleep(rate_limit_delay)

            batch_embeddings = embedder.embed_documents(batch)
            all_embeddings.extend(batch_embeddings)
            print(f"        -> Batch {batch_num}/{total_batches} ({len(batch)} chunks)")

        # Step 4: Upsert to Qdrant + BM25
        print(f"  [4/4] Upserting to Qdrant + BM25...")
        vector_store.upsert_chunks(
            collection=settings.QDRANT_LAW_COLLECTION,
            chunks=chunks,
            embeddings=all_embeddings,
        )
        bm25_index.add_documents(chunks)

        elapsed = time.time() - start
        total_chunks += len(chunks)
        total_time += elapsed

        results.append({
            "file": pdf_file.name,
            "source": source,
            "chunks": len(chunks),
            "chars": len(text),
            "time_s": round(elapsed, 1),
            "status": "OK",
        })

        print(f"  [DONE] {len(chunks)} chunks in {elapsed:.1f}s")

    # Summary
    print(f"\n{'=' * 60}")
    print("  CORPUS INGESTION COMPLETE")
    print("=" * 60)
    print(f"\n  Total PDFs: {len(pdf_files)}")
    print(f"  Total chunks: {total_chunks}")
    print(f"  Total time: {total_time:.1f}s")
    print(f"  BM25 index: {bm25_index.doc_count} documents")

    # Collection stats
    info = vector_store.get_collection_info(settings.QDRANT_LAW_COLLECTION)
    print(f"  Qdrant: {info.get('points_count', '?')} points in '{settings.QDRANT_LAW_COLLECTION}'")

    print("\n  Results:")
    print(f"  {'File':<30} {'Source':<35} {'Chunks':>6} {'Time':>6} {'Status':>8}")
    print(f"  {'-'*30} {'-'*35} {'-'*6} {'-'*6} {'-'*8}")
    for r in results:
        print(f"  {r['file']:<30} {r.get('source', ''):<35} {r.get('chunks', '-'):>6} {r.get('time_s', '-'):>5}s {r['status']:>8}")


if __name__ == "__main__":
    import sys
    import os

    # Parse CLI flags
    resume = "--resume" in sys.argv
    wipe = "--wipe" in sys.argv
    force_local = "--local" in sys.argv  # Override EMBEDDING_MODE=api for ingestion

    if wipe and resume:
        print("[ERROR] Cannot use --wipe and --resume together.")
        sys.exit(1)

    # --local flag forces local SentenceTransformer mode regardless of .env
    # This lets the server run in api mode while ingestion uses local (fast, no rate limits)
    from app.config import settings as _s
    if force_local:
        os.environ["EMBEDDING_MODE"] = "local"
        # Re-read settings after override
        _s.EMBEDDING_MODE = "local"
        print(f"[INFO] --local flag: overriding EMBEDDING_MODE to 'local'")

    if _s.EMBEDDING_MODE == "local":
        delay = 0.0
        print(f"[INFO] Local mode: using SentenceTransformer ({_s.EMBEDDING_MODEL})")
        print("[INFO] No API rate limits — full speed ingestion.")
    else:
        delay = 0.0 if "--fast" in sys.argv else 21.0
        if delay > 0:
            print("[INFO] API mode with rate limit delays (21s/batch).")
            print("[INFO] Use --fast to skip delays (if your API plan allows).")
        else:
            print("[INFO] API mode, fast (no rate limit delays).")

    if resume:
        print("[INFO] Resume mode: skipping PDFs already in Qdrant.")
    if wipe:
        print("[INFO] Wipe mode: deleting ALL existing vectors first.")

    ingest_corpus(rate_limit_delay=delay, resume=resume, wipe=wipe)

