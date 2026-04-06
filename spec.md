Below is a **complete starter project** (same style as your pizza app, but for the HuggingFace Amazon products dataset), using:

✅ **Fully local embeddings** (Ollama)
✅ **Chroma** as vector DB (persisted on disk)
✅ **FastAPI REST API** (with **streaming** chat response)
✅ **React frontend** (streams the answer in UI)

---

## Project structure

```txt
amazon-rag/
  backend/
    app/
      __init__.py
      config.py
      vector_store.py
      rag.py
      main.py
    requirements.txt
    .env.example
  frontend/
    index.html
    package.json
    vite.config.js
    src/
      main.jsx
      App.jsx
      api.js
```

---

# ✅ Backend (FastAPI + LangChain + Ollama + Chroma)

## `backend/requirements.txt`

```txt
fastapi
uvicorn[standard]
pydantic
python-dotenv

langchain
langchain-core
langchain-ollama
langchain-chroma

datasets
tqdm
```

> Note: `datasets` downloads from HuggingFace. If you want fully offline later, you can cache it locally.

---

## `backend/.env.example`

```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=llama3.2
OLLAMA_EMBED_MODEL=mxbai-embed-large

CHROMA_DIR=./chroma_amazon_db
COLLECTION_NAME=amazon_products

# Indexing
HF_DATASET_ID=milistu/AMAZON-Products-2023
HF_SPLIT=train
INDEX_LIMIT=5000
FORCE_REINDEX=false
```

---

## `backend/app/config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3.2")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "mxbai-embed-large")

CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_amazon_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "amazon_products")

HF_DATASET_ID = os.getenv("HF_DATASET_ID", "milistu/AMAZON-Products-2023")
HF_SPLIT = os.getenv("HF_SPLIT", "train")
INDEX_LIMIT = int(os.getenv("INDEX_LIMIT", "5000"))

FORCE_REINDEX = os.getenv("FORCE_REINDEX", "false").lower() == "true"
```

---

## `backend/app/vector_store.py`

```python
import os
from typing import Optional, Dict, Any, List

from datasets import load_dataset
from tqdm import tqdm

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

from .config import (
    OLLAMA_EMBED_MODEL,
    OLLAMA_BASE_URL,
    CHROMA_DIR,
    COLLECTION_NAME,
    HF_DATASET_ID,
    HF_SPLIT,
    INDEX_LIMIT,
    FORCE_REINDEX,
)


def _db_has_data(path: str) -> bool:
    # Chroma persists files; if directory exists and not empty, assume already indexed.
    return os.path.exists(path) and any(os.scandir(path))


def get_vector_store() -> Chroma:
    embeddings = OllamaEmbeddings(model=OLLAMA_EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    return Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_DIR,
        embedding_function=embeddings,
    )


def build_documents(limit: int) -> List[Document]:
    ds = load_dataset(HF_DATASET_ID, split=HF_SPLIT)

    if limit and limit > 0:
        ds = ds.select(range(min(limit, len(ds))))

    docs: List[Document] = []
    for i, row in enumerate(tqdm(ds, desc="Building Documents")):
        title = (row.get("title") or "").strip()
        desc = (row.get("description") or "").strip()
        features = row.get("features") or []
        if isinstance(features, list):
            features_text = " ".join([str(x) for x in features if x is not None])
        else:
            features_text = str(features)

        # Main searchable text
        page_content = " ".join([title, desc, features_text]).strip()

        # Skip empty text rows
        if not page_content:
            continue

        metadata: Dict[str, Any] = {
            "parent_asin": row.get("parent_asin"),
            "main_category": row.get("main_category"),
            "store": row.get("store"),
            "average_rating": row.get("average_rating"),
            "rating_number": row.get("rating_number"),
            "price": row.get("price"),
            "date_first_available": row.get("date_first_available"),
            "image": row.get("image"),
        }

        docs.append(
            Document(
                page_content=page_content,
                metadata=metadata,
                id=str(row.get("parent_asin") or i),
            )
        )

    return docs


