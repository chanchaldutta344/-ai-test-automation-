"""Main FastAPI application for test automation backend.

This module exposes endpoints for:
- POST /api/generate-tests: AI-powered test case generation from acceptance criteria
- POST /api/execute-tests: AI-simulated test execution
- POST /api/execute-tests-http: Real HTTP testing against a live URL
- POST /api/execute-tests-browser: Real browser testing with Playwright against a live URL
"""

from __future__ import annotations

import json
import os
import traceback
from typing import Any, Dict, List, Optional

import httpx

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from google import genai


load_dotenv()


app = FastAPI()

# Allow all origins during local full-stack development (not recommended for production).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Pydantic models (request/response)
# -----------------------------


class GenerateTestsRequest(BaseModel):
    """Request payload for generating tests."""

    acceptance_criteria: str
    user_story: Optional[str] = None


class TestCase(BaseModel):
    """Represents a single test case returned by the AI."""

    id: int
    type: str  # "positive", "negative", "edge_case"
    title: str
    description: str
    steps: List[str]
    expected_result: str


class GenerateTestsResponse(BaseModel):
    test_cases: List[TestCase]
    acceptance_criteria: str


class ExecuteTestsRequest(BaseModel):
    test_cases: List[TestCase]
    acceptance_criteria: str


class ExecuteTestsRealRequest(BaseModel):
    """Request payload for real HTTP or browser-based test execution."""

    test_cases: List[TestCase]
    acceptance_criteria: str
    target_url: str


class StepResult(BaseModel):
    step: str
    status: str
    output: str


class TestResult(BaseModel):
    test_case_id: int
    test_case_title: str
    test_type: str
    status: str  # "PASS", "FAIL", "ERROR"
    actual_result: str
    details: str
    steps_executed: List[StepResult]


class ExecuteTestsResponse(BaseModel):
    results: List[TestResult]
    summary: Dict[str, Any]
    execution_mode: str = "ai_simulated"


# Preferred Gemini models (ordered by preference).
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
]


def get_gemini_client() -> Any:
    """Create and return a Gemini client.

    We return a runtime client; any missing API key is surfaced as an HTTP 500.
    The return type is kept generic to avoid tight coupling to the SDK typing.
    """

    key = os.getenv("GEMINI_API_KEY", "")
    use_mock = os.getenv("USE_MOCK_AI", "false").lower() in ("1", "true", "yes")
    # When `USE_MOCK_AI` is truthy, return None so endpoints run in dev-mode
    # and produce canned/simulated responses without a real Gemini key.
    if use_mock:
        return None
    if not key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured; set USE_MOCK_AI=true for local dev")
    return genai.Client(api_key=key)


def generate_with_fallback(client: Any, prompt: str) -> str:
    """Attempt generation across multiple models until one returns text.

    The AI SDK can fail for individual models; try the list in order and raise
    the last exception if none succeed.
    """

    last_error: Optional[Exception] = None
    for model_name in GEMINI_MODELS:
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            # The SDK returns an object with a `text` attribute on success.
            if getattr(response, "text", None):
                return response.text
        except Exception as e:  # Catch SDK and network errors per-model.
            last_error = e
            continue

    # If we reached here, no model returned usable text.
    if last_error:
        # Surface the SDK error for debugging in logs; convert to HTTP error for API clients.
        raise HTTPException(status_code=502, detail=f"AI models failed: {last_error}")

    raise HTTPException(status_code=500, detail="All AI models failed to respond")


def clean_json_response(content: str) -> str:
    """Strip common code fences and whitespace from AI responses.

    AI responses sometimes include Markdown fences like ```json ... ```; remove them
    so `json.loads` can parse the payload.
    """

    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def build_summary(results: List[TestResult]) -> Dict[str, Any]:
    """Build a summary dict from test results."""
    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    errored = sum(1 for r in results if r.status == "ERROR")
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "pass_rate": f"{(passed / total * 100):.1f}%" if total > 0 else "0%",
    }


