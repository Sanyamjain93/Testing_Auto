import pandas as pd


def write_excel(
    test_cases: list[dict],
    output_path: str,
    input_type: str = "doc",
    chunks_by_req_id: dict | None = None,
):
    """Write test cases to Excel.

    When *input_type* is ``"excel"`` and *chunks_by_req_id* is provided the
    output mirrors the source requirement columns and collapses all steps into
    two cells (Test Steps / Expected Results) so the result is one row per
    test case.

    Otherwise the legacy flat format (one row per step) is used.
    """
    if input_type == "excel" and chunks_by_req_id:
        _write_excel_format(test_cases, output_path, chunks_by_req_id)
    else:
        _write_doc_format(test_cases, output_path)


# ── Legacy flat format (one row per step) ─────────────────────────────────────

def _write_doc_format(test_cases: list[dict], output_path: str) -> None:
    rows = []
    for tc in test_cases:
        req_id = tc.get("requirement_id", "")
        req_text = tc.get("requirement_text", "")
        for step in tc.get("steps", []):
            rows.append({
                "Requirement ID": req_id,
                "Requirement Text": req_text,
                "Test Name": tc.get("test_name", ""),
                "Test Description": tc.get("test_description", ""),
                "Test Type": tc.get("test_type", "positive"),
                "Step Name": step.get("step_name", ""),
                "Action": step.get("action", ""),
                "Expected Result": step.get("expected_result", ""),
                "Quality Score": tc.get("quality_score", ""),
                "Quality Verdict": tc.get("quality_verdict", ""),
                "Quality Flags": tc.get("quality_flags", ""),
            })
    pd.DataFrame(rows).to_excel(output_path, index=False)


# ── Excel-sourced format (one row per test case, source columns preserved) ────

def _write_excel_format(
    test_cases: list[dict],
    output_path: str,
    chunks_by_req_id: dict,
) -> None:
    rows = []
    for tc in test_cases:
        req_id = tc.get("requirement_id", "")
        chunk = chunks_by_req_id.get(req_id, {})

        steps = tc.get("steps", [])
        test_steps_text = "\n".join(
            f"{s.get('step_name', f'Step {i+1}')}: {s.get('action', '')}"
            for i, s in enumerate(steps)
        )
        expected_results_text = "\n".join(
            f"{s.get('step_name', f'Step {i+1}')}: {s.get('expected_result', '')}"
            for i, s in enumerate(steps)
        )

        rows.append({
            "Sr No.": chunk.get("requirement_id", req_id),
            "Functionality": chunk.get("functionality", ""),
            "Area": chunk.get("area", ""),
            "Pre-Conditions": chunk.get("preconditions", ""),
            "Test Scenarios": chunk.get("test_scenarios", ""),
            "Description": chunk.get("description", ""),
            "Test Steps": test_steps_text,
            "Expected Results": expected_results_text,
        })

    pd.DataFrame(rows).to_excel(output_path, index=False)