def ensure_index(limit: Optional[int] = None) -> Dict[str, Any]:
    limit = limit if limit is not None else INDEX_LIMIT
    vector_store = get_vector_store()

    should_add = FORCE_REINDEX or (not _db_has_data(CHROMA_DIR))
    if not should_add:
        return {"status": "ok", "indexed": False, "reason": "db_exists"}

    docs = build_documents(limit=limit)

    # Chroma add_documents uses embeddings internally (Ollama) => may take time.
    ids = [d.id for d in docs]
    vector_store.add_documents(documents=docs, ids=ids)

    return {"status": "ok", "indexed": True, "count": len(docs), "limit": limit}


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
```

---

## `backend/app/rag.py` (RAG prompt + streaming generator)

```python
from typing import Dict, Any, List, Optional, Generator

from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate

from .config import OLLAMA_LLM_MODEL, OLLAMA_BASE_URL
from .vector_store import make_retriever


SYSTEM_TEMPLATE = """
You are an expert shopping assistant.

Rules:
- Use ONLY the provided product context.
- If you cannot answer from the context, say: "I don't know from the provided products."
- Prefer concise, helpful answers.
- When recommending items, include: title (if present), category, price (if available), rating (if available), and parent_asin.

Product context:
{context}

User question:
{question}

Answer:
""".strip()


def _format_docs(docs) -> str:
    lines: List[str] = []
    for d in docs:
        md = d.metadata or {}
        lines.append(
            f"- ASIN: {md.get('parent_asin')} | "
            f"Category: {md.get('main_category')} | "
            f"Price: {md.get('price')} | "
            f"Rating: {md.get('average_rating')} ({md.get('rating_number')})\n"
            f"  Text: {d.page_content}"
        )
    return "\n\n".join(lines)


def stream_answer(
    question: str,
    k: int = 5,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> Generator[str, None, None]:
    retriever = make_retriever(k=k, metadata_filter=metadata_filter)
    docs = retriever.invoke(question)
    context = _format_docs(docs)

    prompt = ChatPromptTemplate.from_template(SYSTEM_TEMPLATE)
    llm = OllamaLLM(model=OLLAMA_LLM_MODEL, base_url=OLLAMA_BASE_URL)

    chain = prompt | llm

    # Stream chunks
    for chunk in chain.stream({"context": context, "question": question}):
        # chunk is usually str
        yield chunk
```

---

## `backend/app/main.py` (FastAPI endpoints + streaming)

```python
from typing import Optional, Dict, Any
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .vector_store import ensure_index
from .rag import stream_answer


app = FastAPI(title="Amazon Products RAG (Local Ollama + Chroma)")


class IndexRequest(BaseModel):
    limit: Optional[int] = None


class ChatRequest(BaseModel):
    question: str
    k: int = 5
    # Simple filter examples:
    # {"main_category": "Electronics"}
    # {"store": "Some Store"}
    # For numeric filters, Chroma filter support depends on version.
    filter: Optional[Dict[str, Any]] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/index")
def index(req: IndexRequest):
    return ensure_index(limit=req.limit)


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    gen = stream_answer(question=req.question, k=req.k, metadata_filter=req.filter)

    # Plain text streaming
    return StreamingResponse(gen, media_type="text/plain")
```

---

## Run backend

### 1) Start Ollama (and pull models)

```bash
ollama pull llama3.2
ollama pull mxbai-embed-large
```

### 2) Setup backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### 3) Index dataset (first time)

```bash
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -d '{"limit": 5000}'
```

---

# ✅ Frontend (React + Streaming UI)

## `frontend/package.json`

```json
{
  "name": "amazon-rag-frontend",
  "private": true,
  "version": "0.0.1",
  "type": "module",
  "scripts": {
    "dev": "vite --port 5173",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.4.0"
  }
}
```

## `frontend/vite.config.js`

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
});
```

## `frontend/src/api.js`

```js
const API_BASE = "http://localhost:8000";

export async function indexDataset(limit = 5000) {
  const res = await fetch(`${API_BASE}/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ limit }),
  });
  if (!res.ok) throw new Error("Index failed");
  return res.json();
}

