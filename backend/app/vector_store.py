import csv
import json
import os
import re
import shutil
import sqlite3
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from datasets import load_dataset
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from tqdm import tqdm

from .config import (
    CHROMA_DIR,
    COLLECTION_NAME,
    DATA_SOURCE,
    EMBED_MAX_CHARS,
    FORCE_REINDEX,
    HF_DATASET_ID,
    HF_SPLIT,
    INDEX_BATCH_SIZE,
    INDEX_LIMIT,
    LOCAL_CSV_PATH,
    OLLAMA_BASE_URL,
    OLLAMA_EMBED_MODEL,
    QDRANT_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_URL,
    SEARCH_FETCH_MAX,
    SEARCH_FETCH_MULTIPLIER,
    VECTOR_DB,
)
from .filters import coerce_date_iso, coerce_float, coerce_int

CSV_FIELDS = [
    "parent_asin",
    "title",
    "description",
    "features",
    "main_category",
    "store",
    "average_rating",
    "rating_number",
    "price",
    "date_first_available",
    "image",
]

SAFE_EMBED_MAX_CHARS = 1000

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "best",
    "by",
    "for",
    "from",
    "good",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "ratings",
    "the",
    "to",
    "under",
    "with",
}


def _db_has_data(path: str) -> bool:
    # Chroma persists files; if directory exists and not empty, assume already indexed.
    return os.path.exists(path) and any(os.scandir(path))


@lru_cache(maxsize=1)
def _get_qdrant_client() -> QdrantClient:
    if QDRANT_API_KEY:
        return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    return QdrantClient(url=QDRANT_URL)


def _qdrant_has_data() -> bool:
    client = _get_qdrant_client()
    try:
        info = client.get_collection(QDRANT_COLLECTION)
    except Exception:
        return False
    return info.points_count > 0


def reset_vector_store() -> Dict[str, Any]:
    get_vector_store.cache_clear()
    _similarity_search_no_filter_cached.cache_clear()
    if VECTOR_DB == "qdrant":
        client = _get_qdrant_client()
        try:
            client.delete_collection(QDRANT_COLLECTION)
        except Exception as exc:
            return {
                "status": "ok",
                "reset": False,
                "vector_db": "qdrant",
                "reason": str(exc),
            }
        return {"status": "ok", "reset": True, "vector_db": "qdrant"}

    if os.path.exists(CHROMA_DIR):
        shutil.rmtree(CHROMA_DIR)
        return {"status": "ok", "reset": True, "vector_db": "chroma"}
    return {"status": "ok", "reset": False, "vector_db": "chroma", "reason": "missing"}


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    embeddings = OllamaEmbeddings(model=OLLAMA_EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    if VECTOR_DB == "qdrant":
        client = _get_qdrant_client()
        return QdrantVectorStore(
            client=client,
            collection_name=QDRANT_COLLECTION,
            embedding=embeddings,
        )
    return Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_DIR,
        embedding_function=embeddings,
    )


def _build_document_from_row(row: Dict[str, Any], fallback_id: str) -> Optional[Document]:
    title = (row.get("title") or "").strip()
    desc = (row.get("description") or "").strip()
    features = row.get("features") or []
    if isinstance(features, list):
        features_text = " ".join([str(x) for x in features if x is not None])
    else:
        features_text = str(features)

    # Main searchable text
    page_content = " ".join([title, desc, features_text]).strip()
    max_chars = min(EMBED_MAX_CHARS, SAFE_EMBED_MAX_CHARS)
    if max_chars > 0 and len(page_content) > max_chars:
        page_content = page_content[:max_chars]

    # Skip empty text rows
    if not page_content:
        return None

    price_val = coerce_float(row.get("price"))
    avg_rating_val = coerce_float(row.get("average_rating"))
    rating_number_val = coerce_int(row.get("rating_number"))
    date_iso = coerce_date_iso(row.get("date_first_available"))

    metadata: Dict[str, Any] = {
        "title": title or None,
        "parent_asin": row.get("parent_asin"),
        "main_category": row.get("main_category"),
        "store": row.get("store"),
        "average_rating": avg_rating_val,
        "rating_number": rating_number_val,
        "price": price_val,
        "date_first_available": date_iso,
        "image": row.get("image"),
    }

    parent_asin = str(row.get("parent_asin") or "row")
    doc_id = f"{parent_asin}-{fallback_id}"

    return Document(
        page_content=page_content,
        metadata=metadata,
        id=doc_id,
    )