# Simple health check used by load balancers / orchestrators.
@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/generate-tests", response_model=GenerateTestsResponse)
async def generate_tests(request: GenerateTestsRequest) -> GenerateTestsResponse:
    """Call the AI to generate 3 test cases from the given acceptance criteria.

    The endpoint validates the AI response and converts it into `TestCase` models.
    """

    client = get_gemini_client()

    # Optional user story context appended to the prompt.
    user_story_context = f"\nUser Story: {request.user_story}\n" if request.user_story else ""

    prompt = f"""You are a senior QA engineer. Given the following acceptance criteria{' and user story' if request.user_story else ''}, generate exactly 3 test cases:

1. A POSITIVE test case - tests the happy path / expected behavior
2. A NEGATIVE test case - tests error handling / invalid inputs / boundary violations
3. An EDGE CASE test case - tests unusual but valid scenarios / boundary conditions
{user_story_context}
Acceptance Criteria:
{request.acceptance_criteria}

Return your response as a JSON object with this exact structure:
{{
  "test_cases": [
    {{
      "id": 1,
      "type": "positive",
      "title": "Short descriptive title",
      "description": "Detailed description of what this test validates",
      "steps": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
      "expected_result": "What should happen when this test passes"
    }},
    {{
      "id": 2,
      "type": "negative",
      "title": "Short descriptive title",
      "description": "Detailed description of what this test validates",
      "steps": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
      "expected_result": "What should happen when this test passes"
    }},
    {{
      "id": 3,
      "type": "edge_case",
      "title": "Short descriptive title",
      "description": "Detailed description of what this test validates",
      "steps": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
      "expected_result": "What should happen when this test passes"
    }}
  ]
}}

Return ONLY valid JSON, no markdown code blocks or extra text."""

    try:
        # If no Gemini client is available (dev mode), return a canned sample response
        if client is None:
            parsed = {
                "test_cases": [
                    {
                        "id": 1,
                        "type": "positive",
                        "title": "Happy path - valid credentials",
                        "description": "User with valid credentials can log in and reach the dashboard",
                        "steps": [
                            "Navigate to login page",
                            "Enter valid email and password",
                            "Click submit"
                        ],
                        "expected_result": "User is redirected to the dashboard and welcome message is shown"
                    },
                    {
                        "id": 2,
                        "type": "negative",
                        "title": "Invalid password shows error",
                        "description": "Incorrect password should show an error message",
                        "steps": [
                            "Navigate to login page",
                            "Enter valid email and invalid password",
                            "Click submit"
                        ],
                        "expected_result": "An 'Invalid password' error message is displayed"
                    },
                    {
                        "id": 3,
                        "type": "edge_case",
                        "title": "Empty password field",
                        "description": "Submitting with empty password should show validation error",
                        "steps": [
                            "Navigate to login page",
                            "Leave password empty",
                            "Click submit"
                        ],
                        "expected_result": "A validation message about required password is shown"
                    }
                ]
            }
        else:
            content = generate_with_fallback(client, prompt)
            content = clean_json_response(content)
            parsed = json.loads(content)

        # Validate shape before constructing Pydantic objects.
        if "test_cases" not in parsed or not isinstance(parsed["test_cases"], list):
            raise HTTPException(status_code=502, detail="AI returned unexpected structure for test_cases")

        test_cases = [TestCase(**tc) for tc in parsed["test_cases"]]

        return GenerateTestsResponse(test_cases=test_cases, acceptance_criteria=request.acceptance_criteria)

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating tests: {str(e)}")


