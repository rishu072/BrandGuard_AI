"""Optional Qdrant retrieval. The default demo keeps using lexical retrieval."""

from __future__ import annotations

import logging
from uuid import NAMESPACE_URL, uuid5

from .config import QDRANT_API_KEY, QDRANT_COLLECTION, QDRANT_EMBED_MODEL, QDRANT_URL

logger = logging.getLogger(__name__)
_client = None
_embedder = None
_collection_ready: set[str] = set()


def configured() -> bool:
    return bool(QDRANT_URL)


def _dependencies():
    global _client, _embedder
    if _client is None:
        from qdrant_client import QdrantClient
        from fastembed import TextEmbedding

        _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None, timeout=8)
        _embedder = TextEmbedding(model_name=QDRANT_EMBED_MODEL)
    return _client, _embedder


def _sources(brand: dict) -> list[dict]:
    sources = []
    for item in brand.get("sources", []):
        if item.get("status", "Approved").lower() != "approved":
            continue
        content = item.get("content") or item.get("summary") or ""
        if content.strip():
            sources.append({"id": item.get("id", ""), "title": item.get("title", "Approved source"), "text": content})
    for item in brand.get("facts", []):
        if item.get("status", "").lower() != "approved":
            continue
        content = item.get("source_excerpt") or f"{item.get('title', '')}: {item.get('value', '')}"
        if content.strip():
            sources.append({"id": item.get("id", ""), "title": item.get("title", "Approved fact"), "text": content})
    return sources


def _ensure_index(organization_id: str, brand: dict, client, embedder) -> None:
    from qdrant_client import models

    if QDRANT_COLLECTION not in _collection_ready:
        if not client.collection_exists(QDRANT_COLLECTION):
            client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=models.VectorParams(
                    size=type(embedder).get_embedding_size(QDRANT_EMBED_MODEL),
                    distance=models.Distance.COSINE,
                ),
            )
        _collection_ready.add(QDRANT_COLLECTION)
    documents = _sources(brand)
    if not documents:
        return
    vectors = list(embedder.embed([item["text"] for item in documents]))
    points = []
    for item, vector in zip(documents, vectors):
        point_id = str(uuid5(NAMESPACE_URL, f"brandguard:{organization_id}:{item['id']}"))
        points.append(
            models.PointStruct(
                id=point_id,
                vector=vector.tolist(),
                payload={
                    "organization_id": organization_id,
                    "source_id": item["id"],
                    "title": item["title"],
                    "text": item["text"],
                },
            )
        )
    client.upsert(collection_name=QDRANT_COLLECTION, points=points, wait=True)


def retrieve_qdrant_sources(text: str, brand: dict, organization_id: str, limit: int = 4) -> list[dict[str, str]] | None:
    if not configured():
        return None
    try:
        from qdrant_client import models

        client, embedder = _dependencies()
        _ensure_index(organization_id, brand, client, embedder)
        query_vector = next(embedder.query_embed(text)).tolist()
        response = client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vector,
            query_filter=models.Filter(
                must=[models.FieldCondition(key="organization_id", match=models.MatchValue(value=organization_id))]
            ),
            limit=limit,
            with_payload=True,
        )
        results = []
        for point in response.points:
            payload = point.payload or {}
            source_id = payload.get("source_id")
            if not source_id:
                continue
            results.append(
                {
                    "id": str(source_id),
                    "title": str(payload.get("title", "Approved source")),
                    "excerpt": str(payload.get("text", ""))[:1200],
                }
            )
        return results
    except Exception:
        logger.exception("Qdrant retrieval was unavailable; using lexical retrieval for this review.")
        return None
