import re
from typing import List, Dict

# Regex to find explicit requirement ID markers in documents.
# Matches patterns like:  "REQ ID: RMS-LOGIN-001"  or  "Req ID: FOO-BAR-002"
_REQ_ID_PATTERN = re.compile(r"REQ(?:UIREMENT)?\s*ID\s*:\s*([\w][\w\-]*)", re.IGNORECASE)

# Regex to detect numbered sub-requirements like 1.1, 1.2, 2.3, 1.1.1 etc.
# Requires the number to start at a word boundary (not mid-word).
_SUBREQ_NUM_PATTERN = re.compile(r"(?<!\w)(\d+\.\d+(?:\.\d+)*)\b")


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> List[str]:
    """Legacy plain-text chunker retained for backward compatibility."""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    chunks: List[str] = []
    i = 0
    L = len(cleaned)
    while i < L:
        end = min(i + chunk_size, L)
        chunks.append(cleaned[i:end])
        i = end - overlap if end < L else end
    return [c for c in chunks if len(c.strip()) > 20]


def _split_by_subreq_numbers(req_id: str, block_text: str) -> List[Dict]:
    """
    Split a requirement block by numbered sub-requirements (e.g. 1.1, 1.2, 2.3).
    Each numbered point becomes its own chunk with the suffix ``_<number>``
    appended to *req_id*.

    Returns an empty list when no numbered sub-requirements are found,
    so the caller can fall back to keeping the block as a single chunk.
    """
    matches = list(_SUBREQ_NUM_PATTERN.finditer(block_text))
    if not matches:
        return []

    parts: List[Dict] = []
    for i, match in enumerate(matches):
        subreq_num = match.group(1)
        text_start = match.end()
        text_end = matches[i + 1].start() if i + 1 < len(matches) else len(block_text)
        req_text = block_text[text_start:text_end].strip()
        if req_text:
            parts.append({
                "requirement_id": f"{req_id}_{subreq_num}",
                "requirement_text": req_text,
            })
    return parts


def chunk_requirements(
    text: str,
    chunk_size: int = 800,
    overlap: int = 200,
) -> List[Dict]:
    """
    Parse a requirements document and return a list of structured chunks:
        {"requirement_id": "...", "requirement_text": "..."}

    Strategy:
    1. Locate all "REQ ID: <id>" markers in the document.
    2. Treat the text between consecutive markers as one requirement block.
    3. Within each block, detect numbered sub-requirements (e.g. 1.1, 1.2).
       Each numbered point becomes its own chunk with the suffix ``_<number>``
       appended to the requirement_id (e.g. RMS-LOGIN-001_1.1).
    4. If a block has no numbered sub-requirements it is kept as a single chunk.
    5. If no REQ ID markers are found, fall back to plain chunking and
       assign auto-generated IDs (REQ-001, REQ-002, …).

    ``chunk_size`` and ``overlap`` are retained for backward-compatible
    call-sites but no longer drive internal splitting.
    """
    # Normalise whitespace while preserving structured formatting.
    lines = [" ".join(line.split()) for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)

    matches = list(_REQ_ID_PATTERN.finditer(cleaned))

    # ── Fallback: no explicit REQ IDs ─────────────────────────────────────
    if not matches:
        plain_chunks = chunk_text(cleaned, chunk_size, overlap)
        result: List[Dict] = []
        for idx, chunk_text_val in enumerate(plain_chunks, start=1):
            result.append({
                "requirement_id": f"REQ-{idx:03d}",
                "requirement_text": chunk_text_val,
            })
        return result

    # ── Build requirement blocks from markers ──────────────────────────────
    blocks: List[Dict] = []
    for match_idx, match in enumerate(matches):
        req_id = match.group(1).strip()
        block_start = match.end()
        block_end = matches[match_idx + 1].start() if match_idx + 1 < len(matches) else len(cleaned)
        block_text = cleaned[block_start:block_end].strip()

        if not block_text:
            continue

        subreq_parts = _split_by_subreq_numbers(req_id, block_text)
        if subreq_parts:
            blocks.extend(subreq_parts)
        else:
            # No numbered sub-requirements — keep the block as a single chunk.
            blocks.append({"requirement_id": req_id, "requirement_text": block_text})

    return [b for b in blocks if len(b["requirement_text"].strip()) > 20]