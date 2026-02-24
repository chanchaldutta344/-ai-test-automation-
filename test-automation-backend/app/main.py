"""Main FastAPI application for test automation backend.

This module exposes two endpoints:
- POST /api/generate-tests: ask the AI to generate test cases from acceptance criteria
- POST /api/execute-tests: ask the AI to simulate executing test cases and return results

The code is intentionally defensive around AI responses (strip code fences, validate JSON).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

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
    if not key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")
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
        content = generate_with_fallback(client, prompt)
        content = clean_json_response(content)
        parsed = json.loads(content)

        results = [TestResult(**r) for r in parsed.get("results", [])]

        total = len(results)
        passed = sum(1 for r in results if r.status == "PASS")
        failed = sum(1 for r in results if r.status == "FAIL")
        errored = sum(1 for r in results if r.status == "ERROR")

        summary = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errored": errored,
            "pass_rate": f"{(passed / total * 100):.1f}%" if total > 0 else "0%",
        }

        return ExecuteTestsResponse(results=results, summary=summary)

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing tests: {str(e)}")
