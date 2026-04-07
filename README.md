<!-- codex resume 019c855e-6ebf-7602-8546-109a32c7aab1 -->
<!-- and for sync create a button for and also insert all data from csv file to app_db -->
<!-- 1. Background sync worker (queue-based) for large imports. -->
<!--  If you want a progress bar for import/sync, I can wire it to the streaming /index/stream endpoint and show live progress. -->
# Amazon Products RAG Search

Local RAG product-search app using:

- FastAPI backend on `PORT=9000`
- React/Vite frontend on `http://localhost:5173`
- Ollama for local embeddings and optional chat generation
- Chroma vector DB by default, with optional Qdrant support
- Local CSV as the recommended product data source

## How The Data Flow Works

The app does **not** search the CSV file directly for normal queries.

The normal flow is:

1. Export products from HuggingFace into a local CSV file.
2. Import the CSV into the **App DB (SQLite)**.
3. Sync embeddings from the App DB into the vector DB.
4. Query `/search` or `/recommendations`; the backend searches the vector DB and returns rows from the App DB.

Why this matters:

- The CSV is your source data file.
- The App DB (SQLite) is the system of record for inserts/updates/deletes.
- Chroma/Qdrant is the searchable RAG database synced from the App DB.
- Ollama creates embeddings during indexing and also embeds each user query during search.
- If you update the CSV, re-run indexing with `reset: true` to refresh the vector DB.

## Requirements

- Python 3.10+
- Node 18+
- Ollama running locally
- Optional: Qdrant if `VECTOR_DB=qdrant`

## Ollama Models

Pull the embedding model and LLM model:

```bash
ollama pull mxbai-embed-large
ollama pull llama3.2
```

Model usage:

- `OLLAMA_EMBED_MODEL=mxbai-embed-large` is used for product/query embeddings.
- `OLLAMA_LLM_MODEL=llama3.2` is used only by `/chat` and `/chat/stream`.
- `/search` and `/recommendations` are faster because they do retrieval without LLM generation.

## Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Important backend `.env` defaults:

```bash
PORT=9000
VECTOR_DB=chroma
CHROMA_DIR=./chroma_amazon_db
COLLECTION_NAME=amazon_products
DATA_SOURCE=app_db
LOCAL_CSV_PATH=./data/amazon_products.csv
APP_DB_PATH=./app_db.sqlite3
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=mxbai-embed-large
OLLAMA_LLM_MODEL=llama3.2
EMBED_MAX_CHARS=1000
```

Start backend:

```bash
cd backend
./run.sh
```

Or manually:

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port ${PORT:-9000}
```

Health check:

```bash
curl http://localhost:9000/health
```

## Vector DB

Default vector DB is Chroma:

```bash
VECTOR_DB=chroma
CHROMA_DIR=./chroma_amazon_db
COLLECTION_NAME=amazon_products
```

Chroma stores the local vector index under `backend/chroma_amazon_db` when the backend runs from the `backend` directory.

To use Qdrant instead:

```bash
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

Then set in `backend/.env`:

```bash
VECTOR_DB=qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=amazon_products
```

## Create Local CSV From HuggingFace

Recommended API method:

```bash
curl -X POST http://localhost:9000/dataset/export \
  -H "Content-Type: application/json" \
  -d '{"limit": 500, "keyword": "earbuds", "output_path": "./data/amazon_products.csv"}'
```

Alternative script method:

```bash
cd backend
source venv/bin/activate
python scripts/export_hf_to_csv.py --limit 500 --keyword earbuds --output ./data/amazon_products.csv
```

Generated file:

```txt
backend/data/amazon_products.csv
```

`backend/data/` is ignored by Git.

## Import CSV Into App DB

Import CSV rows into the SQLite App DB:

```bash
curl -X POST http://localhost:9000/products/import \
  -H "Content-Type: application/json" \
  -d '{\"csv_path\": \"./data/amazon_products.csv\", \"limit\": 500, \"keyword\": \"earbuds\"}'
```

Check App DB count:

```bash
curl http://localhost:9000/status
```

## Sync App DB -> Vector DB (RAG)

Use the streaming endpoint so you can see progress:

```bash
curl -N -X POST http://localhost:9000/index/stream \
  -H "Content-Type: application/json" \
  -d '{"limit": 500, "keyword": "earbuds", "data_source": "app_db", "batch_size": 10, "reset": true}'
```

Non-streaming version:

```bash
curl -X POST http://localhost:9000/index \
  -H "Content-Type: application/json" \
  -d '{"limit": 500, "keyword": "earbuds", "data_source": "app_db", "batch_size": 10, "reset": true}'
```

Notes:

