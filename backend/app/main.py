from time import perf_counter
from typing import Optional, Dict, Any, List
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .vector_store import ensure_index, export_hf_to_csv, stream_index
from .rag import stream_answer, answer_json, stream_recommendations
from .filters import build_vector_filter, infer_filter_from_query, merge_filter_objects
from .vector_store import (
    similarity_search,
    get_index_stats,
    rating_sort_direction,
    metadata_sorted_search,
    upsert_product_embedding,
    delete_product_embedding,
)
from .config import VECTOR_DB, APP_DB_PATH
from .app_db import (
    init_db,
    upsert_product,
    delete_product,
    get_product,
    list_products,
    import_csv,
    count_products,
    get_products_by_ids,
    iter_products,
)


app = FastAPI(title="Amazon Products RAG (Local Ollama + Chroma)")
init_db()

# CORS for any frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NumberRange(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class IntRange(BaseModel):
    min: Optional[int] = None
    max: Optional[int] = None


class DateRange(BaseModel):
    from_: Optional[str] = Field(default=None, alias="from")
    to: Optional[str] = None

    model_config = {"validate_by_name": True}


class FilterModel(BaseModel):
    main_category: Optional[str] = None
    store: Optional[str] = None
    price: Optional[NumberRange] = None
    average_rating: Optional[NumberRange] = None
    rating_number: Optional[IntRange] = None
    date_first_available: Optional[DateRange] = None


class IndexRequest(BaseModel):
    limit: Optional[int] = None
    keyword: Optional[str] = None
    data_source: Optional[str] = None
    csv_path: Optional[str] = None
    batch_size: Optional[int] = None
    reset: bool = False


class ExportCsvRequest(BaseModel):
    output_path: Optional[str] = None
    limit: Optional[int] = None
    keyword: Optional[str] = None


class ChatRequest(BaseModel):
    question: str
    k: int = 5
    filter: Optional[FilterModel] = None
    fast: bool = False


class ProductModel(BaseModel):
    parent_asin: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    features: Optional[Any] = None
    main_category: Optional[str] = None
    store: Optional[str] = None
    average_rating: Optional[float] = None
    rating_number: Optional[int] = None
    price: Optional[float] = None
    date_first_available: Optional[str] = None
    image: Optional[str] = None


class ProductImportRequest(BaseModel):
    csv_path: str = "./data/amazon_products.csv"
    limit: Optional[int] = None
    keyword: Optional[str] = None
    skip_existing: bool = True
    sync_embeddings: bool = False
    reset_vector: bool = False


class SearchRequest(BaseModel):
    query: str
    k: int = 5
    filter: Optional[FilterModel] = None


def _hydrate_results(results: List[Any]) -> List[Dict[str, Any]]:
    ids: List[str] = []
    for d, _ in results:
        md = d.metadata or {}
        if md.get("parent_asin"):
            ids.append(str(md["parent_asin"]))
    rows = get_products_by_ids(ids)
    by_id = {row["parent_asin"]: row for row in rows}

    hydrated: List[Dict[str, Any]] = []
    for d, score in results:
        md = d.metadata or {}
        row = by_id.get(md.get("parent_asin"))
        hydrated.append(
            {
                "parent_asin": (row or md).get("parent_asin"),
                "title": (row or md).get("title"),
                "main_category": (row or md).get("main_category"),
                "store": (row or md).get("store"),
                "price": (row or md).get("price"),
                "average_rating": (row or md).get("average_rating"),
                "rating_number": (row or md).get("rating_number"),
                "date_first_available": (row or md).get("date_first_available"),
                "image": (row or md).get("image"),
                "score": score,
                "snippet": (d.page_content or "")[:220],
            }
        )
    return hydrated


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/status")
def status():
    out = get_index_stats()
    out["app_db"] = {"path": APP_DB_PATH, "count": count_products()}
    return out


@app.post("/index")
def index(req: IndexRequest):
    keyword = req.keyword.strip() if req.keyword else None
    return ensure_index(
        limit=req.limit,
        keyword=keyword,
        data_source=req.data_source,
        csv_path=req.csv_path,
        batch_size=req.batch_size,
        reset=req.reset,
    )


@app.post("/index/stream")
def index_stream(req: IndexRequest):
    keyword = req.keyword.strip() if req.keyword else None
    gen = stream_index(
        limit=req.limit,
        keyword=keyword,
        data_source=req.data_source,
        csv_path=req.csv_path,
        batch_size=req.batch_size,
        reset=req.reset,
    )
    return StreamingResponse(gen, media_type="application/x-ndjson")


@app.post("/dataset/export")
def export_dataset(req: ExportCsvRequest):
    keyword = req.keyword.strip() if req.keyword else None
    return export_hf_to_csv(
        output_path=req.output_path,
        limit=req.limit,
        keyword=keyword,
    )


@app.post("/products")
def create_product(product: ProductModel):
    if not product.parent_asin:
        return {"status": "error", "error": "parent_asin is required"}
    row = upsert_product(product.dict(exclude_none=True))
    embedding_synced = upsert_product_embedding(row)
    return {"status": "ok", "product": row, "embedding_synced": embedding_synced}


@app.put("/products/{parent_asin}")
def update_product(parent_asin: str, product: ProductModel):
    data = product.dict(exclude_none=True)
    data["parent_asin"] = parent_asin
    row = upsert_product(data)
    embedding_synced = upsert_product_embedding(row)
    return {"status": "ok", "product": row, "embedding_synced": embedding_synced}


@app.delete("/products/{parent_asin}")
def remove_product(parent_asin: str):
    deleted = delete_product(parent_asin)
    embedding_deleted = delete_product_embedding(parent_asin)
    return {"status": "ok", "deleted": deleted, "embedding_deleted": embedding_deleted}


