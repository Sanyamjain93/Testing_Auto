from pathlib import Path
from config.config import (
    CHUNK_SIZE, INPUT_DIR, CHUNK_OVERLAP, EMBEDDING_MODEL, OUTPUT_FILE, TOP_K,
    RAG_FETCH_K, RAG_SIMILARITY_THRESHOLD, FAISS_INDEX_FILE, RAG_METADATA_FILE,
)
from ingestion.document_loader import load_document
from retrieval.chunker import chunk_requirements
from retrieval.embedder import Embedder
from retrieval.vector_store import VectorStore
from prompts.testcase_prompt import PROMPT_TEMPLATE
from util.mistral_client import MistralLLM
from util.excel_writer import write_excel
from util.scorer import score_all
from util.deduplicator import deduplicate
from util.json_parser import validate_and_filter_tests
from logger import get_logger
import json
import re
import time

logger = get_logger("test_automation.pipeline")

_SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".md", ".xlsx"}


def detect_module(text: str) -> str:
    """Infer the Oracle Retail module from requirement text keywords."""
    t = text.lower()
    if any(kw in t for kw in ("invoice", "matching", "receipt", "reim")):
        return "REIM"
    if any(kw in t for kw in ("sales audit", "resa")):
        return "RESA"
    if any(kw in t for kw in ("warehouse", "wms")):
        return "WMS"
    if any(kw in t for kw in ("inventory", "sim", "stock count")):
        return "SIM"
    return "RMS"


def _module_from_path(file_path: Path, input_dir: str) -> str | None:
    """Derive module from subfolder name (e.g. .../rms/file.pdf → 'RMS').
    Returns None when the file lives directly in the root input folder."""
    try:
        rel = file_path.relative_to(input_dir)
        if len(rel.parts) > 1:
            return rel.parts[0].upper()
    except ValueError:
        pass
    return None


def _clean_llm_json(raw: str) -> str:
    """Best-effort cleanup of LLM output to produce parseable JSON."""
    # Strip markdown code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())

    # Extract the outermost JSON object or array
    for start_char, end_char in (("{" , "}"), ("[", "]")):
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end + 1]
            break

    # Replace literal newlines/tabs inside JSON string values with escaped versions.
    # We do this by scanning character-by-character and only replacing inside quoted strings.
    result = []
    in_string = False
    escape_next = False
    for ch in raw:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == "\\":
            result.append(ch)
            escape_next = True
        elif ch == '"':
            in_string = not in_string
            result.append(ch)
        elif in_string and ch == "\n":
            result.append("\\n")
        elif in_string and ch == "\r":
            result.append("\\r")
        elif in_string and ch == "\t":
            result.append("\\t")
        else:
            result.append(ch)
    return "".join(result)


