from time import perf_counter
from typing import Optional, Dict, Any, List
import re
from fastapi import FastAPI, Body
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
from .user_db import (
    init_user_db,
    upsert_user,
    delete_user,
    get_user,
    list_users,
    search_users,
    search_by_mobile_suffix,
    search_by_mobile_suffixes,
    search_by_age_range,
    search_by_numeric_range,
    search_by_date_range,
    import_users_csv,
)
from .user_vector_store import (
    upsert_user_embedding,
    delete_user_embedding,
    search_user_embeddings,
)


app = FastAPI(title="Amazon Products RAG (Local Ollama + Chroma)")
init_db()
init_user_db()

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


class UserModel(BaseModel):
    id: Optional[str] = None
    comcode: Optional[str] = None
    policynum: Optional[str] = None
    agency: Optional[str] = None
    ridernum: Optional[str] = None
    plancode: Optional[str] = None
    comkey: Optional[str] = None
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    full_name: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    poltype: Optional[str] = None
    crole: Optional[str] = None
    age: Optional[str] = None
    issue_date: Optional[str] = None
    addr1: Optional[str] = None
    addr2: Optional[str] = None
    city: Optional[str] = None
    mobile: Optional[str] = None
    father_name: Optional[str] = None
    clttype: Optional[str] = None
    ben_seq_no: Optional[str] = None
    remarks: Optional[str] = None
    rrn: Optional[str] = None
    nid: Optional[str] = None
    clntid: Optional[str] = None


class UserImportRequest(BaseModel):
    csv_path: str = "./data/user_data.csv"
    limit: Optional[int] = None
    skip_existing: bool = True


class UserIndexRequest(BaseModel):
    limit: Optional[int] = None


class UserSemanticSearchRequest(BaseModel):
    query: str
    k: int = 5


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


@app.get("/users")
def read_users(
    limit: int = 50,
    offset: int = 0,
    id: Optional[str] = None,
    comcode: Optional[str] = None,
    policynum: Optional[str] = None,
    agency: Optional[str] = None,
    ridernum: Optional[str] = None,
    plancode: Optional[str] = None,
    comkey: Optional[str] = None,
    last_name: Optional[str] = None,
    first_name: Optional[str] = None,
    full_name: Optional[str] = None,
    dob: Optional[str] = None,
    gender: Optional[str] = None,
    poltype: Optional[str] = None,
    crole: Optional[str] = None,
    age: Optional[str] = None,
    issue_date: Optional[str] = None,
    addr1: Optional[str] = None,
    addr2: Optional[str] = None,
    city: Optional[str] = None,
    mobile: Optional[str] = None,
    father_name: Optional[str] = None,
    clttype: Optional[str] = None,
    ben_seq_no: Optional[str] = None,
    remarks: Optional[str] = None,
    rrn: Optional[str] = None,
    nid: Optional[str] = None,
    clntid: Optional[str] = None,
):
    filters = {
        "id": id,
        "comcode": comcode,
        "policynum": policynum,
        "agency": agency,
        "ridernum": ridernum,
        "plancode": plancode,
        "comkey": comkey,
        "last_name": last_name,
        "first_name": first_name,
        "full_name": full_name,
        "dob": dob,
        "gender": gender,
        "poltype": poltype,
        "crole": crole,
        "age": age,
        "issue_date": issue_date,
        "addr1": addr1,
        "addr2": addr2,
        "city": city,
        "mobile": mobile,
        "father_name": father_name,
        "clttype": clttype,
        "ben_seq_no": ben_seq_no,
        "remarks": remarks,
        "rrn": rrn,
        "nid": nid,
        "clntid": clntid,
    }
    rows = list_users(limit=limit, offset=offset, filters=filters)
    return {"status": "ok", "count": len(rows), "users": rows}


@app.get("/users/{user_id}")
def read_user(user_id: str):
    row = get_user(user_id)
    if not row:
        return {"status": "not_found", "id": user_id}
    return {"status": "ok", "user": row}


@app.post("/users")
def create_user(user: UserModel):
    if not user.id:
        return {"status": "error", "error": "id is required"}
    row = upsert_user(user.dict(exclude_none=True))
    return {"status": "ok", "user": row}


@app.put("/users/{user_id}")
def update_user(user_id: str, user: UserModel):
    data = user.dict(exclude_none=True)
    data["id"] = user_id
    row = upsert_user(data)
    return {"status": "ok", "user": row}


@app.post("/users/{user_id}/sync")
def sync_user_embedding(user_id: str):
    row = get_user(user_id)
    if not row:
        return {"status": "not_found", "id": user_id}
    synced = upsert_user_embedding(row)
    return {"status": "ok", "id": user_id, "embedding_synced": synced}


@app.delete("/users/{user_id}")
def remove_user(user_id: str):
    deleted = delete_user(user_id)
    embedding_deleted = delete_user_embedding(user_id)
    return {
        "status": "ok",
        "deleted": deleted,
        "embedding_deleted": embedding_deleted,
    }


@app.post("/users/import")
def import_users(req: UserImportRequest):
    out = import_users_csv(
        req.csv_path, limit=req.limit, skip_existing=req.skip_existing
    )
    return {"status": "ok", **out}


@app.post("/users/search")
def search_users_endpoint(query: str, limit: int = 50, offset: int = 0):
    rows = search_users(query=query, limit=limit, offset=offset)
    return {"status": "ok", "count": len(rows), "users": rows}


