# AI Test Automation

A full-stack application that uses Google Gemini AI to automatically generate and execute test cases from acceptance criteria.

## Features

- **AI-Powered Test Generation**: Enter acceptance criteria and get 3 test cases automatically generated:
  - Positive test case (happy path)
  - Negative test case (error handling)
  - Edge case test case (boundary conditions)
- **Test Execution Simulation**: AI simulates executing each test case step-by-step and produces detailed results
- **Detailed Results Dashboard**: View pass/fail status, execution details, and step-by-step breakdown

## Tech Stack

- **Frontend**: React + TypeScript + Vite + Tailwind CSS + shadcn/ui
- **Backend**: Python + FastAPI + Google Gemini AI
- **AI Model**: Google Gemini 2.5 Flash Lite (with fallback to other models)

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.12+
- Poetry (Python package manager)
- Google Gemini API Key (free at https://aistudio.google.com/apikey)

### Backend Setup

```bash
cd test-automation-backend
echo "GEMINI_API_KEY=your_api_key_here" > .env
poetry install
poetry run fastapi dev app/main.py
```

The backend will start at http://localhost:8000

### Frontend Setup

```bash
cd test-automation-frontend
echo "VITE_API_URL=http://localhost:8000" > .env
npm install
npm run dev
```

The frontend will start at http://localhost:5173

## API Endpoints

- `GET /healthz` - Health check
- `POST /api/generate-tests` - Generate test cases from acceptance criteria
- `POST /api/execute-tests` - Execute test cases and get results

## Usage

1. Enter your user story (optional) and acceptance criteria
2. Click "Generate Test Cases" to create 3 AI-powered test cases
3. Review the generated positive, negative, and edge case tests
4. Click "Execute All Tests" to simulate test execution
5. View detailed results with pass/fail status and step-by-step execution logs
