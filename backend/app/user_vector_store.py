from typing import Any, Dict, List, Optional, Tuple

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from .config import (
    CHROMA_DIR,
    EMBED_MAX_CHARS,
    OLLAMA_BASE_URL,
    OLLAMA_EMBED_MODEL,
    QDRANT_API_KEY,
    QDRANT_URL,
    USER_COLLECTION_NAME,
    USER_QDRANT_COLLECTION,
    VECTOR_DB,
)

SAFE_EMBED_MAX_CHARS = 1000


def _get_qdrant_client() -> QdrantClient:
    if QDRANT_API_KEY:
        return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    return QdrantClient(url=QDRANT_URL)


def get_user_vector_store() -> VectorStore:
    embeddings = OllamaEmbeddings(model=OLLAMA_EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    if VECTOR_DB == "qdrant":
        client = _get_qdrant_client()
        return QdrantVectorStore(
            client=client,
            collection_name=USER_QDRANT_COLLECTION,
            embedding=embeddings,
        )
    return Chroma(
        collection_name=USER_COLLECTION_NAME,
        persist_directory=CHROMA_DIR,
        embedding_function=embeddings,
    )


def _build_user_document(row: Dict[str, Any]) -> Optional[Document]:
    if not row.get("id"):
        return None

    first = str(row.get("first_name") or "")
    last = str(row.get("last_name") or "")
    full = str(row.get("full_name") or "").strip()
    if not full:
        full = f"{first} {last}".strip()

    address = ", ".join(
        [str(row.get("addr1") or ""), str(row.get("addr2") or ""), str(row.get("city") or "")]
    ).strip(", ").strip()

    content_parts = [
        full,
        first,
        last,
        str(row.get("mobile") or ""),
        str(row.get("policynum") or ""),
        str(row.get("clntid") or ""),
        address,
    ]
    page_content = " ".join([p for p in content_parts if p]).strip()
    if not page_content:
        return None

    max_chars = min(EMBED_MAX_CHARS, SAFE_EMBED_MAX_CHARS)
    if max_chars > 0 and len(page_content) > max_chars:
        page_content = page_content[:max_chars]

    metadata = dict(row)
    metadata["full_name"] = full
    metadata["first_name"] = first
    metadata["last_name"] = last

    return Document(page_content=page_content, metadata=metadata, id=str(row["id"]))


def upsert_user_embedding(row: Dict[str, Any]) -> bool:
    doc = _build_user_document(row)
    if doc is None:
        return False
    store = get_user_vector_store()
    try:
        store.delete(ids=[doc.id])
    except Exception:
        pass
    store.add_documents(documents=[doc], ids=[doc.id])
    return True


def delete_user_embedding(user_id: str) -> bool:
    if not user_id:
        return False
    store = get_user_vector_store()
    try:
        store.delete(ids=[str(user_id)])
    except Exception:
        return False
    return True


def search_user_embeddings(
    query: str,
    k: int = 5,
) -> List[Tuple[Document, float]]:
    store = get_user_vector_store()
    return store.similarity_search_with_score(query, k=k)
