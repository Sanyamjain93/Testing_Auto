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