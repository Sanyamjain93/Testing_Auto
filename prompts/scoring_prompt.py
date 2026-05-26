BATCH_SCORING_PROMPT_TEMPLATE = """
You are a senior QA reviewer evaluating the quality of multiple generated test cases.
Your ONLY task is to output a **valid JSON array** — one entry per test case — in this exact schema:

[
  {{
    "index": <integer, same as the index provided>,
    "score": <integer 1-10>,
    "verdict": "<PASS | REVIEW | FAIL>",
    "flags": ["<issue 1>", "<issue 2>", ...]
  }},
  ...
]

===== SCORING RULES =====

Score ranges:
- 8-10 → PASS   : High quality, minimal issues
- 5-7  → REVIEW : Acceptable but needs improvement
- 1-4  → FAIL   : Poor quality, major issues

Evaluate each test case on:
1. COMPLETENESS (all steps fully described, every step has an expected result)
2. CLARITY (actions unambiguous and detailed, expected result measurable/observable)
3. COVERAGE (adequately covers the requirement)
4. STRUCTURE (step names correctly numbered, style rules followed)
5. SPECIFICITY (not too generic, references actual system behavior)
6. SCENARIO CORRECTNESS (test_type matches the actual content):
   - "positive" tests must show a successful flow with no error assertions.
   - "negative" tests MUST contain a step that validates an error message or system rejection.
   - "edge" tests MUST reference a boundary value, limit, or unusual input.

FLAGS TO DETECT:
- "Vague expected result in Step X"
- "Action in Step X lacks preconditions or data setup"
- "Test case is too generic"
- "Missing steps for error/negative scenario"
- "Step numbering is incorrect"
- "Test name and description do not match"
- "Only one step — insufficient coverage"
- "test_type is 'negative' but no error validation step found"
- "test_type is 'edge' but no boundary/limit value used"
- "test_type is missing or invalid"

===== TEST CASES TO EVALUATE =====
{test_cases_block}

===== FINAL INSTRUCTIONS =====
- Return ONLY a valid JSON array, no markdown, no extra text.
- Output exactly {count} entries, one per test case, preserving the index values.
- The "flags" array must be empty ([]) if there are no issues.
"""
