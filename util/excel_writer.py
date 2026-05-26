import pandas as pd

def write_excel(test_cases: list[dict], output_path: str):
    rows = []

    for tc in test_cases:
        req_id = tc.get("requirement_id", "")
        req_text = tc.get("requirement_text", "")

        for step in tc.get("steps", []):
            rows.append({
                "Requirement ID": req_id,
                "Requirement Text": req_text,
                "Test Name": tc["test_name"],
                "Test Description": tc["test_description"],
                "Test Type": tc.get("test_type", "positive"),
                "Step Name": step["step_name"],
                "Action": step["action"],
                "Expected Result": step["expected_result"],
                "Quality Score": tc.get("quality_score", ""),
                "Quality Verdict": tc.get("quality_verdict", ""),
                "Quality Flags": tc.get("quality_flags", ""),
            })

    pd.DataFrame(rows).to_excel(output_path, index=False)