@app.post("/api/execute-tests", response_model=ExecuteTestsResponse)
async def execute_tests(request: ExecuteTestsRequest) -> ExecuteTestsResponse:
    """Ask the AI to simulate executing test cases and return structured results.

    The endpoint computes a small summary (pass/fail counts) from the AI response.
    """

    client = get_gemini_client()

    # Provide the test cases as JSON for the AI to reason about.
    test_cases_json = json.dumps([tc.model_dump() for tc in request.test_cases], indent=2)

    prompt = f"""You are a test execution engine. Given the following acceptance criteria and test cases, simulate executing each test case and determine whether it would PASS or FAIL.

Acceptance Criteria:
{request.acceptance_criteria}

Test Cases:
{test_cases_json}

For each test case, simulate its execution step by step. Determine if the test would PASS or FAIL based on the acceptance criteria.

Rules:
- Positive test cases should generally PASS if the acceptance criteria is well-defined
- Negative test cases should PASS if the system properly handles the error case described
- Edge cases may PASS or FAIL depending on the criteria coverage
- Be realistic in your evaluation

Return your response as a JSON object with this exact structure:
{{
  "results": [
    {{
      "test_case_id": 1,
      "test_case_title": "Title from the test case",
      "test_type": "positive",
      "status": "PASS",
      "actual_result": "Description of what actually happened during execution",
      "details": "Detailed explanation of why this test passed or failed",
      "steps_executed": [
        {{"step": "Step 1: ...", "status": "PASS", "output": "Step completed successfully"}},
        {{"step": "Step 2: ...", "status": "PASS", "output": "Step completed successfully"}}
      ]
    }}
  ]
}}

Return ONLY valid JSON, no markdown code blocks or extra text."""

    try:
        # Dev-mode canned execution when no Gemini client is available.
        if client is None:
            parsed = {"results": []}
            for tc in request.test_cases:
                # Simple heuristic for dev: mark positive/negative as PASS, edge_case as FAIL
                status = "PASS" if tc.type in ("positive", "negative") else "FAIL"
                steps_executed = []
                for step in tc.steps:
                    steps_executed.append({"step": step, "status": status, "output": f"Simulated output for '{step}'"})

                parsed["results"].append({
                    "test_case_id": tc.id,
                    "test_case_title": tc.title,
                    "test_type": tc.type,
                    "status": status,
                    "actual_result": tc.expected_result if status == "PASS" else f"Simulated failure for {tc.title}",
                    "details": f"This is a simulated execution (dev mode). Marked {status}.",
                    "steps_executed": steps_executed,
                })
        else:
            content = generate_with_fallback(client, prompt)
            content = clean_json_response(content)
            parsed = json.loads(content)

        results = [TestResult(**r) for r in parsed.get("results", [])]
        summary = build_summary(results)

        return ExecuteTestsResponse(results=results, summary=summary, execution_mode="ai_simulated")

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing tests: {str(e)}")


# --------------------------
# Execute tests - Real HTTP Testing
# --------------------------