@app.post("/users/index")
def index_users(req: UserIndexRequest):
    rows = list_users(limit=req.limit or 10000, offset=0, filters={})
    synced = 0
    for row in rows:
        if upsert_user_embedding(row):
            synced += 1
    return {"status": "ok", "synced": synced}


@app.post("/users/search/semantic")
@app.get("/users/search/semantic")
def semantic_search_users(
    query: str = "",
    k: int = 5,
    req: Optional[UserSemanticSearchRequest] = Body(None),
):
    if req:
        query = req.query or query
        k = req.k or k
    q = (query or "").lower()
    numbers = re.findall(r"\d+", q)
    if "user id" in q or ("user" in q and "id" in q):
        if numbers:
            rows = search_by_numeric_range(
                "id", int(numbers[0]), int(numbers[0]), limit=k, offset=0
            )
            return {"status": "ok", "query": query, "results": rows, "matched": "user_id"}
    if "father id" in q or ("father" in q and "id" in q):
        if numbers:
            rows = search_by_numeric_range(
                "id", int(numbers[0]), int(numbers[0]), limit=k, offset=0
            )
            return {
                "status": "ok",
                "query": query,
                "results": rows,
                "matched": "father_id",
            }
    wants_suffix = ("last" in q and "digit" in q) or ("ends with" in q) or ("ending" in q)
    if wants_suffix and numbers:
        rows = search_by_mobile_suffixes(numbers, limit=k)
        return {
            "status": "ok",
            "query": query,
            "results": rows,
            "matched": "mobile_suffix",
        }
    if "date" in q or "dob" in q or "issue" in q:
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", q)
        start_date = dates[0] if len(dates) > 0 else None
        end_date = dates[1] if len(dates) > 1 else None
        field = "dob" if "dob" in q else "issue_date"
        if dates:
            rows = search_by_date_range(field, start_date, end_date, limit=k, offset=0)
            return {"status": "ok", "query": query, "results": rows, "matched": "date_range"}
    if "age" in q:
        min_match = re.search(r"(?:min|minimum|at least|over|above)\s*(\d+)", q)
        max_match = re.search(r"(?:max|maximum|under|below|less than)\s*(\d+)", q)
        min_age = int(min_match.group(1)) if min_match else None
        max_age = int(max_match.group(1)) if max_match else None
        if min_age is None and max_age is None and numbers:
            if len(numbers) >= 2:
                min_age = int(numbers[0])
                max_age = int(numbers[1])
            elif len(numbers) == 1:
                min_age = int(numbers[0])
        rows = search_by_age_range(min_age=min_age, max_age=max_age, limit=k, offset=0)
        return {"status": "ok", "query": query, "results": rows, "matched": "age_range"}
    if "nid" in q or "clntid" in q or "policy" in q or "policynum" in q:
        field = "nid"
        if "clntid" in q:
            field = "clntid"
        elif "policy" in q or "policynum" in q:
            field = "policynum"
        min_match = re.search(r"(?:min|minimum|at least|over|above)\s*(\d+)", q)
        max_match = re.search(r"(?:max|maximum|under|below|less than)\s*(\d+)", q)
        min_val = int(min_match.group(1)) if min_match else None
        max_val = int(max_match.group(1)) if max_match else None
        if min_val is not None or max_val is not None:
            rows = search_by_numeric_range(field, min_val, max_val, limit=k, offset=0)
            return {"status": "ok", "query": query, "results": rows, "matched": "numeric_range"}
        if numbers:
            # partial match on numeric fields (e.g., NID contains 533)
            rows = search_users(query=numbers[0], limit=k, offset=0)
            return {"status": "ok", "query": query, "results": rows, "matched": "numeric_partial"}
    # If query looks like a direct field/value search, use SQL LIKE across all columns.
    if numbers or any(
        key in q
        for key in [
            "address",
            "addr",
            "city",
            "mobile",
            "phone",
            "nid",
            "policy",
            "id",
            "dob",
            "date",
            "gender",
            "father",
        ]
    ):
        rows = search_users(query=query, limit=k, offset=0)
        return {"status": "ok", "query": query, "results": rows, "matched": "sql"}
    results = search_user_embeddings(query=query, k=k)
    out = []
    for doc, score in results:
        md = doc.metadata or {}
        out.append(
            {
                "id": md.get("id"),
                "full_name": md.get("full_name"),
                "first_name": md.get("first_name"),
                "last_name": md.get("last_name"),
                "city": md.get("city"),
                "mobile": md.get("mobile"),
                "score": score,
            }
        )
    return {"status": "ok", "query": query, "results": out}


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


@app.post("/products/{parent_asin}/sync")
def sync_product_embedding(parent_asin: str):
    row = get_product(parent_asin)
    if not row:
        return {"status": "not_found", "parent_asin": parent_asin}
    embedding_synced = upsert_product_embedding(row)
    return {"status": "ok", "parent_asin": parent_asin, "embedding_synced": embedding_synced}


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
def read_products(
    limit: int = 50,
    offset: int = 0,
    parent_asin: Optional[str] = None,
    title: Optional[str] = None,
    store: Optional[str] = None,
    main_category: Optional[str] = None,
):
    rows = list_products(
        limit=limit,
        offset=offset,
        parent_asin=parent_asin,
        title=title,
        store=store,
        main_category=main_category,
    )
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
