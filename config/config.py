import os
from dotenv import load_dotenv

load_dotenv(override=True)
# ========= LLM CONFIG =========
# Fallback priority: Groq → Gemini → HuggingFace → Ollama (local)

# --- Gemini (tried first) ---
USE_GEMINI = True
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- HuggingFace Inference API (tried second) ---
USE_HF = True
HF_MODEL = os.getenv("HF_MODEL", "meta-llama/Llama-3.3-70B-Instruct")
HF_API_TOKEN = os.getenv("HF_API_TOKEN")

# --- Groq Inference API (tried third) ---
USE_GROQ = True
GROQ_MODEL = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct") #llama-3.1-8b-instant, llama-3.3-70b-versatile
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# --- Ollama fallback (local, tried last) ---
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# --- SSL ---
# Set SSL_VERIFY=false in .env if you are behind a corporate SSL proxy
# (e.g. Infosys network) that intercepts HTTPS traffic.
SSL_VERIFY = os.getenv("SSL_VERIFY", "true").strip().lower() not in ("false", "0", "no")

# --- Logging ---
# LOG_LEVEL controls verbosity. DEBUG = all logs; INFO = normal flow only.
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()

# ========= RAG CONFIG =========
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 600
CHUNK_OVERLAP = 150
TOP_K = 5

# Cosine similarity threshold for duplicate detection (0.0–1.0).
# Two test cases with similarity >= this value are considered duplicates.
# Lower = more aggressive dedup. Recommended range: 0.90–0.97
DEDUP_THRESHOLD = 0.92

# ========= HYBRID RAG CONFIG =========
# How many FAISS candidates to fetch BEFORE module + similarity filtering.
RAG_FETCH_K = 15
# Minimum cosine similarity (0.0–1.0) for a chunk to be included as context.
RAG_SIMILARITY_THRESHOLD = 0.50

# ========= PATHS =========
INPUT_DIR = "data/sample_requirements"
OUTPUT_FILE = "data/generated_tests.xlsx"
FAISS_INDEX_FILE = "data/faiss_index.faiss"
RAG_METADATA_FILE = "data/metadata.json"
