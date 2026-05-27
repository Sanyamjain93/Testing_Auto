"""
FastAPI backend for the AI Test Case Generator.

Endpoints
---------
GET  /status          – pipeline state
POST /upload          – upload requirement documents
POST /run             – start the pipeline (background thread)
GET  /stream          – SSE log stream (real-time progress)
GET  /results         – generated test cases as JSON
GET  /download        – download generated_tests.xlsx
"""

import contextlib
import io
import json
import logging
import mimetypes
import queue
import re
import shutil
import sys
import threading
import zipfile
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent          # project root
INPUT_DIR = ROOT / "data" / "sample_requirements"
OUTPUT_FILE = ROOT / "data" / "generated_tests.xlsx"
FAISS_INDEX_FILE = ROOT / "data" / "faiss_index.faiss"
RAG_METADATA_FILE = ROOT / "data" / "metadata.json"
SCRIPTS_DIR = ROOT / "scripts"
FRONTEND_BUILD = ROOT / "frontend" / "dist"

sys.path.insert(0, str(ROOT))               # make project-level imports available

from logger import get_logger, new_run_log  # noqa: E402 – must come after sys.path update
from util.mistral_client import LLM_OPTIONS, MistralLLM  # noqa: E402
from util.playwright_generator import generate_grouped_script, generate_playwright_script  # noqa: E402

logger = get_logger("test_automation.backend")

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="AI Test Case Generator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://test-automation-2251.azurewebsites.net",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── shared state (single-pipeline assumption) ─────────────────────────────────
_state: dict = {"running": False, "done": False, "error": None}
_lock = threading.Lock()  # guards all check-then-modify operations on _state / _selected_llm
_log_q: queue.Queue = queue.Queue()
_progress_q: queue.Queue = queue.Queue()  # for structured progress events
_ALLOWED_EXT = {".pdf", ".docx", ".txt", ".md"}

# ── LLM selection state ────────────────────────────────────────────────────────
_selected_llm: dict = LLM_OPTIONS[3].copy()  # default: Groq llama-4-scout


class LLMSelection(BaseModel):
    provider: str
    model: str


# ── print() capture for SSE stream ───────────────────────────────────────────
def emit_progress(stage: str, status: str) -> None:
    """Emit a structured progress event (visible to frontend)."""
    _progress_q.put({"stage": stage, "status": status})


class _QueueWriter(io.TextIOBase):
    """Redirect print() output into the SSE log queue (frontend-visible)."""

    def write(self, s: str) -> int:
        if s.strip():
            _log_q.put(s.rstrip())
        return len(s)


def _pipeline_thread() -> None:
    writer = _QueueWriter()
    # Snapshot LLM config under lock so a concurrent /set-llm cannot half-update it
    with _lock:
        provider = _selected_llm["provider"]
        model = _selected_llm["model"]
    log_file = new_run_log()
    logger.info(f"[PIPELINE] Run log: {log_file}")
    try:
        with contextlib.redirect_stdout(writer):
            from pipeline import run  # noqa: PLC0415 – late import intentional
            run(provider=provider, model=model, emit_progress=emit_progress)
        with _lock:
            _state.update({"running": False, "done": True, "error": None})
    except Exception as exc:  # noqa: BLE001
        logger.error("Pipeline failed", exc_info=True)
        _log_q.put(f"❌ Pipeline error: {exc}")
        with _lock:
            _state.update({"running": False, "done": True, "error": str(exc)})


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/status")
def get_status() -> dict:
    return _state


@app.get("/llm-options")
def get_llm_options() -> dict:
    return {"options": LLM_OPTIONS, "selected": _selected_llm}


@app.post("/set-llm")
def set_llm(selection: LLMSelection) -> dict:
    valid = any(
        o["provider"] == selection.provider and o["model"] == selection.model
        for o in LLM_OPTIONS
    )
    if not valid:
        raise HTTPException(status_code=400, detail="Unknown provider/model combination.")
    with _lock:
        if _state["running"]:
            raise HTTPException(status_code=409, detail="Pipeline is running. Cannot change LLM now.")
        _selected_llm.update({"provider": selection.provider, "model": selection.model})
    logger.info(f"[LLM] Selected: {selection.provider} / {selection.model}")
    return {"status": "ok", "selected": _selected_llm}