- `data_source: "app_db"` tells backend to read rows from the SQLite App DB.
- `reset: true` clears the old vector index before indexing the App DB.
- `batch_size: 10` avoids very large embedding requests to Ollama.

Check vector DB status:

```bash
curl http://localhost:9000/status
```

Expected response shape:

```json
{
  "vector_db": "chroma",
  "collection": "amazon_products",
  "count": 500,
  "persist_directory": "./chroma_amazon_db"
}
```

## Query Indexed CSV Data

After indexing, query the vector DB with `/search`:

```bash
curl -X POST http://localhost:9000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "wireless earbuds under $50 with good ratings", "k": 5}'
```

Fast structured recommendations without LLM generation:

```bash
curl -X POST http://localhost:9000/recommendations \
  -H "Content-Type: application/json" \
  -d '{"question": "wireless earbuds under $50 with good ratings", "k": 5}'
```

LLM-generated answer, slower because it calls Ollama LLM:

```bash
curl -X POST http://localhost:9000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "wireless earbuds under $50 with good ratings", "k": 5}'
```

Streaming LLM answer:

```bash
curl -N -X POST http://localhost:9000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "wireless earbuds under $50 with good ratings", "k": 5}'
```

Fast streaming recommendations without LLM:

```bash
curl -N -X POST http://localhost:9000/recommendations/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "wireless earbuds under $50 with good ratings", "k": 5}'
```

## App DB CRUD (Auto-Sync Embeddings)

Create or update a product (syncs embedding immediately):

```bash
curl -X POST http://localhost:9000/products \
  -H "Content-Type: application/json" \
  -d '{
    "parent_asin": "TEST-ASIN-001",
    "title": "Test Earbuds",
    "description": "Bluetooth earbuds with charging case",
    "main_category": "Electronics",
    "store": "Test Store",
    "average_rating": 4.7,
    "rating_number": 150,
    "price": 39.99
  }'
```

Update by id:

```bash
curl -X PUT http://localhost:9000/products/TEST-ASIN-001 \
  -H "Content-Type: application/json" \
  -d '{\"parent_asin\":\"TEST-ASIN-001\",\"price\":35.99,\"average_rating\":4.8}'
```

Delete (also removes embedding):

```bash
curl -X DELETE http://localhost:9000/products/TEST-ASIN-001
```

## Query Examples

Natural language filters are inferred by backend:

```bash
curl -X POST http://localhost:9000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "wireless earbuds under $50 with good ratings and minimum price is $10", "k": 5}'
```

```bash
curl -X POST http://localhost:9000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "wireless earbuds under $50 minimum rating 4.5", "k": 5}'
```

```bash
curl -X POST http://localhost:9000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "wireless earbuds with lower ratings", "k": 5}'
```

```bash
curl -X POST http://localhost:9000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "wireless earbuds with maximum price and ratings but price do not will be empty, zero, null", "k": 5}'
```

You can also pass explicit structured filters:

```bash
curl -X POST http://localhost:9000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "wireless earbuds",
    "k": 5,
    "filter": {
      "main_category": "Electronics",
      "price": {"min": 10, "max": 50},
      "average_rating": {"min": 4.5},
      "rating_number": {"min": 100}
    }
  }'
```

## Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Frontend `.env`:

```bash
VITE_API_BASE=http://127.0.0.1:9000
```

Open:

```txt
http://localhost:5173
```

Or run helper script:

```bash
cd frontend
./run.sh
```

Frontend supports:

- Export HuggingFace data to CSV.
- Index App DB into vector DB.
- Fast JSON recommendations.
- Search result cards.
- Copy JSON.
- Status panel showing active vector DB and count.

## API Endpoints

- `GET /health`
- `GET /status`
- `POST /dataset/export`
- `POST /index`
- `POST /index/stream`
- `POST /search`
- `POST /recommendations`
- `POST /recommendations/stream`
- `POST /chat`
- `POST /chat/stream`
- `GET /products`
- `GET /products/{parent_asin}`
- `POST /products`
- `PUT /products/{parent_asin}`
- `DELETE /products/{parent_asin}`
- `POST /products/import`

## Troubleshooting

If search returns empty results:

```bash
curl http://localhost:9000/status
```

If count is `0` or old data is still present, reindex with `reset: true`:

```bash
curl -N -X POST http://localhost:9000/index/stream \
  -H "Content-Type: application/json" \
  -d '{"limit": 500, "keyword": "earbuds", "data_source": "app_db", "batch_size": 10, "reset": true}'
```

If indexing fails with Ollama context-length errors, lower this in `backend/.env`:

```bash
EMBED_MAX_CHARS=1000
```

If frontend cannot reach backend, confirm:

```bash
curl http://localhost:9000/health
```

And confirm frontend env:

```bash
VITE_API_BASE=http://127.0.0.1:9000
```
