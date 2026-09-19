"""
Qdrant Migration Script — copy vectors from local Qdrant to Qdrant Cloud.

Reads all points (vectors + payloads) from the local Qdrant instance and
upserts them to Qdrant Cloud. No re-embedding needed — vectors are already
computed.

Usage:
  1. Start local Qdrant:  docker compose up qdrant -d
  2. Set your Qdrant Cloud credentials below (or via env vars)
  3. Run:  uv run python scripts/migrate_qdrant.py

Env vars:
  QDRANT_CLOUD_URL   — Your Qdrant Cloud cluster URL
  QDRANT_CLOUD_KEY   — Your Qdrant Cloud API key
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    VectorParams,
)


# === Configuration ===
def _load_dotenv(path: str) -> dict:
    """Minimal .env parser — no external dependencies."""
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip().strip('"').strip("'")
    return env

# Load backend/.env for credentials
_dotenv = _load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

LOCAL_HOST = os.environ.get("QDRANT_HOST", _dotenv.get("QDRANT_HOST", "localhost"))
LOCAL_PORT = int(os.environ.get("QDRANT_PORT", _dotenv.get("QDRANT_PORT", "6333")))

CLOUD_URL = (
    os.environ.get("QDRANT_CLOUD_URL")
    or os.environ.get("QDRANT_URL")
    or _dotenv.get("QDRANT_URL")
    or "https://4be5afdc-a177-48a5-96fa-c56c0c98eb4a.sa-east-1-0.aws.cloud.qdrant.io"
)
CLOUD_KEY = (
    os.environ.get("QDRANT_CLOUD_KEY")
    or os.environ.get("QDRANT_API_KEY")
    or _dotenv.get("QDRANT_API_KEY")
    or ""
)

COLLECTIONS = ["indian_law_corpus", "user_documents"]
BATCH_SIZE = 100  # Points per upsert batch
SCROLL_SIZE = 100  # Points per scroll page


def migrate_collection(
    local: QdrantClient,
    cloud: QdrantClient,
    collection_name: str,
    vector_size: int = 1024,
):
    """Migrate a single collection from local to cloud Qdrant."""

    # Get local collection info
    try:
        local_info = local.get_collection(collection_name)
        point_count = local_info.points_count
    except Exception as e:
        print(f"  [SKIP] Collection '{collection_name}' not found locally: {e}")
        return 0

    if point_count == 0:
        print(f"  [SKIP] Collection '{collection_name}' is empty.")
        # Still create it on cloud (for user_documents)
        _create_collection(cloud, collection_name, vector_size)
        return 0

    print(f"  [INFO] Local '{collection_name}': {point_count} points")

    # Create collection on cloud (idempotent)
    _create_collection(cloud, collection_name, vector_size)

    # Scroll through all points and upsert in batches
    migrated = 0
    offset = None  # Start from the beginning

    while True:
        # Scroll returns (points, next_offset)
        results, next_offset = local.scroll(
            collection_name=collection_name,
            limit=SCROLL_SIZE,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )

        if not results:
            break

        # Convert to PointStruct for upsert
        points = []
        for point in results:
            points.append(PointStruct(
                id=point.id,
                vector=point.vector,
                payload=point.payload,
            ))

        # Batch upsert to cloud
        for i in range(0, len(points), BATCH_SIZE):
            batch = points[i:i + BATCH_SIZE]
            cloud.upsert(
                collection_name=collection_name,
                points=batch,
            )
            migrated += len(batch)
            print(f"  [PROGRESS] {migrated}/{point_count} points migrated", end="\r")

        if next_offset is None:
            break
        offset = next_offset

    print(f"  [DONE] {migrated}/{point_count} points migrated to cloud.          ")

    # Verify counts match
    cloud_info = cloud.get_collection(collection_name)
    cloud_count = cloud_info.points_count
    if cloud_count == point_count:
        print(f"  [VERIFIED] Cloud count matches: {cloud_count} (OK)")
    else:
        print(f"  [WARNING] Count mismatch! Local: {point_count}, Cloud: {cloud_count}")

    return migrated


def _create_collection(client: QdrantClient, name: str, vector_size: int):
    """Create collection if it doesn't exist."""
    existing = [c.name for c in client.get_collections().collections]
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        print(f"  [CREATED] Collection '{name}' on cloud.")
    else:
        print(f"  [EXISTS] Collection '{name}' already on cloud.")


def main():
    if not CLOUD_KEY:
        print("=" * 60)
        print("ERROR: Qdrant Cloud API key not set!")
        print()
        print("Set it via:")
        print("  1. Environment variable:  set QDRANT_CLOUD_KEY=your_key_here")
        print("  2. Or edit CLOUD_KEY in this script")
        print()
        print("Get your API key from: https://cloud.qdrant.io")
        print("=" * 60)
        sys.exit(1)

    print("=" * 60)
    print("  Qdrant Migration: Local -> Cloud")
    print("=" * 60)
    print(f"  Source:  {LOCAL_HOST}:{LOCAL_PORT}")
    print(f"  Target:  {CLOUD_URL}")
    print(f"  Collections: {', '.join(COLLECTIONS)}")
    print()

    # Connect to local Qdrant
    print("[1/3] Connecting to local Qdrant...")
    local = QdrantClient(host=LOCAL_HOST, port=LOCAL_PORT, timeout=30)
    try:
        local.get_collections()
        print("  [OK] Local Qdrant is reachable.")
    except Exception as e:
        print(f"  [ERROR] Cannot connect to local Qdrant: {e}")
        print("  Make sure Docker is running: docker compose up qdrant -d")
        sys.exit(1)

    # Connect to cloud Qdrant
    print("[2/3] Connecting to Qdrant Cloud...")
    cloud = QdrantClient(url=CLOUD_URL, api_key=CLOUD_KEY, timeout=60)
    try:
        cloud.get_collections()
        print("  [OK] Qdrant Cloud is reachable.")
    except Exception as e:
        print(f"  [ERROR] Cannot connect to Qdrant Cloud: {e}")
        print("  Check your CLOUD_URL and CLOUD_KEY.")
        sys.exit(1)

    # Migrate each collection
    print("[3/3] Migrating collections...")
    start = time.time()
    total = 0

    for collection in COLLECTIONS:
        print(f"\n--- {collection} ---")
        count = migrate_collection(local, cloud, collection)
        total += count

    elapsed = time.time() - start

    print(f"\n{'=' * 60}")
    print(f"  MIGRATION COMPLETE")
    print(f"  Total points migrated: {total}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