def _matches_keyword(row: Dict[str, Any], keyword: str) -> bool:
    if not keyword:
        return True
    haystack = " ".join(
        [
            str(row.get("title") or ""),
            str(row.get("description") or ""),
            " ".join(str(x) for x in (row.get("features") or []) if x is not None)
            if isinstance(row.get("features"), list)
            else str(row.get("features") or ""),
            str(row.get("main_category") or ""),
            str(row.get("store") or ""),
        ]
    ).lower()
    return keyword.lower() in haystack


def _row_for_csv(row: Dict[str, Any]) -> Dict[str, Any]:
    csv_row: Dict[str, Any] = {}
    for field in CSV_FIELDS:
        value = row.get(field)
        if isinstance(value, (list, dict)):
            csv_row[field] = json.dumps(value, ensure_ascii=False)
        elif value is None:
            csv_row[field] = ""
        else:
            csv_row[field] = value
    return csv_row


def _row_from_csv(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    features = out.get("features")
    if features:
        try:
            parsed = json.loads(features)
            out["features"] = parsed
        except json.JSONDecodeError:
            out["features"] = features
    return out


def export_hf_to_csv(
    output_path: Optional[str] = None,
    limit: Optional[int] = None,
    keyword: Optional[str] = None,
) -> Dict[str, Any]:
    path = output_path or LOCAL_CSV_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    ds = load_dataset(HF_DATASET_ID, split=HF_SPLIT)
    max_rows = limit if (limit and limit > 0) else None
    written = 0

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in tqdm(ds, desc="Exporting CSV"):
            if keyword and not _matches_keyword(row, keyword):
                continue
            writer.writerow(_row_for_csv(row))
            written += 1
            if max_rows is not None and written >= max_rows:
                break

    return {
        "status": "ok",
        "path": path,
        "count": written,
        "limit": limit,
        "keyword": keyword,
    }


def _iter_csv_rows(csv_path: str):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"CSV file not found: {csv_path}. Generate it with POST /dataset/export."
        )
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield _row_from_csv(row)


def build_documents(
    limit: int,
    keyword: Optional[str] = None,
    data_source: Optional[str] = None,
    csv_path: Optional[str] = None,
) -> List[Document]:
    docs: List[Document] = []
    source = data_source or DATA_SOURCE
    max_docs = limit if (limit and limit > 0) else None

    if source == "csv":
        rows = _iter_csv_rows(csv_path or LOCAL_CSV_PATH)
        desc = "Building Documents from CSV"
    elif source == "hf":
        rows = load_dataset(HF_DATASET_ID, split=HF_SPLIT)
        desc = "Building Documents from HuggingFace"
    else:
        raise ValueError(f"Unsupported DATA_SOURCE: {source}. Use 'csv' or 'hf'.")

    for i, row in enumerate(tqdm(rows, desc=desc)):
        if keyword and not _matches_keyword(row, keyword):
            continue
        doc = _build_document_from_row(row=row, fallback_id=str(i))
        if doc is None:
            continue
        docs.append(doc)
        if max_docs is not None and len(docs) >= max_docs:
            break

    return docs