export async function streamChat({ question, k = 5, filter = null }, onChunk) {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, k, filter }),
  });
  if (!res.ok) throw new Error("Chat failed");

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const text = decoder.decode(value, { stream: true });
    onChunk(text);
  }
}
```

## `frontend/src/App.jsx`

```jsx
import React, { useState } from "react";
import { indexDataset, streamChat } from "./api";

export default function App() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);

  // simple filters
  const [category, setCategory] = useState("");
  const [store, setStore] = useState("");
  const [k, setK] = useState(5);

  async function handleIndex() {
    setLoading(true);
    setAnswer("");
    try {
      const out = await indexDataset(5000);
      setAnswer(`Index result: ${JSON.stringify(out, null, 2)}`);
    } catch (e) {
      setAnswer(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleAsk() {
    setLoading(true);
    setAnswer("");

    const filter = {};
    if (category.trim()) filter.main_category = category.trim();
    if (store.trim()) filter.store = store.trim();
    const finalFilter = Object.keys(filter).length ? filter : null;

    try {
      await streamChat(
        { question, k: Number(k), filter: finalFilter },
        (chunk) => setAnswer((prev) => prev + chunk)
      );
    } catch (e) {
      setAnswer(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "24px auto", fontFamily: "system-ui" }}>
      <h2>Amazon Products RAG (Local Ollama + Chroma)</h2>

      <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
        <button onClick={handleIndex} disabled={loading}>
          {loading ? "Working..." : "Index Dataset (limit 5000)"}
        </button>
      </div>

      <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
        <input
          style={{ flex: 1, padding: 10 }}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder='Ask: "wireless earbuds under $50 with good ratings"'
        />
        <button onClick={handleAsk} disabled={loading || !question.trim()}>
          {loading ? "Thinking..." : "Ask"}
        </button>
      </div>

      <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
        <input
          style={{ padding: 10, width: 220 }}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="Filter: main_category (optional)"
        />
        <input
          style={{ padding: 10, width: 220 }}
          value={store}
          onChange={(e) => setStore(e.target.value)}
          placeholder="Filter: store (optional)"
        />
        <input
          style={{ padding: 10, width: 80 }}
          type="number"
          min={1}
          max={20}
          value={k}
          onChange={(e) => setK(e.target.value)}
          title="Top K retrieved products"
        />
      </div>

      <pre
        style={{
          whiteSpace: "pre-wrap",
          background: "#111",
          color: "#eee",
          padding: 16,
          borderRadius: 10,
          minHeight: 220,
        }}
      >
        {answer || "Answer will stream here..."}
      </pre>
    </div>
  );
}
```

## `frontend/src/main.jsx`

```jsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(<App />);
```

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

Open: `http://localhost:5173`

---

# Notes (important)

### 1) First indexing will take time

Because you’re generating embeddings locally for thousands of products.

Start with `limit=1000` for testing:

```bash
curl -X POST http://localhost:8000/index -H "Content-Type: application/json" -d '{"limit": 1000}'
```

### 2) Filtering

In this starter, filters are **simple equality** (category/store). Numeric filters like `price <= 50` depend on Chroma filter support + your data types. If you want, I’ll upgrade filters properly (price/rating/date ranges).

---

* ✅ `/search` endpoint returning **top-k products with metadata + similarity scores**
* ✅ Proper numeric/range filters (price/rating/date)
* ✅ Return structured JSON recommendations + citations
* ✅ Use Qdrant for faster production-scale search (optional)

also add README.md file for details with curl
