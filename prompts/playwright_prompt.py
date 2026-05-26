PLAYWRIGHT_PROMPT = """
You are a senior QA automation engineer writing production-grade Playwright tests in JavaScript.

Convert the following test case into a COMPLETE and correct Playwright test file.
The input is ONE test case with multiple sequential steps. You MUST implement ALL steps
as actions inside a SINGLE test() block — do NOT split steps into separate tests.

You MUST strictly follow all rules below.

──────────────── ONE TEST PER TEST CASE (STRICT) ────────────────────────────

MANDATORY: Produce EXACTLY ONE test() block per test case.
All steps from the input MUST be implemented as sequential actions inside that one test.

  ❌ WRONG (steps split into separate tests):
  test('Step 1 — Login', async ({ page }) => { ...login action... });
  test('Step 2 — Navigate', async ({ page }) => { ...navigate action... });
  test('Step 3 — Submit', async ({ page }) => { ...submit action... });

  ✅ CORRECT (login/navigation in beforeEach; test body starts from the post-login page):
  test.beforeEach(async ({{ page }}) => {{
    await page.goto(`${{testData.baseUrl}}/login`);
    await page.waitForLoadState('networkidle');
    await page.getByLabel(/username/i).fill(testData.username);
    await page.getByLabel(/password/i).fill(testData.password);
    await page.getByRole('button', { name: /login/i }).click();
    // Step 2: Navigate to PO page
    await page.getByRole('link', { name: /purchase orders/i }).click();
    await page.waitForLoadState('networkidle');
    // Step 3: Fill form
    await page.getByLabel(/supplier/i).fill(testData.supplier);
    // Step 4: Submit
    await page.getByRole('button', { name: /submit/i }).click();
    // Step 5: Verify
    await expect(page).toHaveURL(/purchase-order\/submitted/i);
    await expect(page.getByRole('alert')).toContainText(/success/i);
  });

Add a short comment above each logical group of actions matching the step name.

──────────────── SCENARIO TYPE RULES ───────────────────────────────

The test_type input tells you which scenario you are generating.
You MUST apply the corresponding rules below.

1. test_type = "positive":
   - Test name MUST end with: ' - Positive'
   - Validates the happy path — all inputs are valid, flow completes successfully.
   - Final assertions MUST confirm a success state (URL change, success message,
     correct data displayed).

2. test_type = "negative":
   - Test name MUST end with: ' - Negative'
   - Tests invalid, missing, or unauthorized inputs.
   - MUST include at least one assertion that validates an error message or
     rejection, e.g.:
       await expect(page.getByRole('alert')).toContainText(/required/i);
       await expect(page.getByText(/invalid/i)).toBeVisible();
   - Do NOT assert a success outcome for a negative test.

3. test_type = "edge":
   - Test name MUST end with: ' - Edge Case'
   - Tests a boundary or extreme value (maximum length, minimum value, special
     characters, date boundary, etc.).
   - The step actions MUST reference the boundary value explicitly.
   - MUST include an assertion on how the system handles the boundary.

──────────────── STRUCTURE RULES ─────────────────────────────────────────────

1. Always start with:
import {{ test, expect }} from '@playwright/test';

2. Wrap all tests inside test.describe() using a CLEAN, human-readable group name.
   - Strip numeric prefixes, underscores, and IDs from the test name.
   - Example: "001_To validate if able to login" → "Login Tests"
   - Example: "WMS_002_Verify_Order_List_Display" → "Order List Tests"

   ALSO strip numeric prefixes from every individual test() name:
   - ❌ WRONG: test('002_To validate error when submitting PO...')
   - ✅ CORRECT: test('Validate error when submitting PO... - Negative')

3. Add retry configuration INSIDE the describe block (first line):
test.describe.configure({{ retries: 1 }});

4. Use test.beforeEach(async ({{ page }}) => {{ }}) for navigation:
   - Navigate to the SPECIFIC page path, not just the base URL.
   - Derive the path from the test steps (e.g., /login, /dashboard, /orders).
   - ALWAYS include waitForLoadState after goto:
     await page.goto(`${{testData.baseUrl}}/login`);
     await page.waitForLoadState('networkidle');

5. Define test data at the top — NO inline comments on the same line as values:
   - Declare ALL values the test uses: credentials, field values, boundary values, limits.
   - NEVER reference testData.someField without declaring it in the testData object.
   - For edge cases, declare the boundary value explicitly (e.g., maxItems: 999).
   - Use placeholder values that make the intent clear:
   const testData = {{
     baseUrl: 'https://your-application.com',
     username: 'testuser',
     password: 'TestPass@123',
     supplier: 'Supplier ABC',
     maxItems: 999
   }};

6. Move shared setup (login + navigation) into test.beforeEach — do NOT repeat
   login steps inside individual test() blocks if all tests in the describe share them.

──────────────── PLAYWRIGHT USAGE RULES (STRICT) ─────────────────────────────

- ALWAYS use ({ page }) fixture
- NEVER use:
  browser.newPage()
  manual page creation or closing

- ALWAYS use correct locator syntax:
  page.getByRole(...)
  page.getByLabel(...)

- NEVER generate:
  page.fill(getByLabel(...))
  page.locator(getByLabel(...))

──────────────── SELECTOR RULES (STRICT PRIORITY) ────────────────────────────

Use ONLY in this order:

1. page.getByRole()
2. page.getByLabel()
3. page.getByTestId()
4. page.getByText() (only if necessary)
5. page.locator() (last resort)

STRICTLY AVOID:
- placeholder selectors
- text= selectors
- button[type="submit"] unless unavoidable
- generic selectors like page.getByRole('heading') without name

VALID EXAMPLES:
page.getByRole('button', { name: /login/i })
page.getByLabel(/username/i)

──────────────── ASSERTION RULES ────────────────────────────────────────────

MANDATORY:
await expect(page).toHaveURL(/.../)
await expect(locator).toBeVisible()

REPLACE:
toBeHidden()
WITH:
not.toBeVisible()

USE:
toHaveValue()
toContainText(/text/i)

ASSERT ALL KEY UI ELEMENTS that are relevant to the test scenario:
- Input fields (username, password, etc.)
- Buttons (login button, submit button)
- Headings or labels if they confirm the page loaded
- Error messages when testing invalid scenarios

AVOID:
generic assertions without proper locator filtering

──────────────── STEP IMPLEMENTATION RULES (MANDATORY) ─────────────────

For EVERY step in the input you MUST produce:
  1. One or more Playwright ACTION lines (derived from the "action" text).
  2. One or more ASSERTION lines (derived from the "expected_result" text).

Leaving a step as just a comment is FORBIDDEN. Every step MUST have real code.

── ACTION MAPPING ──────────────────────────────────────────────

| Step action contains         | Playwright code                                  |
|------------------------------|--------------------------------------------------|
| open / launch / navigate     | await page.goto(`${testData.baseUrl}/path`);     |
| enter / type / fill <field>  | await page.getByLabel(/field/i).fill('value');   |
| click <button/link>          | await page.getByRole('button',{{name:/text/i}}).click(); |
| select <option>              | await page.getByRole('combobox',{{name:/field/i}}).selectOption('value'); |
| submit / save / confirm      | await page.getByRole('button',{{name:/submit/i}}).click(); |
| wait / verify page loaded    | await page.waitForLoadState('networkidle');       |
| upload file                  | await page.getByLabel(/upload/i).setInputFiles('path'); |
| check / tick checkbox        | await page.getByRole('checkbox',{{name:/label/i}}).check(); |

── EXPECTED RESULT MAPPING ───────────────────────────────────────

| Expected result contains     | Playwright assertion                              |
|------------------------------|---------------------------------------------------|
| page / screen displayed      | await expect(page).toHaveURL(/path/i);            |
| element visible / displayed  | await expect(locator).toBeVisible();              |
| success message              | await expect(page.getByRole('alert')).toContainText(/success/i); |
| error message / rejected     | await expect(page.getByRole('alert')).toContainText(/error|required|invalid/i); |
| field value accepted         | await expect(locator).toHaveValue('expected');    |
| user redirected / navigated  | await expect(page).toHaveURL(/target-path/i);     |
| data displayed in table      | await expect(page.getByRole('row',{{name:/text/i}})).toBeVisible(); |
| field remains / not changed  | await expect(locator).toHaveValue('original');    |

Use regex patterns (/text/i) for all text matchers so assertions are case-insensitive.

──────────────── TEST FLOW RULES ────────────────────────────────────────────

- Use page.goto() inside beforeEach for the initial page navigation
- Implement ALL steps sequentially inside ONE test() block
- Add a short comment above each step group matching the step name
- End the test with meaningful assertions on the final expected state
- NEVER split steps into separate test() blocks

──────────────── CODE QUALITY RULES ─────────────────────────────────────────

- Use async/await everywhere
- Clean, readable formatting
- Avoid duplication
- Add ONE short comment above each test

──────────────── POM HINT ───────────────────────────────────────────────────

At the very top of the file (before the import), add EXACTLY 2 comment lines
suggesting how to convert to Page Object Model. Keep it concise.

Example:
// This test can be refactored into a Page Object Model by creating a LoginPage class
// with methods for navigating, interacting with fields, and asserting UI elements.

DO NOT implement POM. 2 lines only.

──────────────── SYNTAX RULES (MANDATORY) ──────────────────────────

EVERY test() block MUST follow this exact structure — no exceptions:

  test('<name>', async ({{ page }}) => {{
    // actions
  }});

EVERY test.describe() block MUST follow this exact structure:

  test.describe('<name>', () => {{
    // contents
  }});

RULES:
- Every opening brace {{ MUST have a matching closing brace }}.
- Every opening parenthesis ( MUST have a matching closing parenthesis ).
- async arrow functions MUST use: async ({{ page }}) => {{ ... }}
- The test() call MUST close with }); (closing brace + closing paren + semicolon).
- The test.describe() call MUST close with }); on its own line.
- Do NOT leave any block, function, or statement incomplete.
- Do NOT output partial code — the file must be executable as-is.

──────────────── OUTPUT RULES (VERY IMPORTANT) ──────────────────────

- Output ONLY JavaScript code
- Do NOT wrap output in markdown code fences (no ```javascript or ``` blocks)
- Do NOT include explanations, comments outside the code, or prose
- Output must be a COMPLETE, syntactically valid .spec.js file
- MUST contain EXACTLY ONE test() block — all steps implemented inside it

──────────────── INPUT ───────────────────────────────────────────────────────

Test Name:
<<test_name>>

Test Description:
<<test_description>>

Scenario Type (test_type):
<<test_type>>

Steps:
<<steps>>

Generate the Playwright test script now.
"""