# Prompt: Recreate the AI Test Automation Project

Use the instructions below to build a complete Python project from scratch that auto-generates structured software test cases from requirements documents using a RAG (Retrieval-Augmented Generation) pipeline backed by an LLM.

---

## Project Overview

Build a Python CLI application that:
1. Reads requirements documents (PDF, DOCX, XLSX, TXT) from an input folder.
2. Parses and chunks the text into individual requirements using `REQ ID:` markers.
3. Embeds all chunks with a sentence-transformer model and stores them in a FAISS vector index.
4. For each requirement chunk, retrieves the TOP-K most semantically similar neighbors to use as RAG context.
5. Calls an LLM (with a multi-backend fallback chain: Gemini → HuggingFace → Ollama) to generate structured test cases as JSON.
6. Validates, cleans, and backfills traceability fields in the returned JSON.
7. Deduplicates test cases using cosine similarity on their name + description embeddings.
8. Scores all test cases in batches using the same LLM and a separate scoring prompt.
9. Renumbers test cases sequentially and writes the final output to an Excel file.
10. Prints a traceability coverage report (per requirement ID, how many test cases survived).

---

## Folder Structure

```
project-root/
├── run.py                        # Entry point (SSL fix + calls pipeline.run())
├── pipeline.py                   # Main orchestration pipeline
├── main.py                       # Stub (prints hello)
├── pyproject.toml                # Project metadata and dependencies
├── requirement.txt               # pip requirements
├── .env                          # API keys and toggles (NOT committed to git)
│
├── config/
│   ├── __init__.py
│   └── config.py                 # All configuration constants
│
├── data/
│   └── sample_requirements/      # Drop requirement docs here (PDF/DOCX/XLSX/TXT)
│
├── ingestion/
│   ├── __init__.py
│   └── document_loader.py        # Multi-format document reader
│
├── retrieval/
│   ├── __init__.py
│   ├── chunker.py                # Smart requirement chunker
│   ├── embedder.py               # SentenceTransformer wrapper
│   └── vector_store.py           # FAISS vector index wrapper
│
├── prompts/
│   ├── __init__.py
│   ├── testcase_prompt.py        # LLM prompt template for test case generation
│   └── scoring_prompt.py         # LLM prompt template for quality scoring
│
└── util/
    ├── __init__.py
    ├── mistral_client.py         # Multi-backend LLM client (Gemini→HF→Ollama)
    ├── scorer.py                 # Batch scoring logic
    ├── deduplicator.py           # Cosine-similarity deduplication
    ├── excel_writer.py           # Pandas Excel output writer
    └── json_parser.py            # JSON validation and field backfill
```

---

## File-by-File Implementation

### `run.py`
Entry point. Performs two tasks before launching the pipeline:
1. **Corporate SSL proxy fix**: Try to `import truststore; truststore.inject_into_ssl()`. If the env var `SSL_VERIFY=false` is set in `.env`, disable SSL verification globally across `ssl`, `urllib3`, and set `REQUESTS_CA_BUNDLE=""` and `CURL_CA_BUNDLE=""` to empty strings.
2. Load `.env` with `python-dotenv` (`load_dotenv(override=True)`) and then call `from pipeline import run; run()`.

```python
# run.py
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import os
from dotenv import load_dotenv
load_dotenv(override=True)

if os.getenv("SSL_VERIFY", "true").strip().lower() in ("false", "0", "no"):
    import ssl, warnings, urllib3
    ssl._create_default_https_context = ssl._create_unverified_context
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    os.environ["REQUESTS_CA_BUNDLE"] = ""
    os.environ["CURL_CA_BUNDLE"] = ""
    print("   ⚠️  SSL verification DISABLED (SSL_VERIFY=false).")

from pipeline import run

if __name__ == "__main__":
    run()
```

---

### `config/config.py`
All configuration in one place. Load `.env` at the top.

