import json
import re
from prompts.scoring_prompt import BATCH_SCORING_PROMPT_TEMPLATE
from logger import get_logger

logger = get_logger("test_automation.scorer")

# Number of test cases sent to the LLM in a single scoring call.
# Tune this down if you still hit rate limits, or up to use fewer API calls.
BATCH_SIZE = 10


def _format_steps(steps: list[dict]) -> str:
    lines = []
    for step in steps:
        lines.append(f"  {step.get('step_name', '')}:")
        lines.append(f"    Action: {step.get('action', '')}")
        lines.append(f"    Expected Result: {step.get('expected_result', '')}")
    return "\n".join(lines)


def _escape_braces(text: str) -> str:
    """Escape literal { and } so .format() doesn't treat them as placeholders."""
    return text.replace("{", "{{").replace("}", "}}")


def _build_batch_block(batch: list[tuple[int, dict]]) -> str:
    """Format a list of (index, test_case) pairs into a readable block for the prompt."""
    parts = []
    for idx, tc in batch:
        steps_text = _format_steps(tc.get("steps", []))
        parts.append(
            f"--- Test Case Index {idx} ---\n"
            f"Test Name: {tc.get('test_name', '')}\n"
            f"Test Type: {tc.get('test_type', 'positive')}\n"
            f"Test Description: {tc.get('test_description', '')}\n"
            f"Steps:\n{steps_text}"
        )
    return "\n\n".join(parts)


def _score_batch(batch: list[tuple[int, dict]], llm) -> dict[int, dict]:
    """
    Send a batch of test cases to the LLM for scoring in one call.
    Returns a mapping of index → score result dict.
    """
    block = _escape_braces(_build_batch_block(batch))
    prompt = BATCH_SCORING_PROMPT_TEMPLATE.format(
        test_cases_block=block,
        count=len(batch),
    )

    try:
        raw = llm.generate(prompt)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        results = json.loads(raw)

        scored = {}
        for entry in results:
            i = int(entry["index"])
            scored[i] = {
                "quality_score": int(entry.get("score", 0)),
                "quality_verdict": str(entry.get("verdict", "UNKNOWN")),
                "quality_flags": "; ".join(entry.get("flags", [])),
            }
        return scored

    except Exception as exc:
        logger.warning(f"   ⚠️  Batch scoring failed: {exc}", exc_info=True)
        return {
            idx: {"quality_score": 0, "quality_verdict": "ERROR", "quality_flags": f"Scoring failed: {exc}"}
            for idx, _ in batch
        }


def score_all(test_cases: list[dict], llm, batch_size: int = BATCH_SIZE) -> None:
    """
    Score all test cases in-place using batched LLM calls.
    Adds quality_score, quality_verdict, quality_flags to each test case dict.
    """
    total = len(test_cases)
    indexed = list(enumerate(test_cases))

    for start in range(0, total, batch_size):
        batch = indexed[start: start + batch_size]
        end = start + len(batch)
        print(f"   🔍 Scoring test cases {start + 1}–{end} of {total} (1 API call for {len(batch)} cases)...")
        scored = _score_batch(batch, llm)
        for idx, tc in batch:
            tc.update(scored.get(idx, {
                "quality_score": 0,
                "quality_verdict": "ERROR",
                "quality_flags": "No result returned for this index",
            }))

    passed = sum(1 for tc in test_cases if tc.get("quality_verdict") == "PASS")
    review = sum(1 for tc in test_cases if tc.get("quality_verdict") == "REVIEW")
    failed = sum(1 for tc in test_cases if tc.get("quality_verdict") == "FAIL")
    print(f"\n   📊 Quality Summary → PASS: {passed} | REVIEW: {review} | FAIL: {failed} | Total: {total}")

