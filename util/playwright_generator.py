import re

from prompts.playwright_prompt import PLAYWRIGHT_PROMPT


def generate_playwright_script(test: dict, llm) -> str:
    """Generate a Playwright JS test file for a single test case.

    All steps are implemented as sequential actions inside ONE test() block.
    The raw LLM output is post-processed by _clean_script() to strip markdown
    fences and balance any unclosed braces before the file is written.

    Args:
        test: dict with keys test_name, test_description, steps (list of dicts)
        llm:  any object with a .generate(prompt: str) -> str method

    Returns:
        Cleaned, syntactically valid JavaScript source code as a string.
    """
    steps_text = "\n".join(
        f"{i + 1}. {step['action']} → Expected: {step['expected_result']}"
        for i, step in enumerate(test.get("steps", []))
    )

    prompt = PLAYWRIGHT_PROMPT
    prompt = prompt.replace("<<test_name>>", test["test_name"])
    prompt = prompt.replace("<<test_description>>", test.get("test_description", ""))
    prompt = prompt.replace("<<test_type>>", test.get("test_type", "positive"))
    prompt = prompt.replace("<<steps>>", steps_text)

    raw = llm.generate(prompt)
    return _clean_script(raw)


def generate_grouped_script(group_name: str, tests: list[dict], llm) -> str:
    """Generate a single Playwright JS file containing one test() block per test case.

    Used when multiple related test cases share the same requirement ID.  Each
    test case is sent to the LLM individually so it can produce its own test()
    block; the results are extracted, syntax-cleaned, and assembled into one
    test.describe() file.

    Args:
        group_name: Human-readable describe() label (e.g. "Purchase Order Tests")
        tests:      List of test dicts (test_name, test_description, steps)
        llm:        Any object with a .generate(prompt: str) -> str method

    Returns:
        Complete, syntactically valid .spec.js source as a string.
    """
    # ── Phase 1: run LLM for each test, harvest testData fields + beforeEach ──
    # baseUrl is always the caller's default; other fields come from LLM outputs.
    merged_fields: dict[str, str] = {"baseUrl": "'https://your-application.com'"}
    all_before_each_bodies: list[str | None] = []  # collect all; pick best after loop
    rendered_tests: list[tuple[str, list[str]]] = []

    for test in tests:
        steps_text = "\n".join(
            f"{i + 1}. {step['action']} → Expected: {step['expected_result']}"
            for i, step in enumerate(test.get("steps", []))
        )
        prompt = PLAYWRIGHT_PROMPT
        prompt = prompt.replace("<<test_name>>", test["test_name"])
        prompt = prompt.replace("<<test_description>>", test.get("test_description", ""))
        prompt = prompt.replace("<<test_type>>", test.get("test_type", "positive"))
        prompt = prompt.replace("<<steps>>", steps_text)

        raw = llm.generate(prompt)
        cleaned = _clean_script(raw)

        # Merge testData fields from this LLM output (later tests may add new keys)
        merged_fields.update(_extract_test_data_fields(cleaned))

        # Collect beforeEach body for later scoring; all are kept, best wins
        all_before_each_bodies.append(_extract_before_each_body(cleaned))

        test_blocks = _extract_test_blocks(cleaned)
        rendered_tests.append((test["test_name"], test_blocks))

    # ── Phase 2: assemble the final file ──
    # Pick the most complete beforeEach seen across all LLM outputs
    shared_before_each_body = _select_best_before_each(all_before_each_bodies)

    # Build testData block lines, stripping the trailing comma from the last entry
    td_lines = [f"  {k}: {v}," for k, v in merged_fields.items()]
    if td_lines:
        td_lines[-1] = td_lines[-1].rstrip(",")

    # Build beforeEach block from harvested body, or fall back to minimal navigation
    if shared_before_each_body:
        before_each_inner = "\n".join(
            f"    {line.strip()}" if line.strip() else ""
            for line in shared_before_each_body.splitlines()
        )
        before_each_block = (
            "  test.beforeEach(async ({ page }) => {\n"
            + before_each_inner + "\n"
            + "  });"
        )
    else:
        before_each_block = (
            "  test.beforeEach(async ({ page }) => {\n"
            "    await page.goto(`${testData.baseUrl}/`);\n"
            "    await page.waitForLoadState('networkidle');\n"
            "  });"
        )

    lines = [
        "// Auto-generated — each test() covers one logical scenario.",
        "// Refactor into a Page Object Model by extracting shared actions into page classes.",
        "",
        "import { test, expect } from '@playwright/test';",
        "",
        "const testData = {",
        *td_lines,
        "};",
        "",
        f"test.describe('{group_name}', () => {{",
        "  test.describe.configure({ retries: 1 });",
        "",
        before_each_block,
        "",
    ]

    for test_name, test_blocks in rendered_tests:
        if test_blocks:
            lines.append(f"  // ── {test_name} ──")
            for block in test_blocks:
                indented = "\n".join("  " + l for l in block.splitlines())
                lines.append(indented)
                lines.append("")
        else:
            # Fallback: emit a valid placeholder so the file stays runnable
            safe_name = test_name.replace("'", "\\'")
            lines.append(f"  // ── {test_name} ──")
            lines.append(f"  test('{safe_name}', async ({{ page }}) => {{")
            lines.append("    // TODO: LLM output could not be parsed — implement steps manually")
            lines.append("  });")
            lines.append("")

    lines.append("});")  # close outer describe
    return "\n".join(lines)


# ──────────────────────────────── helpers ─────────────────────────────────────