def run(provider: str = "groq", model: str = "meta-llama/llama-4-scout-17b-16e-instruct", emit_progress=None):
    def emit(stage: str, status: str) -> None:
        """Emit progress event if callback is provided."""
        if emit_progress:
            emit_progress(stage, status)

    emit("loading_documents", "running")
    print(f"📂 Loading documents from: {INPUT_DIR}")
    logger.info(f"[PIPELINE] run() started — loading from {INPUT_DIR}")
    if not Path(INPUT_DIR).exists():
        logger.warning(f"Input directory not found: {INPUT_DIR}")
        print(f"⚠️  Input directory not found: {INPUT_DIR}")
        return

    all_chunks = []
    for f in sorted(Path(INPUT_DIR).rglob("*")):
        if not f.is_file() or f.suffix.lower() not in _SUPPORTED_EXTS:
            continue
        raw_text = load_document(f)
        module = _module_from_path(f, INPUT_DIR) or detect_module(raw_text[:500])
        logger.debug(f"Loading [{module}]: {f.relative_to(INPUT_DIR)}")
        file_chunks = chunk_requirements(raw_text, CHUNK_SIZE, CHUNK_OVERLAP)
        for c in file_chunks:
            c["module"] = module
        all_chunks.extend(file_chunks)

    if not all_chunks:
        logger.warning("No documents found in input directory.")
        print("⚠️  No documents found. Exiting.")
        return

    print(f"✅ Documents loaded. {len(all_chunks)} requirement chunks across all files.\n")
    logger.info(f"[PIPELINE] {len(all_chunks)} requirement chunks loaded from {INPUT_DIR}")
    emit("loading_documents", "done")

    # Extract plain texts for embedding
    chunk_texts = [c["requirement_text"] for c in all_chunks]

    print(f"🔢 Embedding chunks using model: {EMBEDDING_MODEL}")
    logger.info(f"[PIPELINE] Embedding {len(all_chunks)} chunks with model: {EMBEDDING_MODEL}")
    embedder = Embedder(EMBEDDING_MODEL)
    vectors = embedder.embed(chunk_texts)
    print(f"✅ Embeddings complete. Vector dimensions: {len(vectors[0])}\n")
    logger.info(f"[PIPELINE] Embeddings complete. dim={len(vectors[0])}")

    # ── Load existing FAISS index or build a new one ───────────────────────
    emit("rag_retrieval", "running")
    if Path(FAISS_INDEX_FILE).exists() and Path(RAG_METADATA_FILE).exists():
        print("🗄️  Loading existing FAISS index from disk...")
        store = VectorStore.load(FAISS_INDEX_FILE, RAG_METADATA_FILE)
        print(f"✅ Loaded FAISS index ({store.index.ntotal} vectors) and metadata ({len(store.metadata)} entries)\n")
        logger.info(f"[PIPELINE] FAISS index loaded from disk: {store.index.ntotal} vectors, {len(store.metadata)} metadata entries")
    else:
        print("🗄️  Building FAISS vector store...")
        store = VectorStore(len(vectors[0]))
        chunk_metadata = [
            {
                "id": i,
                "text": c["requirement_text"],
                "module": c["module"],
                "requirement_id": c["requirement_id"],
            }
            for i, c in enumerate(all_chunks)
        ]
        store.add(vectors, chunk_metadata)
        store.save(FAISS_INDEX_FILE, RAG_METADATA_FILE)
        print(f"✅ FAISS index built and saved ({store.index.ntotal} vectors)\n")
        logger.info(f"[PIPELINE] FAISS index built and saved: {store.index.ntotal} vectors")

    llm = MistralLLM(provider, model)
    emit("rag_retrieval", "done")

    print(f"🤖 Starting test case generation ({len(all_chunks)} chunks) with {provider} / {model}...\n")
    logger.info(f"[PIPELINE] Starting generation for {len(all_chunks)} chunks")
    emit("generating_tests", "running")

    test_cases = []
    # Coverage tracking: requirement_id → list of test names
    requirement_to_tests: dict[str, list[str]] = {c["requirement_id"]: [] for c in all_chunks}

    for i, chunk in enumerate(all_chunks):
        req_id = chunk["requirement_id"]
        req_text = chunk["requirement_text"]
        detected_module = chunk["module"]
        print(f"   ⏳ [{i + 1}/{len(all_chunks)}] {req_id} [module={detected_module}]...")
        logger.info(f"[PIPELINE] Processing chunk {i + 1}/{len(all_chunks)}: {req_id} [module={detected_module}]")
        start_time = time.time()

        # ── Module-aware RAG retrieval ─────────────────────────────────────
        fetch_k = min(RAG_FETCH_K + 1, store.index.ntotal)
        indices, scores = store.search(vectors[i], k=fetch_k)

        logger.debug(f"[RAG] Raw candidates fetched: {len(indices)}")
        for rank, (ridx, rscore) in enumerate(zip(indices[:5], scores[:5])):
            if 0 <= ridx < len(store.metadata):
                rmeta = store.metadata[ridx]
                logger.debug(
                    f"[RAG] Candidate #{rank + 1} | Score={rscore:.3f} | "
                    f"Module={rmeta['module']} | ReqID={rmeta['requirement_id']}"
                )

        context_chunks: list[str] = []
        for idx, score in zip(indices, scores):
            if len(context_chunks) >= TOP_K:
                break
            if idx < 0 or idx >= len(store.metadata):
                continue
            meta = store.metadata[idx]
            if meta["requirement_id"] == req_id:   # skip self
                continue

            reasons = []
            if meta["module"] != detected_module:
                reasons.append("module mismatch")
            if score < RAG_SIMILARITY_THRESHOLD:
                reasons.append("low score")

            if reasons:
                logger.debug(
                    f"[RAG DROP] {reasons} | Score={score:.3f} | "
                    f"Module={meta['module']} | ReqID={meta['requirement_id']}"
                )
                continue

            context_chunks.append(meta["text"])

        logger.debug(f"[RAG] Final context chunks: {len(context_chunks)}")
        if not context_chunks:
            logger.warning(
                f"[RAG MISS] Req={req_id} | No context above threshold. "
                f"Falling back to requirement-only generation"
            )
        context = "\n\n---\n\n".join(context_chunks)

        prompt = PROMPT_TEMPLATE.format(
            requirement_id=req_id,
            incoming_req=req_text,
            context=context,
            module=detected_module,
        )
        estimated_tokens = int(len(prompt.split()) * 1.3)
        logger.info(f"[LLM] Req={req_id} | Estimated tokens: {estimated_tokens}")
        logger.debug(f"[LLM INPUT] Req={req_id} | Prompt preview:\n{prompt[:500]}")

        raw = llm.generate(prompt)

        logger.debug(f"[LLM OUTPUT RAW] Req={req_id} | Output preview:\n{raw[:500]}")

        try:
            cleaned = _clean_llm_json(raw)
            parsed = json.loads(cleaned)

            # Handle both formats:
            if isinstance(parsed, dict) and "tests" in parsed:
                new_tests = parsed["tests"]
            elif isinstance(parsed, list):
                new_tests = parsed
            else:
                raise ValueError("Unexpected JSON structure")

            # Validate traceability fields; backfill / reject as needed.
            new_tests = validate_and_filter_tests(new_tests, req_id, req_text)

            test_cases.extend(new_tests)

            # Record coverage
            for tc in new_tests:
                requirement_to_tests.setdefault(req_id, []).append(tc.get("test_name", ""))

            logger.info(f"[COVERAGE] {req_id} → {len(new_tests)} test case(s)")
            print(f"   ✅ [{i + 1}/{len(all_chunks)}] {req_id}: {len(new_tests)} test case(s). Total: {len(test_cases)}")

        except (json.JSONDecodeError, ValueError) as err:
            logger.warning(f"[JSON ERROR] Req={req_id} | Invalid JSON: {err}")
            logger.debug(f"[JSON ERROR] Raw output preview: {raw[:300]}")
            print(f"   ⚠️  [{i + 1}/{len(all_chunks)}] {req_id}: LLM returned invalid JSON, skipping.")

        elapsed = time.time() - start_time
        logger.info(f"[TIME] Req={req_id} processed in {elapsed:.2f}s")
    print(f"\n🧹 Deduplicating {len(test_cases)} test cases...")
    test_cases = deduplicate(test_cases)
    print(f"\n📊 Scoring {len(test_cases)} test cases for quality...")
    score_all(test_cases, llm)

    # ── Coverage report ────────────────────────────────────────────────────
    print("\n📋 TRACEABILITY COVERAGE REPORT")
    print("─" * 50)
    uncovered = []
    for req_id, test_names in requirement_to_tests.items():
        surviving = [
            tc.get("test_name", "")
            for tc in test_cases
            if tc.get("requirement_id") == req_id
        ]
        count = len(surviving)
        logger.info(f"[COVERAGE] {req_id} → {count} test case(s) (post-dedup)")
        if count == 0:
            uncovered.append(req_id)
    if uncovered:
        logger.warning(f"[COVERAGE GAP] Missing test cases for: {uncovered}")
        print(f"\n   ⚠️  Requirements with ZERO test cases ({len(uncovered)}):")
        for req_id in uncovered:
            print(f"      - {req_id}")
    else:
        print("\n   ✅ All requirements have at least one test case.")
    print("─" * 50)

    print(f"\n📊 Writing {len(test_cases)} test cases to: {OUTPUT_FILE}")

    # Renumber all test cases sequentially (001_, 002_, ...) across the full output.
    # The LLM restarts numbering from 001 for each chunk, so we fix it here.

    for idx, tc in enumerate(test_cases, start=1):
        prefix = f"{idx:03d}_"
        # Strip any existing leading NNN_ prefix the LLM added, then prepend the correct one
        clean_name = re.sub(r"^\d{3}_", "", tc.get("test_name", ""))
        clean_desc = re.sub(r"^\d{3}_", "", tc.get("test_description", ""))
        tc["test_name"] = prefix + clean_name
        tc["test_description"] = clean_desc

    write_excel(test_cases, OUTPUT_FILE)
    print(f"✅ Done! Output saved to: {OUTPUT_FILE}")
    logger.info(f"[PIPELINE] Pipeline complete. {len(test_cases)} test cases saved to {OUTPUT_FILE}")
    emit("generating_tests", "done")