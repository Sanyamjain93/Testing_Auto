import faiss
import numpy as np
import json
from pathlib import Path
from typing import Dict, List, Tuple


def _normalize(vectors: np.ndarray) -> np.ndarray:
    """L2-normalise rows so that inner-product == cosine similarity."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (vectors / norms).astype(np.float32)


class VectorStore:
    def __init__(self, dim: int):
        # IndexFlatIP with normalised vectors gives exact cosine similarity scores in [0, 1].
        self.index = faiss.IndexFlatIP(dim)
        self._metadata: List[Dict] = []

    def add(self, vectors, metadata: List[Dict] | None = None) -> None:
        arr = _normalize(np.array(vectors, dtype=np.float32))
        self.index.add(arr)
        if metadata:
            self._metadata.extend(metadata)

    def search(self, query_vec, k: int) -> Tuple[List[int], List[float]]:
        """Return (indices, cosine_scores) for the top-k nearest neighbours."""
        query = _normalize(np.array(query_vec, dtype=np.float32).reshape(1, -1))
        scores, indices = self.index.search(query, k)
        return indices[0].tolist(), scores[0].tolist()

    def save(self, index_path: str, metadata_path: str) -> None:
        """Persist FAISS index and chunk metadata to disk."""
        Path(index_path).parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, index_path)
        Path(metadata_path).write_text(
            json.dumps(self._metadata, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, index_path: str, metadata_path: str) -> "VectorStore":
        """Load a previously saved FAISS index and its metadata."""
        index = faiss.read_index(index_path)
        store = cls(index.d)
        store.index = index
        store._metadata = json.loads(
            Path(metadata_path).read_text(encoding="utf-8")
        )
        return store

    @property
    def metadata(self) -> List[Dict]:
        return self._metadata