```python
import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ── LLM CONFIG ──────────────────────────────────────────────────────────────
# Fallback order: Gemini → HuggingFace → Ollama

USE_GEMINI      = True
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GOOGLE_API_KEY  = os.getenv("GOOGLE_API_KEY")

USE_HF          = True
HF_MODEL        = os.getenv("HF_MODEL", "meta-llama/Llama-3.3-70B-Instruct")
HF_API_TOKEN    = os.getenv("HF_API_TOKEN")

OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

SSL_VERIFY = os.getenv("SSL_VERIFY", "true").strip().lower() not in ("false", "0", "no")

# ── RAG CONFIG ───────────────────────────────────────────────────────────────
EMBEDDING_MODEL  = "all-MiniLM-L6-v2"
CHUNK_SIZE       = 600
CHUNK_OVERLAP    = 150
TOP_K            = 5
DEDUP_THRESHOLD  = 0.92   # cosine similarity above which two test cases are duplicates

# ── PATHS ────────────────────────────────────────────────────────────────────
INPUT_DIR   = "data/sample_requirements"
OUTPUT_FILE = "data/generated_tests.xlsx"
```

---

### `ingestion/document_loader.py`
Reads a single file and returns its full text as a plain string. Supported formats:
- `.pdf` → use `PyPDF2.PdfReader`, join all page texts
- `.docx` → use `python-docx`, join all paragraph texts
- `.xlsx` → use `pandas.read_excel`, flatten all cells to string and join
- `.txt` → `path.read_text()`
- Any other extension → raise `ValueError("Unsupported file type: ...")`

```python
from PyPDF2 import PdfReader
from docx import Document
import pandas as pd
from pathlib import Path

def load_document(path: Path) -> str:
    if path.suffix == ".pdf":
        reader = PdfReader(path)
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    if path.suffix == ".docx":
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    if path.suffix == ".xlsx":
        df = pd.read_excel(path)
        return "\n".join(df.astype(str).values.flatten())
    if path.suffix == ".txt":
        return path.read_text()
    raise ValueError(f"Unsupported file type: {path.suffix}")
```

---

### `retrieval/chunker.py`
Two regex patterns:
- `_REQ_ID_PATTERN`: matches `REQ ID: RMS-LOGIN-001` or `REQUIREMENT ID: FOO-001` etc.
- `_SUBREQ_NUM_PATTERN`: matches numbered sub-requirements like `1.1`, `1.2`, `2.3.1` not preceded by a word character.

**`chunk_requirements(text, chunk_size, overlap)`** — main function:
1. Normalize whitespace (collapse multi-space, remove blank lines).
2. Find all `_REQ_ID_PATTERN` matches to locate requirement blocks.
3. For each block (text between consecutive REQ ID markers), try to split further by `_SUBREQ_NUM_PATTERN`. If sub-requirements are found, each numbered item becomes its own chunk with ID `{req_id}_{subreq_num}`. If not, keep the block as a single chunk.
4. If no REQ ID markers exist at all, fall back to plain character-based sliding-window chunking and assign auto-IDs `REQ-001`, `REQ-002`, etc.
5. Return a list of dicts: `[{"requirement_id": "...", "requirement_text": "..."}, ...]`

Also include a legacy `chunk_text(text, chunk_size, overlap)` that returns a plain `list[str]` using the sliding-window approach.

---

### `retrieval/embedder.py`
Thin wrapper around `sentence_transformers.SentenceTransformer`.

```python
from sentence_transformers import SentenceTransformer

class Embedder:
    def __init__(self, model_name: str):
        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]):
        return self.model.encode(texts, show_progress_bar=True)
```

---

### `retrieval/vector_store.py`
Thin wrapper around `faiss.IndexFlatL2`.

```python
import faiss
import numpy as np

class VectorStore:
    def __init__(self, dim: int):
        self.index = faiss.IndexFlatL2(dim)

    def add(self, vectors):
        self.index.add(np.array(vectors, dtype=np.float32))

    def search(self, query_vec, k: int):
        query = np.array(query_vec, dtype=np.float32).reshape(1, -1)
        distances, indices = self.index.search(query, k)
        return indices[0]
```

