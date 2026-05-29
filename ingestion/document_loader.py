from PyPDF2 import PdfReader
from docx import Document
import pandas as pd
from pathlib import Path

# Expected columns for structured Excel requirement ingestion
EXCEL_REQ_COLUMNS = {"Functionality", "Area", "Pre-Conditions", "Test Scenarios", "Description"}


def load_document(path: Path) -> str:
    """Return raw text for non-Excel files. For Excel, flattens all cells (legacy/fallback)."""
    if path.suffix == ".pdf":
        reader = PdfReader(path)
        return "\n".join(p.extract_text() or "" for p in reader.pages)

    if path.suffix == ".docx":
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)

    if path.suffix == ".xlsx":
        df = pd.read_excel(path)
        return "\n".join(df.astype(str).values.flatten())

    if path.suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")

    raise ValueError(f"Unsupported file type: {path.suffix}")


def load_excel_requirements(path: Path) -> list[dict] | None:
    """
    Load an Excel requirements file and return a list of structured row dicts.

    Returns None if the file does not have the expected requirement columns,
    so the caller can fall back to plain text chunking.

    Each returned dict has:
        requirement_id  – from "Sr No." column (or auto-generated ROW-NNN)
        requirement_text – formatted multi-line string (for embedding / RAG)
        functionality   – raw Functionality cell
        area            – raw Area cell
        preconditions   – raw Pre-Conditions cell
        test_scenarios  – raw Test Scenarios cell
        description     – raw Description cell
    """
    df = pd.read_excel(path, dtype=str).fillna("")
    cols = {c.strip() for c in df.columns}

    # Require at least the core content columns
    if not EXCEL_REQ_COLUMNS.issubset(cols):
        return None  # caller should fall back to chunk-based flow

    rows = []
    for i, row in df.iterrows():
        sr_no = str(row.get("Sr No.", "")).strip()
        req_id = f"ROW-{i + 1:03d}" if not sr_no or sr_no.lower() == "nan" else sr_no

        functionality  = str(row.get("Functionality",  "")).strip()
        area           = str(row.get("Area",           "")).strip()
        preconditions  = str(row.get("Pre-Conditions", "")).strip()
        test_scenarios = str(row.get("Test Scenarios", "")).strip()
        description    = str(row.get("Description",    "")).strip()

        # Skip completely empty rows
        if not any([functionality, area, preconditions, test_scenarios, description]):
            continue

        req_text = (
            f"REQUIREMENT DETAILS:\n\n"
            f"Functionality: {functionality}\n"
            f"Area: {area}\n\n"
            f"Pre-Conditions:\n{preconditions}\n\n"
            f"Test Scenario:\n{test_scenarios}\n\n"
            f"Description:\n{description}"
        )

        rows.append({
            "requirement_id":  req_id,
            "requirement_text": req_text,
            "functionality":   functionality,
            "area":            area,
            "preconditions":   preconditions,
            "test_scenarios":  test_scenarios,
            "description":     description,
        })

    return rows if rows else None
