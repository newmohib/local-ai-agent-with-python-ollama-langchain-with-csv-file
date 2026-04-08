import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3.2")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "mxbai-embed-large")
EMBED_MAX_CHARS = int(os.getenv("EMBED_MAX_CHARS", "1000"))

VECTOR_DB = os.getenv("VECTOR_DB", "chroma")

CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_amazon_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "amazon_products")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "amazon_products")
USER_COLLECTION_NAME = os.getenv("USER_COLLECTION_NAME", "users")
USER_QDRANT_COLLECTION = os.getenv("USER_QDRANT_COLLECTION", "users")

HF_DATASET_ID = os.getenv("HF_DATASET_ID", "milistu/AMAZON-Products-2023")
HF_SPLIT = os.getenv("HF_SPLIT", "train")
DATA_SOURCE = os.getenv("DATA_SOURCE", "csv")
LOCAL_CSV_PATH = os.getenv("LOCAL_CSV_PATH", "./data/amazon_products.csv")
APP_DB_PATH = os.getenv("APP_DB_PATH", "./app_db.sqlite3")
USER_DB_PATH = os.getenv("USER_DB_PATH", "./user_db.sqlite3")
INDEX_LIMIT = int(os.getenv("INDEX_LIMIT", "5000"))
INDEX_BATCH_SIZE = int(os.getenv("INDEX_BATCH_SIZE", "10"))
SEARCH_FETCH_MULTIPLIER = int(os.getenv("SEARCH_FETCH_MULTIPLIER", "4"))
SEARCH_FETCH_MAX = int(os.getenv("SEARCH_FETCH_MAX", "30"))

FORCE_REINDEX = os.getenv("FORCE_REINDEX", "false").lower() == "true"