---

### `prompts/testcase_prompt.py`
Define a single module-level string `PROMPT_TEMPLATE` that instructs the LLM to act as an expert QA engineer and output **only a valid JSON object** of this schema:

```json
{
  "tests": [
    {
      "requirement_id": "string",
      "requirement_text": "string",
      "test_name": "string",
      "test_description": "string",
      "steps": [
        {
          "step_name": "string",
          "action": "string",
          "expected_result": "string"
        }
      ]
    }
  ]
}
```

The prompt must enforce:
- **Traceability**: `requirement_id` and `requirement_text` must be copied EXACTLY from the inputs — never invented.
- **Naming convention**: `test_name` starts with a 3-digit prefix (`001_`, `002_`, ...) followed by the description text. `test_description` is identical but without the prefix.
- **Step naming**: Always `"Step 1"`, `"Step 2"`, etc. — restarting from Step 1 per test case. Never use descriptive step names.
- **Action richness**: Multi-line, detailed, includes preconditions, data setup, system/module context.
- **Expected results**: Present for every step; must be concrete and measurable.
- **Scope discipline**: Only generate test cases for the provided requirement. Do NOT bleed into unrelated modules.

The template uses three format placeholders: `{requirement_id}`, `{incoming_req}`, `{context}`.

Since the template contains JSON example braces, escape literal braces as `{{` and `}}` in the Python f-string / `.format()` template.

---

### `prompts/scoring_prompt.py`
Define `BATCH_SCORING_PROMPT_TEMPLATE` — instructs the LLM to output a **valid JSON array** with one entry per test case:

```json
[
  {
    "index": <int>,
    "score": <int 1-10>,
    "verdict": "<PASS|REVIEW|FAIL>",
    "flags": ["issue 1", "issue 2"]
  }
]
```

Scoring rubric:
- 8–10 → PASS
- 5–7  → REVIEW
- 1–4  → FAIL

Evaluation dimensions: completeness, clarity, coverage, structure, specificity.

Flags to detect (examples):
- `"Vague expected result in Step X"`
- `"Action in Step X lacks preconditions or data setup"`
- `"Test case is too generic"`
- `"Missing steps for error/negative scenario"`
- `"Step numbering is incorrect"`
- `"Test name and description do not match"`
- `"Only one step — insufficient coverage"`

Template placeholders: `{test_cases_block}`, `{count}`.

---

### `util/mistral_client.py`
Class `MistralLLM` with a multi-backend `generate(prompt: str) -> str` method.

**Backends in priority order:**

1. **Gemini** (via `google-genai` SDK): `genai.Client(api_key=GOOGLE_API_KEY).models.generate_content(model=GEMINI_MODEL, contents=prompt)`. Retry up to 8 times with exponential backoff + jitter. Skip all retries and fall through on `RESOURCE_EXHAUSTED`, `QUOTA_EXCEEDED`, `PERMISSION_DENIED`, `NOT_FOUND`, `INVALID_ARGUMENT`, or HTTP 429. Parse `retryDelay` from the API error string for server-specified wait times.

2. **HuggingFace** (via `huggingface_hub.InferenceClient`): Call `chat_completion(messages=[{"role": "user", "content": prompt}], max_tokens=4096)`. Retry on 429 and 5xx. Immediately re-raise on 401, 402, 403 (auth/billing errors).

3. **Ollama** (local, last resort): POST to `{OLLAMA_BASE_URL}/api/generate` with `{"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}`, timeout=300s. Return `response.json()["response"]`.

Raise `RuntimeError("All LLM backends failed. ...")` only if all three fail.

**Retry helper `_wait(attempt, reason, exc=None)`**: if the exception contains `'retryDelay': '12.5s'`, use that delay; otherwise use `BASE_DELAY * 2^(attempt-1) + uniform(0,1)`.

---