def _clean_script(js: str) -> str:
    """Strip markdown fences and balance unclosed braces in LLM-generated JS.

    Steps:
    1. Remove any ``` code-fence wrapping the output.
    2. Count net open braces (ignoring content inside strings and comments).
    3. Append the correct number of closing '});' lines so the file is valid.
    """
    # 1. Strip markdown fences
    js = js.strip()
    js = re.sub(r'^```(?:javascript|js|typescript|ts)?\s*\n?', '', js, flags=re.IGNORECASE)
    js = re.sub(r'\n?```\s*$', '', js)
    js = js.strip()

    # 2. Balance braces
    depth = _brace_depth(js)
    if depth > 0:
        # Append closing tokens from innermost to outermost.
        # Each unclosed block gets '});' (closes the arrow-function body and
        # the surrounding call parenthesis).
        for i in range(depth, 0, -1):
            indent = "  " * (i - 1)
            js += f"\n{indent}" + ("});" if i > 1 else "});")

    return js


def _brace_depth(js: str) -> int:
    """Return the number of unclosed '{' braces in JS source.

    Skips brace characters that appear inside:
    - Single-quoted strings  'text'
    - Double-quoted strings  "text"
    - Template literals      `text`
    - Line comments          // ...
    - Block comments         /* ... */
    """
    depth = 0
    in_string: str | None = None  # current string delimiter, or None
    i = 0
    n = len(js)

    while i < n:
        c = js[i]

        if in_string:
            if c == "\\":          # escaped character — skip next
                i += 2
                continue
            if c == in_string:     # end of string
                in_string = None
        else:
            if c == "/" and js[i:i + 2] == "//":   # line comment
                while i < n and js[i] != "\n":
                    i += 1
                continue
            if c == "/" and js[i:i + 2] == "/*":   # block comment
                end = js.find("*/", i + 2)
                i = end + 2 if end != -1 else n
                continue
            if c in ('"', "'", "`"):  # start of string / template literal
                in_string = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth = max(0, depth - 1)

        i += 1

    return depth


def _extract_test_blocks(js_source: str) -> list[str]:
    """Return a list of complete test('...', ...) { ... }); blocks from JS source.

    Correctly skips the `({ page })` parameter destructuring and locates the
    test *body* opening brace (the one after `=>`), then walks balanced braces
    to find the matching close.
    """
    blocks: list[str] = []
    for m in re.finditer(r"\btest(?:\.only|\.skip)?\s*\(", js_source):
        start = m.start()

        # Find the arrow `=>` that introduces the async callback body.
        # This skips past `async ({ page })` so we don't mistake the
        # destructuring `{` for the opening brace of the test body.
        arrow_pos = js_source.find("=>", m.end())
        if arrow_pos == -1:
            continue  # no arrow function found — skip malformed block

        # Find the opening brace of the test body (must come after `=>`)
        brace_pos = js_source.find("{", arrow_pos + 2)
        if brace_pos == -1:
            continue  # test body is empty / missing — skip

        # Walk balanced braces to find the matching closing brace
        depth = 0
        end = brace_pos
        for i in range(brace_pos, len(js_source)):
            if js_source[i] == "{":
                depth += 1
            elif js_source[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break

        # Capture trailing `);` so the block is a complete statement
        tail_end = end + 1
        while tail_end < len(js_source) and js_source[tail_end] in (";", ")", " "):
            tail_end += 1

        block = js_source[start:tail_end].strip()

        # Only keep blocks that have real implementation (not just whitespace/comments)
        body = js_source[brace_pos + 1:end].strip()
        if body:
            blocks.append(block)

    return blocks


def _select_best_before_each(bodies: list[str | None]) -> str | None:
    """Choose the most complete beforeEach body from a list of candidates.

    Scoring heuristic (higher is better):
    - +1 per line of content (longer bodies carry more setup)
    - +50 bonus if the body contains authentication actions (fill / login /
      username / password keywords), so a body that actually logs in always
      wins over a body that merely navigates.

    Returns None when no valid (non-empty) body is found.
    """
    valid = [b for b in bodies if b]
    if not valid:
        return None

    def _score(body: str) -> int:
        score = len(body.splitlines())
        if re.search(r"\b(fill|login|username|password)\b", body, re.IGNORECASE):
            score += 50
        return score

    return max(valid, key=_score)


def _extract_test_data_fields(js_source: str) -> dict[str, str]:
    """Extract key→raw-value pairs from the testData object in JS source.

    Returns a dict mapping field names to their raw JS value strings, e.g.
    {"username": "'testuser'", "maxItems": "999"}.
    ``baseUrl`` is intentionally skipped so the caller's default is preserved.
    Only single-line values (strings, numbers, booleans) are supported.
    """
    match = re.search(r"const\s+testData\s*=\s*\{([^}]+)\}", js_source, re.DOTALL)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for field_match in re.finditer(r"(\w+)\s*:\s*([^,\n]+)", match.group(1)):
        key = field_match.group(1).strip()
        if key == "baseUrl":
            continue
        # Strip trailing inline comments and punctuation
        value = re.sub(r"\s*//.*$", "", field_match.group(2)).strip().rstrip(",")
        if value:
            fields[key] = value
    return fields


def _extract_before_each_body(js_source: str) -> str | None:
    """Return the body text (excluding outer braces) of test.beforeEach, or None.

    Walks balanced braces so nested blocks are captured correctly.
    """
    match = re.search(r"test\.beforeEach\s*\(", js_source)
    if not match:
        return None
    arrow_pos = js_source.find("=>", match.end())
    if arrow_pos == -1:
        return None
    brace_pos = js_source.find("{", arrow_pos + 2)
    if brace_pos == -1:
        return None
    depth = 0
    end = brace_pos
    for i in range(brace_pos, len(js_source)):
        if js_source[i] == "{":
            depth += 1
        elif js_source[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = js_source[brace_pos + 1:end].strip()
    return body if body else None