@app.post("/api/execute-tests-http", response_model=ExecuteTestsResponse)
async def execute_tests_http(request: ExecuteTestsRealRequest) -> ExecuteTestsResponse:
    """Execute test cases by making real HTTP requests to the target URL."""

    client = get_gemini_client()
    target_url = request.target_url.rstrip("/")
    test_cases_json = json.dumps([tc.model_dump() for tc in request.test_cases], indent=2)

    prompt = f"""You are a QA automation engineer. Given acceptance criteria, test cases, and a target URL, generate an HTTP test plan for each test case.

Target URL: {target_url}
Acceptance Criteria: {request.acceptance_criteria}

Test Cases:
{test_cases_json}

For each test case, generate a list of HTTP requests to execute. Return a JSON object:
{{
  "test_plans": [
    {{
      "test_case_id": 1,
      "requests": [
        {{
          "method": "GET",
          "path": "/",
          "headers": {{}},
          "body": null,
          "expected_status": 200,
          "description": "Load the homepage"
        }}
      ]
    }}
  ]
}}

Rules:
- Use realistic HTTP methods and paths based on the acceptance criteria
- For login tests, try POST /login, POST /api/login, POST /auth/login etc.
- For page loads, use GET requests
- Include appropriate headers (Content-Type: application/json for API calls)
- expected_status should be realistic (200 for success, 401/403 for unauthorized, 400 for bad input)

Return ONLY valid JSON, no markdown code blocks or extra text."""

    try:
        # Dev-mode canned HTTP test plan when no Gemini client is available.
        if client is None:
            test_plans = {
                "test_plans": [
                    {
                        "test_case_id": tc.id,
                        "requests": [
                            {
                                "method": "GET",
                                "path": "/",
                                "headers": {},
                                "body": None,
                                "expected_status": 200,
                                "description": f"Load homepage for '{tc.title}'",
                            }
                        ],
                    }
                    for tc in request.test_cases
                ]
            }
        else:
            content = generate_with_fallback(client, prompt)
            content = clean_json_response(content)
            test_plans = json.loads(content)
        results: List[TestResult] = []

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as http_client:
            for plan in test_plans.get("test_plans", []):
                test_case_id = plan["test_case_id"]
                matching_tc = next(
                    (tc for tc in request.test_cases if tc.id == test_case_id), None
                )
                if not matching_tc:
                    continue

                steps_executed: List[StepResult] = []
                overall_status = "PASS"
                actual_results: List[str] = []

                for req in plan.get("requests", []):
                    method = req.get("method", "GET").upper()
                    path = req.get("path", "/")
                    headers = req.get("headers", {})
                    body = req.get("body")
                    expected_status = req.get("expected_status", 200)
                    description = req.get("description", f"{method} {path}")
                    url = f"{target_url}{path}"

                    try:
                        if method == "POST":
                            resp = await http_client.post(url, headers=headers, json=body)
                        elif method == "PUT":
                            resp = await http_client.put(url, headers=headers, json=body)
                        elif method == "DELETE":
                            resp = await http_client.delete(url, headers=headers)
                        elif method == "PATCH":
                            resp = await http_client.patch(url, headers=headers, json=body)
                        else:
                            resp = await http_client.get(url, headers=headers)

                        status_match = resp.status_code == expected_status
                        step_status = "PASS" if status_match else "FAIL"
                        if not status_match:
                            overall_status = "FAIL"
                        response_preview = resp.text[:200] if resp.text else "(empty)"
                        step_output = (
                            f"HTTP {resp.status_code} (expected {expected_status}). "
                            f"Response: {response_preview}"
                        )
                        steps_executed.append(StepResult(
                            step=f"{description} [{method} {path}]",
                            status=step_status,
                            output=step_output,
                        ))
                        actual_results.append(f"{method} {path} -> {resp.status_code}")

                    except httpx.ConnectError:
                        overall_status = "FAIL"
                        steps_executed.append(StepResult(
                            step=f"{description} [{method} {path}]",
                            status="FAIL",
                            output=f"Connection refused: {url}",
                        ))
                        actual_results.append(f"{method} {path} -> Connection refused")
                    except httpx.TimeoutException:
                        overall_status = "FAIL"
                        steps_executed.append(StepResult(
                            step=f"{description} [{method} {path}]",
                            status="FAIL",
                            output=f"Timeout: {url}",
                        ))
                        actual_results.append(f"{method} {path} -> Timeout")
                    except Exception as exc:
                        overall_status = "ERROR"
                        steps_executed.append(StepResult(
                            step=f"{description} [{method} {path}]",
                            status="ERROR",
                            output=f"Error: {str(exc)}",
                        ))
                        actual_results.append(f"{method} {path} -> Error")

                results.append(TestResult(
                    test_case_id=test_case_id,
                    test_case_title=matching_tc.title,
                    test_type=matching_tc.type,
                    status=overall_status,
                    actual_result="; ".join(actual_results),
                    details=f"Executed {len(steps_executed)} HTTP request(s) against {target_url}",
                    steps_executed=steps_executed,
                ))

        summary = build_summary(results)
        return ExecuteTestsResponse(
            results=results, summary=summary, execution_mode="http_real"
        )
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to parse AI test plan: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error in HTTP test execution: {str(e)}"
        )


# --------------------------
# Execute tests - Real Browser Testing (Playwright)
# --------------------------