@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)) -> dict:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Validate extensions before touching the filesystem
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in _ALLOWED_EXT:
            raise HTTPException(
                status_code=400,
                detail=f"'{ext}' is not allowed. Accepted: {sorted(_ALLOWED_EXT)}",
            )

    # Save to a staging directory first — only swap into INPUT_DIR when all writes succeed.
    # This prevents a partial upload from leaving the input directory in a broken state.
    staging = INPUT_DIR.parent / "_upload_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    saved: list[str] = []
    try:
        for f in files:
            dest = staging / Path(f.filename).name  # strip any path components
            with dest.open("wb") as out:
                shutil.copyfileobj(f.file, out)
            saved.append(f.filename)
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"File save failed: {exc}") from exc

    # All writes succeeded — atomically replace INPUT_DIR contents
    for existing in INPUT_DIR.iterdir():
        existing.unlink()
    for staged_file in staging.iterdir():
        shutil.move(str(staged_file), INPUT_DIR / staged_file.name)
    shutil.rmtree(staging, ignore_errors=True)

    logger.info(f"Uploaded {len(saved)} file(s): {saved}")
    return {"uploaded": saved}


@app.post("/reset")
def reset_state() -> dict:
    """Reset backend pipeline state so the frontend starts clean after a user-triggered reset."""
    with _lock:
        if _state["running"]:
            raise HTTPException(status_code=409, detail="Pipeline is running. Wait for it to finish before resetting.")
        _state.update({"running": False, "done": False, "error": None})
    while not _log_q.empty():
        _log_q.get_nowait()
    while not _progress_q.empty():
        _progress_q.get_nowait()
    logger.info("[RESET] State cleared by user.")
    return {"status": "reset"}


@app.post("/run")
def start_pipeline() -> dict:
    with _lock:
        if _state["running"]:
            return {"status": "already_running"}
        _state.update({"running": True, "done": False, "error": None})

    # Drain stale log messages from a previous run
    while not _log_q.empty():
        _log_q.get_nowait()
    while not _progress_q.empty():
        _progress_q.get_nowait()

    thread = threading.Thread(target=_pipeline_thread, daemon=True)
    thread.start()
    return {"status": "started"}


@app.get("/stream")
async def stream_logs() -> StreamingResponse:
    import asyncio  # noqa: PLC0415

    async def _generate() -> AsyncGenerator[str, None]:
        while True:
            try:
                # Check for progress events first
                prog = _progress_q.get_nowait()
                yield f"data: {json.dumps({'progress': prog})}\n\n"
            except queue.Empty:
                pass

            try:
                msg = _log_q.get_nowait()
                yield f"data: {json.dumps({'log': msg})}\n\n"
            except queue.Empty:
                if not _state["running"]:
                    # Drain any items that arrived between the last poll and shutdown
                    draining = True
                    while draining:
                        draining = False
                        try:
                            prog = _progress_q.get_nowait()
                            yield f"data: {json.dumps({'progress': prog})}\n\n"
                            draining = True
                        except queue.Empty:
                            pass
                        try:
                            leftover = _log_q.get_nowait()
                            yield f"data: {json.dumps({'log': leftover})}\n\n"
                            draining = True
                        except queue.Empty:
                            pass
                    break
                await asyncio.sleep(0.15)

        # Final event
        if _state.get("error"):
            yield f"data: {json.dumps({'error': _state['error']})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/rag-index")
def refresh_rag_index() -> dict:
    """Delete persisted FAISS index + metadata so they are rebuilt on the next Run."""
    if _state["running"]:
        raise HTTPException(status_code=409, detail="Pipeline is currently running. Wait for it to finish.")
    deleted = []
    for f in (FAISS_INDEX_FILE, RAG_METADATA_FILE):
        if f.exists():
            f.unlink()
            deleted.append(f.name)
    logger.info(f"RAG index cleared by user: {deleted or 'nothing to delete'}")
    return {"deleted": deleted, "message": "RAG index cleared. It will be rebuilt on the next Run."}


