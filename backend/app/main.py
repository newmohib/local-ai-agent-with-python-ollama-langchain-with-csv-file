from time import perf_counter
from typing import Optional, Dict, Any, List
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .vector_store import ensure_index, export_hf_to_csv, stream_index
from .rag import stream_answer, answer_json
from .filters import build_vector_filter, infer_filter_from_query, merge_filter_objects
from .vector_store import (
    similarity_search,
    get_index_stats,
    rating_sort_direction,
    metadata_sorted_search,
)
from .config import VECTOR_DB


app = FastAPI(title="Amazon Products RAG (Local Ollama + Chroma)")

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


class SearchRequest(BaseModel):
    query: str
    k: int = 5
    filter: Optional[FilterModel] = None


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/status")
def status():
    return get_index_stats()


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


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    explicit_filter = req.filter.dict(by_alias=True) if req.filter else None
    merged_filter = merge_filter_objects(
        explicit_filter,
        infer_filter_from_query(req.question),
    )
    vector_filter = build_vector_filter(VECTOR_DB, merged_filter)
    gen = stream_answer(
        question=req.question,
        k=req.k,
        metadata_filter=vector_filter,
        filter_obj=merged_filter,
    )

    # Plain text streaming
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

    recommendations_out: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    for d, score in results:
        md = d.metadata or {}
        recommendations_out.append(
            {
                "parent_asin": md.get("parent_asin"),
                "title": md.get("title"),
                "main_category": md.get("main_category"),
                "store": md.get("store"),
                "price": md.get("price"),
                "average_rating": md.get("average_rating"),
                "rating_number": md.get("rating_number"),
                "date_first_available": md.get("date_first_available"),
                "image": md.get("image"),
                "score": score,
            }
        )
        citations.append(
            {
                "parent_asin": md.get("parent_asin"),
                "score": score,
                "snippet": (d.page_content or "")[:220],
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

    out: List[Dict[str, Any]] = []
    for d, score in results:
        md = d.metadata or {}
        out.append(
            {
                "parent_asin": md.get("parent_asin"),
                "title": md.get("title"),
                "main_category": md.get("main_category"),
                "store": md.get("store"),
                "price": md.get("price"),
                "average_rating": md.get("average_rating"),
                "rating_number": md.get("rating_number"),
                "date_first_available": md.get("date_first_available"),
                "image": md.get("image"),
                "score": score,
                "snippet": (d.page_content or "")[:220],
            }
        )

    return {
        "query": req.query,
        "results": out,
        "applied_filter": merged_filter,
        "timing_ms": {"retrieval": retrieval_ms},
    }