### `util/json_parser.py`
Two functions:
1. `safe_parse(text: str) -> dict`: `json.loads(text)` wrapped in a try/except, returns `{"error": "Invalid JSON", "raw": text}` on failure.
2. `validate_and_filter_tests(tests: list, expected_requirement_id: str, expected_requirement_text: str) -> list`:
   - For each test case dict:
     - If `requirement_id` is missing or empty → backfill from `expected_requirement_id` and log a warning.
     - If `requirement_text` is missing or empty → backfill from `expected_requirement_text` and log a warning.
     - If `requirement_id` does not exactly match `expected_requirement_id` → log error and skip the test case.
     - If `requirement_text` is still empty after backfill → log error and skip.
   - Return only valid test cases.

---

### `util/deduplicator.py`
Function `deduplicate(test_cases: list[dict]) -> list[dict]`:
1. Build a text fingerprint for each test case: `f"{test_name} {test_description}".strip()`.
2. Embed all fingerprints using `Embedder(EMBEDDING_MODEL)`.
3. Iterate through vectors; for each, compare cosine similarity against all already-kept vectors.
4. If similarity ≥ `DEDUP_THRESHOLD`, mark as duplicate and skip; otherwise add to kept list.
5. Return the kept test cases. Print count of kept vs. removed.

---

### `util/scorer.py`
Function `score_all(test_cases: list[dict], llm, batch_size=10) -> None`:
1. Split test cases into batches of `batch_size`.
2. For each batch, format a human-readable block (index, test name, description, steps) with literal `{` and `}` escaped, insert into `BATCH_SCORING_PROMPT_TEMPLATE`, call `llm.generate(prompt)`.
3. Parse the JSON array response. Map `index → {quality_score, quality_verdict, quality_flags}`.
4. Update each test case dict in-place. On error, set `quality_verdict="ERROR"`.
5. After all batches, print a summary: `PASS | REVIEW | FAIL | Total`.

---

### `util/excel_writer.py`
Function `write_excel(test_cases: list[dict], output_path: str) -> None`:
- Flatten each test case into one row per step.
- Columns: `Requirement ID`, `Requirement Text`, `Test Name`, `Test Description`, `Step Name`, `Action`, `Expected Result`, `Quality Score`, `Quality Verdict`, `Quality Flags`.
- Write with `pandas.DataFrame(rows).to_excel(output_path, index=False)`.

---

### `pipeline.py`
Main orchestration function `run()`:

```
1. Load all documents from INPUT_DIR using load_document().
2. Concatenate all texts.
3. Chunk into requirements using chunk_requirements(text, CHUNK_SIZE, CHUNK_OVERLAP).
4. Extract chunk_texts = [c["requirement_text"] for c in chunks].
5. Embed chunk_texts with Embedder(EMBEDDING_MODEL).
6. Build VectorStore, add all vectors.
7. Initialize MistralLLM().
8. For each chunk[i]:
   a. Search vector store for TOP_K+1 neighbors, drop index i itself, take TOP_K.
   b. Join retrieved texts with "\n\n---\n\n" as context.
   c. Format PROMPT_TEMPLATE with requirement_id, incoming_req, context.
   d. Call llm.generate(prompt) → raw string.
   e. Call _clean_llm_json(raw) to strip markdown fences and fix unescaped control chars inside strings.
   f. json.loads() → handle both {"tests": [...]} and plain list formats.
   g. validate_and_filter_tests() → backfill/reject bad entries.
   h. Append valid test cases to master list; track coverage map {req_id: [test_names]}.
9. deduplicate(test_cases).
10. score_all(test_cases, llm).
11. Print TRACEABILITY COVERAGE REPORT: per req_id, how many test cases survived dedup.
    Flag any requirements with zero test cases.
12. Renumber test_name sequentially (001_, 002_, ...): strip any existing NNN_ prefix
    with regex re.sub(r"^\d{3}_", "", name) then prepend the correct f"{idx:03d}_".
13. write_excel(test_cases, OUTPUT_FILE).
```

