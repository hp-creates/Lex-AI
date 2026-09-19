import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

c = QdrantClient(host="localhost", port=6333)
info = c.get_collection("indian_law_corpus")
print(f"Total points in indian_law_corpus: {info.points_count}")

acts = ["BNS", "BNSS", "COI", "CPA", "CrPC", "DV", "I PC", "ITA", "MVA", "POCSO", "RTI"]
for a in acts:
    count = c.count(
        collection_name="indian_law_corpus",
        count_filter=Filter(must=[FieldCondition(key="act_short", match=MatchValue(value=a))]),
    ).count
    status = "DONE" if count > 0 else "MISSING"
    print(f"  [{status:>7}] {a:>6}: {count} points")