@app.get("/products/{parent_asin}")
def read_product(parent_asin: str):
    row = get_product(parent_asin)
    if not row:
        return {"status": "not_found", "parent_asin": parent_asin}
    return {"status": "ok", "product": row}


@app.get("/products")
def read_products(limit: int = 50, offset: int = 0):
    rows = list_products(limit=limit, offset=offset)
    return {"status": "ok", "count": len(rows), "products": rows}


@app.post("/products/import")
def import_products(req: ProductImportRequest):
    inserted = import_csv(
        req.csv_path,
        limit=req.limit,
        keyword=req.keyword,
        skip_existing=req.skip_existing,
    )
    sync_result = None
    if req.sync_embeddings:
        if req.reset_vector:
            sync_result = ensure_index(
                limit=count_products(),
                keyword=req.keyword,
                data_source="app_db",
                reset=True,
            )
        else:
            synced = 0
            for row in iter_products(limit=req.limit, keyword=req.keyword):
                if upsert_product_embedding(row):
                    synced += 1
            sync_result = {"status": "ok", "synced": synced}
    return {
        "status": "ok",
        "inserted": inserted,
        "sync_embeddings": req.sync_embeddings,
        "sync_result": sync_result,
    }


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    explicit_filter = req.filter.dict(by_alias=True) if req.filter else None
    merged_filter = merge_filter_objects(
        explicit_filter,
        infer_filter_from_query(req.question),
    )
    vector_filter = build_vector_filter(VECTOR_DB, merged_filter)
    if req.fast:
        gen = stream_recommendations(
            question=req.question,
            k=req.k,
            metadata_filter=vector_filter,
            filter_obj=merged_filter,
            sse=True,
        )
        return StreamingResponse(
            gen,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    gen = stream_answer(
        question=req.question,
        k=req.k,
        metadata_filter=vector_filter,
        filter_obj=merged_filter,
    )
    return StreamingResponse(gen, media_type="text/plain")


@app.post("/chat")
def chat(req: ChatRequest):
    explicit_filter = req.filter.dict(by_alias=True) if req.filter else None
    merged_filter = merge_filter_objects(
        explicit_filter,
        infer_filter_from_query(req.question),
    )
    vector_filter = build_vector_filter(VECTOR_DB, merged_filter)
    return answer_json(
        question=req.question,
        k=req.k,
        metadata_filter=vector_filter,
        filter_obj=merged_filter,
    )


@app.post("/recommendations")
def recommendations(req: ChatRequest):
    explicit_filter = req.filter.dict(by_alias=True) if req.filter else None
    merged_filter = merge_filter_objects(
        explicit_filter,
        infer_filter_from_query(req.question),
    )
    vector_filter = build_vector_filter(VECTOR_DB, merged_filter)
    started = perf_counter()
    sort_direction = rating_sort_direction(req.question)
    if sort_direction or (merged_filter or {}).get("price_sort"):
        results = metadata_sorted_search(
            req.question,
            k=req.k,
            filter_obj=merged_filter,
        )
    else:
        results = similarity_search(
            req.question,
            k=req.k,
            metadata_filter=vector_filter,
            filter_obj=merged_filter,
        )
    retrieval_ms = round((perf_counter() - started) * 1000, 2)

    hydrated = _hydrate_results(results)
    recommendations_out: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    for item in hydrated:
        recommendations_out.append(
            {
                "parent_asin": item.get("parent_asin"),
                "title": item.get("title"),
                "main_category": item.get("main_category"),
                "store": item.get("store"),
                "price": item.get("price"),
                "average_rating": item.get("average_rating"),
                "rating_number": item.get("rating_number"),
                "date_first_available": item.get("date_first_available"),
                "image": item.get("image"),
                "score": item.get("score"),
            }
        )
        citations.append(
            {
                "parent_asin": item.get("parent_asin"),
                "score": item.get("score"),
                "snippet": item.get("snippet"),
            }
        )

    return {
        "question": req.question,
        "answer": "Retrieved matching products without LLM generation.",
        "recommendations": recommendations_out,
        "citations": citations,
        "applied_filter": merged_filter,
        "timing_ms": {"retrieval": retrieval_ms},
    }


@app.post("/recommendations/stream")
def recommendations_stream(req: ChatRequest):
    explicit_filter = req.filter.dict(by_alias=True) if req.filter else None
    merged_filter = merge_filter_objects(
        explicit_filter,
        infer_filter_from_query(req.question),
    )
    vector_filter = build_vector_filter(VECTOR_DB, merged_filter)
    gen = stream_recommendations(
        question=req.question,
        k=req.k,
        metadata_filter=vector_filter,
        filter_obj=merged_filter,
    )
    return StreamingResponse(gen, media_type="application/x-ndjson")


@app.post("/search")
def search(req: SearchRequest):
    explicit_filter = req.filter.dict(by_alias=True) if req.filter else None
    merged_filter = merge_filter_objects(
        explicit_filter,
        infer_filter_from_query(req.query),
    )
    vector_filter = build_vector_filter(VECTOR_DB, merged_filter)
    started = perf_counter()
    sort_direction = rating_sort_direction(req.query)
    if sort_direction or (merged_filter or {}).get("price_sort"):
        results = metadata_sorted_search(
            req.query,
            k=req.k,
            filter_obj=merged_filter,
        )
    else:
        results = similarity_search(
            req.query,
            k=req.k,
            metadata_filter=vector_filter,
            filter_obj=merged_filter,
        )
    retrieval_ms = round((perf_counter() - started) * 1000, 2)

    out = _hydrate_results(results)

    return {
        "query": req.query,
        "results": out,
        "applied_filter": merged_filter,
        "timing_ms": {"retrieval": retrieval_ms},
    }