**`_clean_llm_json(raw: str) -> str`** helper:
- Strip leading/trailing markdown fences (` ```json `, ` ``` `).
- Extract the outermost `{...}` or `[...]` substring.
- Scan character-by-character tracking `in_string` and `escape_next` booleans; replace bare `\n`, `\r`, `\t` inside string values with their escape sequences `\\n`, `\\r`, `\\t`.

---

## Dependencies

### `pyproject.toml`
```toml
[project]
name = "test-automation"
version = "0.1.0"
description = "AI-powered test case generation from requirements documents"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "dotenv>=0.9.9",
    "faiss-cpu>=1.13.0",
    "google>=3.0.0",
    "google-genai>=1.0.0",
    "google-generativeai>=0.8.0",
    "huggingface_hub>=0.23.0",
    "ipykernel>=6.0.0",
    "openpyxl>=3.1.0",
    "pandas>=2.0.0",
    "pypdf2>=3.0.0",
    "python-docx>=0.8.11",
    "pyyaml>=6.0.0",
    "requests>=2.31.0",
    "sentence-transformers>=2.7.0",
    "torch>=2.0.0",
    "tqdm>=4.66.0",
    "truststore>=0.9.0",
    "typing-extensions>=4.0.0",
    "python-dotenv>=1.0.0",
]
```

### `.env` (template — do NOT commit)
```
GOOGLE_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash

HF_API_TOKEN=your-huggingface-token
HF_MODEL=meta-llama/Llama-3.3-70B-Instruct

OLLAMA_MODEL=llama3
OLLAMA_BASE_URL=http://localhost:11434

SSL_VERIFY=true
```

---

## How to Run

```bash
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# 2. Install dependencies
pip install -e .

# 3. Add your API keys to .env

# 4. Drop requirement documents into data/sample_requirements/
#    Supported: .pdf, .docx, .xlsx, .txt
#    Documents must contain REQ ID markers like:
#      "REQ ID: RMS-LOGIN-001"

# 5. Run the pipeline
python run.py

# 6. Output is written to data/generated_tests.xlsx
```

---

## Expected Output Excel Columns
| Column | Description |
|---|---|
| Requirement ID | Source requirement identifier (e.g. `RMS-LOGIN-001`) |
| Requirement Text | Full text of the requirement |
| Test Name | `001_To validate if able to login with valid credentials` |
| Test Description | Same as Test Name but without the `001_` prefix |
| Step Name | `Step 1`, `Step 2`, ... |
| Action | Detailed action description |
| Expected Result | Concrete, observable system behavior |
| Quality Score | Integer 1–10 from LLM scoring |
| Quality Verdict | `PASS`, `REVIEW`, or `FAIL` |
| Quality Flags | Semicolon-separated list of quality issues |

---

## Key Design Decisions to Preserve
1. **Fallback LLM chain**: Never hard-fail on a single LLM. Always try Gemini → HuggingFace → Ollama in order.
2. **Retry with exponential backoff**: Use `BASE_DELAY * 2^(attempt-1) + jitter`. Honor API-specified `retryDelay` values from error messages.
3. **JSON repair before parsing**: LLMs frequently wrap output in markdown fences or embed raw newlines inside string values. Always clean before `json.loads()`.
4. **Field backfill over rejection**: If `requirement_id` or `requirement_text` is missing but the structure is valid, backfill from the chunk rather than discard.
5. **Semantic deduplication**: Use cosine similarity on embeddings of `test_name + test_description`, not exact string matching. Default threshold: 0.92.
6. **Batched scoring**: Score 10 test cases per LLM call to minimize API usage.
7. **Sequential renumbering**: Always renumber test case names with `001_`, `002_`, ... after deduplication to ensure contiguous IDs.
8. **Corporate proxy support**: Respect `SSL_VERIFY=false` in `.env` and propagate it to all HTTP stacks (`ssl`, `urllib3`, `requests`, `httpx`).