@app.post("/generate-scripts")
def generate_scripts_endpoint() -> dict:
    """Read test cases from the Excel output, generate a Playwright script per test,
    and save each file to the scripts/ directory."""
    if not OUTPUT_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="No test cases found. Run the pipeline first.",
        )

    import openpyxl  # noqa: PLC0415

    wb = openpyxl.load_workbook(OUTPUT_FILE)
    ws = wb.active
    headers = [cell.value for cell in next(ws.iter_rows(max_row=1))]

    # Reconstruct unique test objects from flat Excel rows (one row per step)
    tests_map: dict = {}
    for row_vals in ws.iter_rows(min_row=2, values_only=True):
        row = dict(zip(headers, row_vals))
        key = (row.get("Requirement ID"), row.get("Test Name"), row.get("Test Description"))
        if key not in tests_map:
            tests_map[key] = {
                "requirement_id": row.get("Requirement ID", ""),
                "test_name": row.get("Test Name", ""),
                "test_description": row.get("Test Description", "") or "",
                "test_type": str(row.get("Test Type") or "positive").strip().lower(),
                "steps": [],
            }
        tests_map[key]["steps"].append({
            "step_name": row.get("Step Name", ""),
            "action": row.get("Action", ""),
            "expected_result": row.get("Expected Result", ""),
        })

    tests = list(tests_map.values())
    if not tests:
        raise HTTPException(status_code=404, detail="No test cases found in output file.")

    logger.info(f"[SCRIPT] Generating Playwright scripts for {len(tests)} test case(s)")

    llm = MistralLLM(_selected_llm["provider"], _selected_llm["model"])
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Group tests by requirement_id so related cases share one describe() ──
    groups: dict[str, list] = {}
    for t in tests:
        req_id = t.get("requirement_id") or "UNGROUPED"
        groups.setdefault(req_id, []).append(t)

    count = 0
    errors: list[str] = []
    for group_idx, (req_id, group_tests) in enumerate(groups.items()):
        try:
            safe_req = re.sub(r"[^\w\s-]", "", req_id).strip().replace(" ", "_")[:40]
            # Derive a human-readable describe label from the first test name in the group
            first_name = group_tests[0]["test_name"]
            group_label = re.sub(r"^[\d_]+", "", first_name).strip().replace("_", " ")
            # Trim to a concise feature label (≤ 60 chars)
            group_label = re.sub(r"\s+", " ", group_label)[:60].strip() + " Tests"

            if len(group_tests) == 1:
                # Single test — still generate with multi-block prompt via generate_playwright_script
                script = generate_playwright_script(group_tests[0], llm)
            else:
                # Multiple tests for same requirement — merge into one describe file
                script = generate_grouped_script(group_label, group_tests, llm)

            filename = f"{group_idx + 1:03d}_{safe_req}.spec.js"
            (SCRIPTS_DIR / filename).write_text(script, encoding="utf-8")
            count += 1
            logger.info(f"[SCRIPT] Generated: {filename} ({len(group_tests)} test(s))")
        except Exception as exc:  # noqa: BLE001
            failed_names = [t["test_name"] for t in group_tests]
            errors.extend(failed_names)
            logger.error(f"[SCRIPT ERROR] group={req_id}: {exc}", exc_info=True)

    return {"message": f"{count} script(s) generated", "count": count, "errors": errors}


@app.get("/download-scripts")
def download_scripts_endpoint() -> FileResponse:
    """Zip all generated Playwright scripts and return the archive."""
    scripts = sorted(SCRIPTS_DIR.glob("*.spec.js")) if SCRIPTS_DIR.exists() else []
    if not scripts:
        raise HTTPException(
            status_code=404,
            detail="No scripts found. Click 'Generate Playwright Scripts' first.",
        )

    zip_path = ROOT / "data" / "playwright_scripts.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in scripts:
            zf.write(f, f.name)

    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename="playwright_scripts.zip",
    )


def _derive_script_label(script_name: str, script_content: str) -> str:
    """Build a user-friendly label from the first test title in the script."""
    match = re.search(r"test\s*\(\s*['\"]([^'\"]+)['\"]", script_content)
    if match:
        return match.group(1).strip()
    return Path(script_name).stem.replace("_", " ")


@app.get("/scripts")
def list_scripts() -> dict:
    """Return generated Playwright scripts for in-app code viewer."""
    scripts = sorted(SCRIPTS_DIR.glob("*.spec.js")) if SCRIPTS_DIR.exists() else []
    if not scripts:
        return {"scripts": []}

    items = []
    for script_path in scripts:
        content = script_path.read_text(encoding="utf-8")
        items.append(
            {
                "name": script_path.name,
                "label": _derive_script_label(script_path.name, content),
                "language": "javascript",
                "content": content,
                "size": script_path.stat().st_size,
                "mime": mimetypes.guess_type(script_path.name)[0] or "text/plain",
            }
        )

    return {"scripts": items}


@app.get("/results")
def get_results() -> dict:
    if not OUTPUT_FILE.exists():
        return {"test_cases": []}
    try:
        import openpyxl  # noqa: PLC0415
        wb = openpyxl.load_workbook(OUTPUT_FILE)
        ws = wb.active
        headers = [cell.value for cell in next(ws.iter_rows(max_row=1))]
        rows = [
            dict(zip(headers, row))
            for row in ws.iter_rows(min_row=2, values_only=True)
        ]
        return {"test_cases": rows}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/download")
def download_excel() -> FileResponse:
    if not OUTPUT_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="No output file found. Run the pipeline first.",
        )
    return FileResponse(
        str(OUTPUT_FILE),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="generated_tests.xlsx",
    )


# ── Serve React SPA in production ─────────────────────────────────────────────
if FRONTEND_BUILD.exists():
    _assets = FRONTEND_BUILD / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="static-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:  # noqa: ARG001
        return FileResponse(str(FRONTEND_BUILD / "index.html"))
else:
    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"message": "Backend running. Start the frontend with: cd frontend && npm run dev"}


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True, app_dir=str(Path(__file__).parent))