def ensure_index(
    limit: Optional[int] = None,
    keyword: Optional[str] = None,
    data_source: Optional[str] = None,
    csv_path: Optional[str] = None,
    batch_size: Optional[int] = None,
    reset: bool = False,
) -> Dict[str, Any]:
    limit = limit if limit is not None else INDEX_LIMIT
    reset_result = reset_vector_store() if reset else None
    vector_store = get_vector_store()

    if keyword:
        should_add = True
    elif VECTOR_DB == "qdrant":
        should_add = FORCE_REINDEX or (not _qdrant_has_data())
    else:
        should_add = FORCE_REINDEX or (not _db_has_data(CHROMA_DIR))
    if not should_add:
        return {"status": "ok", "indexed": False, "reason": "db_exists"}

    docs = build_documents(
        limit=limit,
        keyword=keyword,
        data_source=data_source,
        csv_path=csv_path,
    )
    if not docs:
        return {
            "status": "ok",
            "indexed": False,
            "reason": "no_matching_rows",
            "limit": limit,
            "keyword": keyword,
        }

    batch_size = batch_size or INDEX_BATCH_SIZE
    indexed_count = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        ids = [d.id for d in batch]
        vector_store.add_documents(documents=batch, ids=ids)
        indexed_count += len(batch)

    _similarity_search_no_filter_cached.cache_clear()

    return {
        "status": "ok",
        "indexed": True,
        "count": indexed_count,
        "limit": limit,
        "keyword": keyword,
        "data_source": data_source or DATA_SOURCE,
        "csv_path": csv_path or LOCAL_CSV_PATH,
        "batch_size": batch_size,
        "reset": reset_result,
        "embed_max_chars": min(EMBED_MAX_CHARS, SAFE_EMBED_MAX_CHARS),
    }


