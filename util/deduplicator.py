import numpy as np
from retrieval.embedder import Embedder
from config.config import EMBEDDING_MODEL, DEDUP_THRESHOLD
from logger import get_logger

logger = get_logger("test_automation.deduplicator")


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def deduplicate(test_cases: list[dict]) -> list[dict]:
    """
    Remove near-duplicate test cases using cosine similarity on their
    test_name + test_description embeddings.

    Two test cases are considered duplicates when their similarity >= DEDUP_THRESHOLD.
    The first occurrence is kept; subsequent near-duplicates are dropped.

    Returns the deduplicated list.
    """
    if len(test_cases) <= 1:
        return test_cases

    # Build a text fingerprint for each test case (name + description)
    fingerprints = [
        f"{tc.get('test_name', '')} {tc.get('test_description', '')}".strip()
        for tc in test_cases
    ]

    print(f"   🔢 Embedding {len(fingerprints)} test cases for deduplication...")
    embedder = Embedder(EMBEDDING_MODEL)
    vectors = embedder.embed(fingerprints)
    vectors = np.array(vectors, dtype=np.float32)

    kept_indices = []
    kept_vectors = []

    for i, vec in enumerate(vectors):
        is_duplicate = False
        for kv in kept_vectors:
            if _cosine_similarity(vec, kv) >= DEDUP_THRESHOLD:
                is_duplicate = True
                break
        if not is_duplicate:
            kept_indices.append(i)
            kept_vectors.append(vec)

    removed = len(test_cases) - len(kept_indices)
    print(f"   ✅ Deduplication complete: kept {len(kept_indices)}, removed {removed} duplicate(s).")
    return [test_cases[i] for i in kept_indices]
