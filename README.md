codex resume 019c855e-6ebf-7602-8546-109a32c7aab1
# Amazon Products RAG (Local Ollama + Chroma)

Starter project for a local RAG app over the HuggingFace Amazon products dataset.

## Requirements

- Python 3.10+
- Node 18+
- Ollama running locally
- Optional: Qdrant (if `VECTOR_DB=qdrant`)

## Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Start the API:

```bash
uvicorn app.main:app --reload --port ${PORT:-9000}
```

Or run the helper script:

```bash
cd backend
./run.sh
```

## Pull Ollama models

```bash
ollama pull llama3.2
ollama pull mxbai-embed-large
```

## Optional: Qdrant setup

If you want to use Qdrant instead of Chroma:

1. Start Qdrant (example using Docker).

```bash
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

2. In `.env`, set:

```bash
VECTOR_DB=qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=amazon_products
```

## Index dataset (first run)

```bash
curl -X POST http://localhost:9000/index \
  -H "Content-Type: application/json" \
  -d '{"limit": 5000}'
```

For a quicker test:

```bash
curl -X POST http://localhost:9000/index \
  -H "Content-Type: application/json" \
  -d '{"limit": 1000}'
```

Index only earbuds-related products from HuggingFace:

```bash
curl -X POST http://localhost:9000/index \
  -H "Content-Type: application/json" \
  -d '{"limit": 500, "keyword": "earbuds"}'
```

## Streaming chat

```bash
curl -N -X POST http://localhost:9000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "wireless earbuds under $50 with good ratings", "k": 5}'
```

## JSON chat (structured + citations)

```bash
curl -X POST http://localhost:9000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "wireless earbuds under $50 with good ratings", "k": 5}'
```

## Quick query examples

```bash
# Basic search
curl -X POST http://localhost:9000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "wireless earbuds", "k": 5}'
```

```bash
# Chat with category + price + rating filters
curl -X POST http://localhost:9000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "best budget headphones for commuting",
    "k": 5,
    "filter": {
      "main_category": "Electronics",
      "price": {"max": 60},
      "average_rating": {"min": 4.2},
      "rating_number": {"min": 200}
    }
  }'
```

```bash
# Search with date range
curl -X POST http://localhost:9000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "kitchen knife set",
    "k": 5,
    "filter": {
      "date_first_available": {"from": "2021-01-01", "to": "2024-12-31"}
    }
  }'
```

With simple filters:

```bash
curl -N -X POST http://localhost:9000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "wireless earbuds under $50", "k": 5, "filter": {"main_category": "Electronics"}}'
```

With numeric/date range filters:

```bash
curl -X POST http://localhost:9000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "wireless earbuds under $50 with good ratings",
    "k": 5,
    "filter": {
      "main_category": "Electronics",
      "price": {"min": 10, "max": 50},
      "average_rating": {"min": 4.0},
      "rating_number": {"min": 200},
      "date_first_available": {"from": "2022-01-01", "to": "2024-12-31"}
    }
  }'
```

## Search (top-k + scores)

```bash
curl -X POST http://localhost:9000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "wireless earbuds",
    "k": 5,
    "filter": {"main_category": "Electronics"}
  }'
```

## Frontend setup

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

The frontend uses `VITE_API_BASE` (default `http://localhost:9000` if not set).

```bash
VITE_API_BASE=http://localhost:9000
```

Open `http://localhost:5173`.

Or run the helper script:

```bash
cd frontend
./run.sh
```

## Endpoints

- `GET /health`
- `GET /status`
- `POST /index`
- `POST /chat/stream`
- `POST /chat`
- `POST /search`

## Notes

- First indexing will take time because embeddings are generated locally.
- Filters support equality and numeric/date ranges for `price`, `average_rating`, `rating_number`, and `date_first_available`.
- If you indexed before these filter changes, delete the Chroma directory or set `FORCE_REINDEX=true` to rebuild with numeric/date metadata.
- If Ollama returns `input length exceeds the context length`, reduce `EMBED_MAX_CHARS` in `backend/.env` (default `3500`) and reindex.
