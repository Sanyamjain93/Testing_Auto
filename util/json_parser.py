import json
from logger import get_logger

logger = get_logger("test_automation.json_parser")


def safe_parse(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        return {"error": "Invalid JSON", "raw": text}


def validate_and_filter_tests(
    tests: list,
    expected_requirement_id: str,
    expected_requirement_text: str,
) -> list:
    """
    Validate each test case for required traceability fields.

    Rules (any violation → test case is skipped with a logged warning):
    - requirement_id must be present and non-empty.
    - requirement_text must be present and non-empty.
    - requirement_id must exactly match *expected_requirement_id*.

    If the LLM omitted the fields but the structure is otherwise valid,
    this function backfills them from the input chunk so no test cases
    are silently lost, but still logs a warning.

    Returns the filtered (and possibly backfilled) list.
    """
    valid: list = []
    for i, test in enumerate(tests):
        req_id = test.get("requirement_id", "")
        req_text = test.get("requirement_text", "")

        # ── Backfill missing fields before hard rejection ──────────────────
        if not req_id:
            logger.warning(
                "[JSON] Test case %d is missing requirement_id — backfilling from chunk ('%s').",
                i,
                expected_requirement_id,
            )
            test["requirement_id"] = expected_requirement_id
            req_id = expected_requirement_id

        if not req_text:
            logger.warning(
                "[JSON] Test case %d is missing requirement_text — backfilling from chunk.",
                i,
            )
            test["requirement_text"] = expected_requirement_text
            req_text = expected_requirement_text

        # ── Hard reject: requirement_id mismatch ──────────────────────────
        if req_id != expected_requirement_id:
            logger.error(
                "[JSON] Test case %d has mismatched requirement_id: expected '%s', got '%s'. Skipping.",
                i,
                expected_requirement_id,
                req_id,
            )
            continue

        # ── Hard reject: empty requirement_text after backfill ────────────
        if not req_text.strip():
            logger.error(
                "[JSON] Test case %d has empty requirement_text even after backfill. Skipping.",
                i,
            )
            continue

        # ── Backfill / normalise test_type ────────────────────────────────
        raw_type = str(test.get("test_type", "")).strip().lower()
        if raw_type not in ("positive", "negative", "edge"):
            logger.warning(
                "[JSON] Test case %d has invalid/missing test_type '%s' — defaulting to 'positive'.",
                i,
                raw_type,
            )
            test["test_type"] = "positive"

        valid.append(test)

    return valid