@app.post("/api/execute-tests-browser", response_model=ExecuteTestsResponse)
async def execute_tests_browser(request: ExecuteTestsRealRequest) -> ExecuteTestsResponse:
    """Execute test cases using a real headless browser via Playwright."""

    from playwright.async_api import async_playwright

    client = get_gemini_client()
    target_url = request.target_url.rstrip("/")
    test_cases_json = json.dumps([tc.model_dump() for tc in request.test_cases], indent=2)

    prompt = f"""You are a browser test automation expert. Given acceptance criteria, test cases, and a target URL, generate a browser test plan for each test case.

Target URL: {target_url}
Acceptance Criteria: {request.acceptance_criteria}

Test Cases:
{test_cases_json}

For each test case, generate a list of browser actions. Return a JSON object:
{{
  "test_plans": [
    {{
      "test_case_id": 1,
      "actions": [
        {{"action": "goto", "url": "{target_url}", "description": "Navigate to the page"}},
        {{"action": "check_title", "expected": "My App", "description": "Verify page title"}},
        {{"action": "check_visible", "selector": "input[type=email]", "description": "Check email input visible"}},
        {{"action": "fill", "selector": "input[type=email]", "value": "test@example.com", "description": "Enter email"}},
        {{"action": "click", "selector": "button[type=submit]", "description": "Click submit"}},
        {{"action": "check_url", "expected": "/dashboard", "description": "Verify redirect"}},
        {{"action": "check_text", "text": "Welcome", "description": "Verify welcome message"}}
      ]
    }}
  ]
}}

Available actions:
- "goto": Navigate to URL. Params: url
- "fill": Type into input. Params: selector, value
- "click": Click element. Params: selector
- "check_title": Check title contains text. Params: expected
- "check_url": Check URL contains text. Params: expected
- "check_visible": Check element visible. Params: selector
- "check_text": Check page contains text. Params: text
- "wait": Wait ms. Params: ms

Rules:
- Start each test with "goto" to the target URL
- Use CSS selectors for elements
- Be realistic about selectors
- Include verification steps

Return ONLY valid JSON, no markdown code blocks or extra text."""

    try:
        # Dev-mode canned browser test plan when no Gemini client is available.
        if client is None:
            test_plans = {
                "test_plans": [
                    {
                        "test_case_id": tc.id,
                        "actions": [
                            {"action": "goto", "url": target_url, "description": f"Navigate to {target_url}"},
                            {"action": "check_title", "expected": "", "description": "Check page has a title"},
                            {"action": "check_text", "text": ".", "description": f"Verify page has content for '{tc.title}'"},
                        ],
                    }
                    for tc in request.test_cases
                ]
            }
        else:
            content = generate_with_fallback(client, prompt)
            content = clean_json_response(content)
            test_plans = json.loads(content)
        results: List[TestResult] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)

            for plan in test_plans.get("test_plans", []):
                test_case_id = plan["test_case_id"]
                matching_tc = next(
                    (tc for tc in request.test_cases if tc.id == test_case_id), None
                )
                if not matching_tc:
                    continue

                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()
                steps_executed: List[StepResult] = []
                overall_status = "PASS"

                for action_def in plan.get("actions", []):
                    action = action_def.get("action", "")
                    description = action_def.get("description", action)

                    try:
                        if action == "goto":
                            nav_url = action_def.get("url", target_url)
                            if not nav_url.startswith("http"):
                                nav_url = f"{target_url}{nav_url}"
                            response = await page.goto(
                                nav_url, wait_until="domcontentloaded", timeout=15000
                            )
                            status_code = response.status if response else 0
                            step_ok = 200 <= status_code < 400
                            steps_executed.append(StepResult(
                                step=description,
                                status="PASS" if step_ok else "FAIL",
                                output=f"Navigated to {nav_url} (HTTP {status_code})",
                            ))
                            if not step_ok:
                                overall_status = "FAIL"

                        elif action == "fill":
                            selector = action_def.get("selector", "")
                            value = action_def.get("value", "")
                            try:
                                await page.fill(selector, value, timeout=5000)
                                steps_executed.append(StepResult(
                                    step=description,
                                    status="PASS",
                                    output=f"Filled '{selector}' with value",
                                ))
                            except Exception:
                                overall_status = "FAIL"
                                steps_executed.append(StepResult(
                                    step=description,
                                    status="FAIL",
                                    output=f"Element not found: {selector}",
                                ))

                        elif action == "click":
                            selector = action_def.get("selector", "")
                            try:
                                await page.click(selector, timeout=5000)
                                await page.wait_for_timeout(1000)
                                steps_executed.append(StepResult(
                                    step=description,
                                    status="PASS",
                                    output=f"Clicked: {selector}",
                                ))
                            except Exception:
                                overall_status = "FAIL"
                                steps_executed.append(StepResult(
                                    step=description,
                                    status="FAIL",
                                    output=f"Element not clickable: {selector}",
                                ))

                        elif action == "check_title":
                            expected = action_def.get("expected", "")
                            title = await page.title()
                            if expected.lower() in title.lower():
                                steps_executed.append(StepResult(
                                    step=description,
                                    status="PASS",
                                    output=f"Title '{title}' contains '{expected}'",
                                ))
                            else:
                                overall_status = "FAIL"
                                steps_executed.append(StepResult(
                                    step=description,
                                    status="FAIL",
                                    output=f"Title '{title}' missing '{expected}'",
                                ))

                        elif action == "check_url":
                            expected = action_def.get("expected", "")
                            current_url = page.url
                            if expected.lower() in current_url.lower():
                                steps_executed.append(StepResult(
                                    step=description,
                                    status="PASS",
                                    output=f"URL '{current_url}' contains '{expected}'",
                                ))
                            else:
                                overall_status = "FAIL"
                                steps_executed.append(StepResult(
                                    step=description,
                                    status="FAIL",
                                    output=f"URL '{current_url}' missing '{expected}'",
                                ))

                        elif action == "check_visible":
                            selector = action_def.get("selector", "")
                            try:
                                is_visible = await page.is_visible(selector, timeout=5000)
                                if is_visible:
                                    steps_executed.append(StepResult(
                                        step=description,
                                        status="PASS",
                                        output=f"Element '{selector}' is visible",
                                    ))
                                else:
                                    overall_status = "FAIL"
                                    steps_executed.append(StepResult(
                                        step=description,
                                        status="FAIL",
                                        output=f"Element '{selector}' not visible",
                                    ))
                            except Exception:
                                overall_status = "FAIL"
                                steps_executed.append(StepResult(
                                    step=description,
                                    status="FAIL",
                                    output=f"Element '{selector}' not found",
                                ))

                        elif action == "check_text":
                            text = action_def.get("text", "")
                            page_content = await page.content()
                            if text.lower() in page_content.lower():
                                steps_executed.append(StepResult(
                                    step=description,
                                    status="PASS",
                                    output=f"Page contains '{text}'",
                                ))
                            else:
                                overall_status = "FAIL"
                                steps_executed.append(StepResult(
                                    step=description,
                                    status="FAIL",
                                    output=f"Page missing '{text}'",
                                ))

                        elif action == "wait":
                            ms = action_def.get("ms", 1000)
                            await page.wait_for_timeout(ms)
                            steps_executed.append(StepResult(
                                step=description,
                                status="PASS",
                                output=f"Waited {ms}ms",
                            ))

                        else:
                            steps_executed.append(StepResult(
                                step=description,
                                status="PASS",
                                output=f"Skipped unknown action '{action}'",
                            ))

                    except Exception as exc:
                        overall_status = "FAIL"
                        steps_executed.append(StepResult(
                            step=description,
                            status="FAIL",
                            output=f"Browser error: {str(exc)[:200]}",
                        ))

                await context.close()
                passed_steps = sum(1 for s in steps_executed if s.status == "PASS")
                total_steps = len(steps_executed)
                results.append(TestResult(
                    test_case_id=test_case_id,
                    test_case_title=matching_tc.title,
                    test_type=matching_tc.type,
                    status=overall_status,
                    actual_result=f"{passed_steps}/{total_steps} steps passed on {target_url}",
                    details=(
                        f"Browser test: {total_steps} actions against "
                        f"{target_url} using headless Chromium"
                    ),
                    steps_executed=steps_executed,
                ))

            await browser.close()

        summary = build_summary(results)
        return ExecuteTestsResponse(
            results=results, summary=summary, execution_mode="browser_real"
        )
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to parse AI test plan: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Browser test error: {str(e)}\n{traceback.format_exc()}",
        )
