"""
Tavily Web Search — guarded fallback when corpus retrieval returns nothing.

Guardrails:
- Only fires when corpus + rewrite yield 0 relevant docs
- Prepends "Indian law" to queries to scope results
- Domain whitelist: prioritizes authoritative Indian legal sources
- Max 3 results to keep context tight
- All results tagged as "web_source" so the LLM knows they're not from the corpus
"""

from tavily import TavilyClient

from app.config import settings


# Authoritative Indian legal domains to prioritize
_INCLUDE_DOMAINS = [
    "indiankanoon.org",
    "indiacode.gov.in",
    "legislative.gov.in",
    "livelaw.in",
    "barandbench.com",
    "scconline.com",
    "sci.gov.in",
]


def tavily_search(query: str, max_results: int = 3) -> list[dict]:
    """
    Run a Tavily web search scoped to Indian law.

    Args:
        query: The user's legal question
        max_results: Max results to return (default 3)

    Returns:
        List of dicts with text, source, url keys — formatted like corpus chunks
        so they can be used directly by the generate node.
        Returns empty list if Tavily is not configured or fails.
    """
    if not settings.TAVILY_API_KEY:
        print("[WEB SEARCH] Skipped — TAVILY_API_KEY not set")
        return []

    # Scope the query to Indian law
    scoped_query = f"Indian law: {query}"

    try:
        client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        response = client.search(
            query=scoped_query,
            search_depth="basic",
            max_results=max_results,
            include_domains=_INCLUDE_DOMAINS,
            include_answer=False,
        )

        results = []
        for item in response.get("results", []):
            title = item.get("title", "")
            content = item.get("content", "")
            url = item.get("url", "")

            if not content.strip():
                continue

            # Format as a chunk compatible with the generate node
            results.append({
                "chunk_id": f"web_{hash(url) % 100000}",
                "text": f"[Web Source: {title}]\n{content}",
                "source": f"Web: {title[:80]}",
                "act_short": "",
                "section": "",
                "section_title": title[:100],
                "url": url,
                "collection": "web_search",
                "search_type": "web",
                "rrf_score": 0.5,  # Fixed score for web results
            })

        print(f"[WEB SEARCH] Query: '{scoped_query}' -> {len(results)} results")
        return results

    except Exception as e:
        print(f"[WEB SEARCH] Error: {e}")
        return []