def stream_index(
    limit: Optional[int] = None,
    keyword: Optional[str] = None,
    data_source: Optional[str] = None,
    csv_path: Optional[str] = None,
    batch_size: Optional[int] = None,
    reset: bool = False,
):
    limit = limit if limit is not None else INDEX_LIMIT
    batch_size = batch_size or INDEX_BATCH_SIZE
    if reset:
        yield json.dumps({"event": "reset", **reset_vector_store()}) + "\n"
    vector_store = get_vector_store()

    yield json.dumps({"event": "building_documents", "limit": limit}) + "\n"
    docs = build_documents(
        limit=limit,
        keyword=keyword,
        data_source=data_source,
        csv_path=csv_path,
    )

    if not docs:
        yield json.dumps(
            {
                "event": "complete",
                "status": "ok",
                "indexed": False,
                "reason": "no_matching_rows",
                "limit": limit,
                "keyword": keyword,
            }
        ) + "\n"
        return

    yield json.dumps(
        {
            "event": "documents_built",
            "count": len(docs),
            "batch_size": batch_size,
            "data_source": data_source or DATA_SOURCE,
            "csv_path": csv_path or LOCAL_CSV_PATH,
        }
    ) + "\n"

    indexed_count = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        batch_number = (i // batch_size) + 1
        yield json.dumps(
            {
                "event": "indexing_batch",
                "batch": batch_number,
                "from": i + 1,
                "to": i + len(batch),
                "total": len(docs),
            }
        ) + "\n"
        ids = [d.id for d in batch]
        vector_store.add_documents(documents=batch, ids=ids)
        indexed_count += len(batch)
        _similarity_search_no_filter_cached.cache_clear()
        yield json.dumps(
            {
                "event": "batch_indexed",
                "batch": batch_number,
                "indexed": indexed_count,
                "total": len(docs),
            }
        ) + "\n"

    yield json.dumps(
        {
            "event": "complete",
            "status": "ok",
            "indexed": True,
            "count": indexed_count,
            "limit": limit,
            "keyword": keyword,
            "data_source": data_source or DATA_SOURCE,
            "csv_path": csv_path or LOCAL_CSV_PATH,
            "batch_size": batch_size,
            "embed_max_chars": min(EMBED_MAX_CHARS, SAFE_EMBED_MAX_CHARS),
        }
    ) + "\n"


def make_retriever(
    k: int = 5,
    metadata_filter: Optional[Dict[str, Any]] = None,
):
    vector_store = get_vector_store()
    search_kwargs = {"k": k}
    if metadata_filter:
        # Chroma supports simple filters; more complex operators may vary by version.
        search_kwargs["filter"] = metadata_filter

    return vector_store.as_retriever(search_kwargs=search_kwargs)


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    normalized = []
    for token in tokens:
        if len(token) > 3 and token.endswith("s"):
            token = token[:-1]
        normalized.append(token)
    return normalized


def _query_tokens(query: str) -> List[str]:
    tokens = _tokenize(query)
    return [t for t in tokens if len(t) > 1 and t not in _STOPWORDS]


def _doc_overlap_score(query_tokens: List[str], doc: Document) -> float:
    if not query_tokens:
        return 0.0
    md = doc.metadata or {}
    doc_text = " ".join(
        [
            str(md.get("title") or ""),
            str(md.get("main_category") or ""),
            str(md.get("store") or ""),
            str(doc.page_content or ""),
        ]
    )
    doc_tokens = set(_tokenize(doc_text))
    matched = sum(1 for tok in query_tokens if tok in doc_tokens)
    return matched / float(len(query_tokens))


def _rerank_by_lexical_overlap(
    query: str, docs_with_scores: List[Tuple[Document, float]], k: int
) -> List[Tuple[Document, float]]:
    q_tokens = _query_tokens(query)
    if not docs_with_scores:
        return docs_with_scores

    indexed = list(enumerate(docs_with_scores))
    scored = [
        (idx, pair, _doc_overlap_score(q_tokens, pair[0]))
        for idx, pair in indexed
    ]

    # Relevance gate: if we cannot find any lexical evidence, return no results.
    # This prevents obvious semantic drift from vector-only nearest neighbors.
    positive = [item for item in scored if item[2] > 0.0]
    if not positive:
        return []

    reranked = sorted(
        positive,
        key=lambda item: (
            -item[2],
            item[0],  # preserve vector order as tie-breaker
        ),
    )
    return [item[1] for item in reranked[:k]]


def similarity_search(
    query: str,
    k: int = 5,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> List[Tuple[Document, float]]:
    if metadata_filter is None:
        return list(_similarity_search_no_filter_cached(query, k))

    return _similarity_search_uncached(
        query=query,
        k=k,
        metadata_filter=metadata_filter,
    )


@lru_cache(maxsize=128)
def _similarity_search_no_filter_cached(
    query: str,
    k: int,
) -> Tuple[Tuple[Document, float], ...]:
    return tuple(
        _similarity_search_uncached(query=query, k=k, metadata_filter=None)
    )


def _similarity_search_uncached(
    query: str,
    k: int = 5,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> List[Tuple[Document, float]]:
    vector_store: VectorStore = get_vector_store()
    fetch_k = max(k, min(SEARCH_FETCH_MAX, k * SEARCH_FETCH_MULTIPLIER))
    search_kwargs: Dict[str, Any] = {"k": fetch_k}
    if metadata_filter:
        search_kwargs["filter"] = metadata_filter

    # Returns (Document, score)
    docs_with_scores = vector_store.similarity_search_with_score(query, **search_kwargs)
    return _rerank_by_lexical_overlap(query=query, docs_with_scores=docs_with_scores, k=k)


def get_index_stats() -> Dict[str, Any]:
    if VECTOR_DB == "qdrant":
        client = _get_qdrant_client()
        try:
            info = client.get_collection(QDRANT_COLLECTION)
            return {
                "vector_db": "qdrant",
                "collection": QDRANT_COLLECTION,
                "count": info.points_count,
                "url": QDRANT_URL,
            }
        except Exception:
            return {
                "vector_db": "qdrant",
                "collection": QDRANT_COLLECTION,
                "count": None,
                "url": QDRANT_URL,
            }

    count = None
    sqlite_path = os.path.join(CHROMA_DIR, "chroma.sqlite3")
    if os.path.exists(sqlite_path):
        try:
            con = sqlite3.connect(sqlite_path, timeout=1)
            try:
                count = con.execute("select count(*) from embeddings").fetchone()[0]
            finally:
                con.close()
        except Exception:
            count = None

    return {
        "vector_db": "chroma",
        "collection": COLLECTION_NAME,
        "count": count,
        "persist_directory": CHROMA_DIR,
    }
