"""
Pinecone Vector Memory Tool — Semantic recall of past incidents, runbooks, and KB articles.

Provides two core operations:
1. query() — Retrieve semantically similar past experiences
2. upsert() — Store new experiences for future recall (experience distillation)

Usage:
    from src.tools.query_pinecone import query_memory, upsert_memory
    results = query_memory("ADFS authentication failing for external users")
    upsert_memory("lesson-2026-02-21", "Root cause was expired SAML cert...", {"client": "GR Energy"})
"""
import os
import json
import logging
import hashlib
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("tools.pinecone")

# Lazy-loaded clients
_pc_index = None
_openai_client = None


def _get_openai_client():
    """Lazy-load OpenAI client for embeddings."""
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY is required for embedding generation. "
                "Set it in your .env file."
            )
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def _get_pinecone_index():
    """Lazy-load Pinecone index."""
    global _pc_index
    if _pc_index is None:
        from pinecone import Pinecone
        api_key = os.getenv("PINECONE_API_KEY", "").strip()
        if not api_key:
            raise EnvironmentError(
                "PINECONE_API_KEY is required. Set it in your .env file."
            )
        index_name = os.getenv("PINECONE_INDEX_NAME", "pa-memory")
        pc = Pinecone(api_key=api_key)

        # Check if index exists; if not, create it
        existing = [idx.name for idx in pc.list_indexes()]
        if index_name not in existing:
            logger.info("[Pinecone] Index '%s' not found. Creating...", index_name)
            from pinecone import ServerlessSpec
            pc.create_index(
                name=index_name,
                dimension=1536,  # text-embedding-3-small dimension
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            logger.info("[Pinecone] Index '%s' created.", index_name)

        _pc_index = pc.Index(index_name)
    return _pc_index


def _embed(text: str) -> list[float]:
    """Generate an embedding vector for the given text."""
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    client = _get_openai_client()
    resp = client.embeddings.create(input=[text], model=model)
    return resp.data[0].embedding


def _make_id(text: str) -> str:
    """Generate a deterministic ID from text content."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def query_memory(
    query: str,
    *,
    top_k: int = 5,
    filter_metadata: Optional[dict] = None,
    min_score: float = 0.7,
) -> list[dict]:
    """
    Query Pinecone for semantically similar past incidents, runbooks, or KB articles.

    Args:
        query: Natural language description of the current problem/need
        top_k: Number of results to return
        filter_metadata: Optional Pinecone metadata filter (e.g., {"client": "GR Energy"})
        min_score: Minimum cosine similarity score to include

    Returns:
        List of dicts, each with:
            - "score": float (0–1 cosine similarity)
            - "content": str (the stored text)
            - "metadata": dict (category, date, client, etc.)
            - "id": str (vector ID)
    """
    logger.info("[Pinecone] Querying: %s", query[:80])

    try:
        embedding = _embed(query)
        index = _get_pinecone_index()

        query_params = {
            "vector": embedding,
            "top_k": top_k,
            "include_metadata": True,
        }
        if filter_metadata:
            query_params["filter"] = filter_metadata

        results = index.query(**query_params)

        matches = []
        for match in results.get("matches", []):
            if match["score"] >= min_score:
                matches.append({
                    "score": round(match["score"], 4),
                    "content": match.get("metadata", {}).get("content", ""),
                    "metadata": {
                        k: v for k, v in match.get("metadata", {}).items()
                        if k != "content"
                    },
                    "id": match["id"],
                })

        logger.info(
            "[Pinecone] Found %d matches (>%.2f) out of %d total",
            len(matches), min_score, len(results.get("matches", [])),
        )
        return matches

    except EnvironmentError:
        logger.warning("[Pinecone] Not configured — returning empty results")
        return []
    except Exception as e:
        logger.error("[Pinecone] Query failed: %s", e)
        return []


def upsert_memory(
    doc_id: str,
    content: str,
    metadata: Optional[dict] = None,
) -> bool:
    """
    Store a new experience vector in Pinecone (experience distillation).

    Args:
        doc_id: Unique identifier for the document (e.g., "incident-2026-02-21-entra-sync")
        content: The text content to embed and store
        metadata: Additional metadata (category, client, date, tags, etc.)

    Returns:
        True if upsert succeeded, False otherwise
    """
    logger.info("[Pinecone] Upserting: %s (%d chars)", doc_id, len(content))

    try:
        embedding = _embed(content)
        index = _get_pinecone_index()

        meta = metadata or {}
        meta["content"] = content[:4000]  # Pinecone metadata limit ~40KB
        meta["ingested_at"] = datetime.now(timezone.utc).isoformat()
        meta.setdefault("source", "agent-distillation")

        index.upsert(vectors=[{
            "id": doc_id,
            "values": embedding,
            "metadata": meta,
        }])

        logger.info("[Pinecone] Upserted '%s' successfully", doc_id)
        return True

    except Exception as e:
        logger.error("[Pinecone] Upsert failed: %s", e)
        return False


def bulk_upsert(documents: list[dict], batch_size: int = 50) -> int:
    """
    Batch upsert multiple documents. Each doc should have: id, content, metadata.

    Returns:
        Number of successfully upserted documents
    """
    logger.info("[Pinecone] Bulk upserting %d documents...", len(documents))
    count = 0

    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        vectors = []
        for doc in batch:
            try:
                emb = _embed(doc["content"])
                meta = doc.get("metadata", {})
                meta["content"] = doc["content"][:4000]
                meta["ingested_at"] = datetime.now(timezone.utc).isoformat()
                vectors.append({
                    "id": doc.get("id", _make_id(doc["content"])),
                    "values": emb,
                    "metadata": meta,
                })
            except Exception as e:
                logger.error("[Pinecone] Failed to embed doc '%s': %s", doc.get("id"), e)

        if vectors:
            try:
                index = _get_pinecone_index()
                index.upsert(vectors=vectors)
                count += len(vectors)
            except Exception as e:
                logger.error("[Pinecone] Batch upsert failed: %s", e)

    logger.info("[Pinecone] Bulk upsert complete: %d/%d succeeded", count, len(documents))
    return count


if __name__ == "__main__":
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

    # Test query
    results = query_memory("ADFS authentication failing for external users")
    for r in results:
        print(f"Match ({r['score']}): {r['content'][:100]}...")
        print(f"  Metadata: {r['metadata']}")
