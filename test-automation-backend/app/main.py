from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import json
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

app = FastAPI()

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


class GenerateTestsRequest(BaseModel):
    acceptance_criteria: str
    user_story: Optional[str] = None


class TestCase(BaseModel):
    id: int
    type: str  # "positive", "negative", "edge_case"
    title: str
    description: str
    steps: list[str]
    expected_result: str


class GenerateTestsResponse(BaseModel):
    test_cases: list[TestCase]
    acceptance_criteria: str


class ExecuteTestsRequest(BaseModel):
    test_cases: list[TestCase]
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
    steps_executed: list[StepResult]


class ExecuteTestsResponse(BaseModel):
    results: list[TestResult]
    summary: dict


GEMINI_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
]


def get_gemini_client() -> genai.Client:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")
    return genai.Client(api_key=key)


def generate_with_fallback(client: genai.Client, prompt: str) -> str:
    """Try multiple Gemini models with fallback."""
    last_error = None
    for model_name in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            if response.text:
                return response.text
        except Exception as e:
            last_error = e
            continue
    if last_error:
        raise last_error
    raise HTTPException(status_code=500, detail="All AI models failed to respond")


def clean_json_response(content: str) -> str:
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/api/generate-tests", response_model=GenerateTestsResponse)
async def generate_tests(request: GenerateTestsRequest):
    client = get_gemini_client()

    user_story_context = ""
    if request.user_story:
        user_story_context = f"\nUser Story: {request.user_story}\n"

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
        test_cases = [TestCase(**tc) for tc in parsed["test_cases"]]

        return GenerateTestsResponse(
            test_cases=test_cases,
            acceptance_criteria=request.acceptance_criteria
        )

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating tests: {str(e)}")


@app.post("/api/execute-tests", response_model=ExecuteTestsResponse)
async def execute_tests(request: ExecuteTestsRequest):
    client = get_gemini_client()

    prompt = f"""You are a test execution engine. Given the following acceptance criteria and test cases, simulate executing each test case and determine whether it would PASS or FAIL.

Acceptance Criteria:
{request.acceptance_criteria}

Test Cases:
{json.dumps([tc.model_dump() for tc in request.test_cases], indent=2)}

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
            "pass_rate": f"{(passed / total * 100):.1f}%" if total > 0 else "0%"
        }

        return ExecuteTestsResponse(results=results, summary=summary)

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing tests: {str(e)}")
