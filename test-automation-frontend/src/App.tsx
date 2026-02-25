import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { FlaskConical, Play, CheckCircle2, XCircle, AlertTriangle, Loader2, ChevronDown, ChevronUp, Sparkles, Globe, Monitor, Cpu } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface TestCase {
  id: number
  type: string
  title: string
  description: string
  steps: string[]
  expected_result: string
}

interface StepResult {
  step: string
  status: string
  output: string
}

interface TestResult {
  test_case_id: number
  test_case_title: string
  test_type: string
  status: string
  actual_result: string
  details: string
  steps_executed: StepResult[]
}

interface ExecutionSummary {
  total: number
  passed: number
  failed: number
  errored: number
  pass_rate: string
}

function App() {
  const [acceptanceCriteria, setAcceptanceCriteria] = useState('')
  const [userStory, setUserStory] = useState('')
  const [testCases, setTestCases] = useState<TestCase[]>([])
  const [testResults, setTestResults] = useState<TestResult[]>([])
  const [summary, setSummary] = useState<ExecutionSummary | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isExecuting, setIsExecuting] = useState(false)
  const [error, setError] = useState('')
  const [expandedResults, setExpandedResults] = useState<Set<number>>(new Set())
  const [activeTab, setActiveTab] = useState('input')
  const [executionMode, setExecutionMode] = useState<'ai' | 'http' | 'browser'>('ai')
  const [targetUrl, setTargetUrl] = useState('')
  const [executionModeLabel, setExecutionModeLabel] = useState('')

  const toggleResultExpanded = (id: number) => {
    setExpandedResults(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleGenerateTests = async () => {
    if (!acceptanceCriteria.trim()) {
      setError('Please enter acceptance criteria')
      return
    }

    setIsGenerating(true)
    setError('')
    setTestCases([])
    setTestResults([])
    setSummary(null)

    try {
      const response = await fetch(`${API_URL}/api/generate-tests`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          acceptance_criteria: acceptanceCriteria,
          user_story: userStory || undefined,
        }),
      })

      if (!response.ok) {
        const errData = await response.json()
        throw new Error(errData.detail || 'Failed to generate test cases')
      }

      const data = await response.json()
      setTestCases(data.test_cases)
      setActiveTab('tests')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleExecuteTests = async () => {
    if (testCases.length === 0) {
      setError('No test cases to execute')
      return
    }

    if (executionMode !== 'ai' && !targetUrl.trim()) {
      setError('Please enter a target URL for real testing')
      return
    }

    setIsExecuting(true)
    setError('')
    setTestResults([])
    setSummary(null)

    // Choose endpoint based on execution mode
    let endpoint = '/api/execute-tests'
    if (executionMode === 'http') endpoint = '/api/execute-tests-http'
    if (executionMode === 'browser') endpoint = '/api/execute-tests-browser'

    const modeLabels = { ai: 'AI Simulated', http: 'HTTP Testing', browser: 'Browser Testing' }

    try {
      const payload: Record<string, unknown> = {
        test_cases: testCases,
        acceptance_criteria: acceptanceCriteria,
      }
      if (executionMode !== 'ai') {
        payload.target_url = targetUrl
      }

      const response = await fetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const errData = await response.json()
        throw new Error(errData.detail || 'Failed to execute test cases')
      }

      const data = await response.json()
      setTestResults(data.results)
      setSummary(data.summary)
      setExecutionModeLabel(modeLabels[executionMode])
      setExpandedResults(new Set(data.results.map((r: TestResult) => r.test_case_id)))
      setActiveTab('results')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setIsExecuting(false)
    }
  }

  const getTypeBadge = (type: string) => {
    switch (type) {
      case 'positive':
        return <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200 hover:bg-emerald-100">Positive</Badge>
      case 'negative':
        return <Badge className="bg-red-100 text-red-800 border-red-200 hover:bg-red-100">Negative</Badge>
      case 'edge_case':
        return <Badge className="bg-amber-100 text-amber-800 border-amber-200 hover:bg-amber-100">Edge Case</Badge>
      default:
        return <Badge variant="outline">{type}</Badge>
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'PASS':
        return <CheckCircle2 className="text-emerald-500" size={20} />
      case 'FAIL':
        return <XCircle className="text-red-500" size={20} />
      default:
        return <AlertTriangle className="text-amber-500" size={20} />
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PASS':
        return <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200 hover:bg-emerald-100">PASS</Badge>
      case 'FAIL':
        return <Badge className="bg-red-100 text-red-800 border-red-200 hover:bg-red-100">FAIL</Badge>
      default:
        return <Badge className="bg-amber-100 text-amber-800 border-amber-200 hover:bg-amber-100">ERROR</Badge>
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      {/* Header */}
      <header className="border-b bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center gap-3">
          <div className="p-2 bg-indigo-600 rounded-lg">
            <FlaskConical className="text-white" size={24} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">AI Test Automation</h1>
            <p className="text-sm text-slate-500">Generate & execute test cases from acceptance criteria</p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Sparkles className="text-indigo-500" size={16} />
            <span className="text-xs text-slate-500">Powered by Google Gemini</span>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Error Banner */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
            <XCircle className="text-red-500 mt-0.5 shrink-0" size={18} />
            <div>
              <p className="text-sm font-medium text-red-800">Error</p>
              <p className="text-sm text-red-600 mt-1">{error}</p>
            </div>
            <button onClick={() => setError('')} className="ml-auto text-red-400 hover:text-red-600">
              <XCircle size={16} />
            </button>
          </div>
        )}

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-6 bg-white border">
            <TabsTrigger value="input" className="data-[state=active]:bg-indigo-50 data-[state=active]:text-indigo-700">
              Input
            </TabsTrigger>
            <TabsTrigger
              value="tests"
              className="data-[state=active]:bg-indigo-50 data-[state=active]:text-indigo-700"
              disabled={testCases.length === 0}
            >
              Test Cases ({testCases.length})
            </TabsTrigger>
            <TabsTrigger
              value="results"
              className="data-[state=active]:bg-indigo-50 data-[state=active]:text-indigo-700"
              disabled={testResults.length === 0}
            >
              Results {summary && `(${summary.pass_rate})`}
            </TabsTrigger>
          </TabsList>

          {/* Input Tab */}
          <TabsContent value="input">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Acceptance Criteria</CardTitle>
                    <CardDescription>
                      Enter the acceptance criteria for your user story. The AI will generate positive, negative, and edge case test cases.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <label className="text-sm font-medium text-slate-700 mb-1.5 block">
                        User Story (Optional)
                      </label>
                      <Textarea
                        placeholder="As a [user], I want to [action], so that [benefit]..."
                        value={userStory}
                        onChange={(e) => setUserStory(e.target.value)}
                        className="resize-none h-20 border-slate-200 focus:border-indigo-300 focus:ring-indigo-200"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium text-slate-700 mb-1.5 block">
                        Acceptance Criteria <span className="text-red-500">*</span>
                      </label>
                      <Textarea
                        placeholder={`Enter your acceptance criteria here, e.g.:\n\n- Given a registered user with valid credentials\n- When they enter their email and password on the login page\n- Then they should be redirected to the dashboard\n- And a welcome message should be displayed\n- If credentials are invalid, an error message should appear`}
                        value={acceptanceCriteria}
                        onChange={(e) => setAcceptanceCriteria(e.target.value)}
                        className="resize-none h-48 border-slate-200 focus:border-indigo-300 focus:ring-indigo-200"
                      />
                    </div>
                    <Button
                      onClick={handleGenerateTests}
                      disabled={isGenerating || !acceptanceCriteria.trim()}
                      className="w-full bg-indigo-600 hover:bg-indigo-700 text-white h-11"
                    >
                      {isGenerating ? (
                        <>
                          <Loader2 className="animate-spin" size={18} />
                          Generating Test Cases...
                        </>
                      ) : (
                        <>
                          <Sparkles size={18} />
                          Generate Test Cases
                        </>
                      )}
                    </Button>
                  </CardContent>
                </Card>
              </div>

              {/* How it Works */}
              <div>
                <Card className="border-indigo-100 bg-indigo-50/30">
                  <CardHeader>
                    <CardTitle className="text-lg text-indigo-900">How It Works</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      <div className="flex gap-3">
                        <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-sm font-bold shrink-0">1</div>
                        <div>
                          <p className="text-sm font-medium text-slate-800">Enter Criteria</p>
                          <p className="text-xs text-slate-500 mt-0.5">Provide your acceptance criteria and optional user story</p>
                        </div>
                      </div>
                      <div className="flex gap-3">
                        <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-sm font-bold shrink-0">2</div>
                        <div>
                          <p className="text-sm font-medium text-slate-800">Generate Tests</p>
                          <p className="text-xs text-slate-500 mt-0.5">AI creates positive, negative, and edge case tests</p>
                        </div>
                      </div>
                      <div className="flex gap-3">
                        <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-sm font-bold shrink-0">3</div>
                        <div>
                          <p className="text-sm font-medium text-slate-800">Execute Tests</p>
                          <p className="text-xs text-slate-500 mt-0.5">AI simulates execution and produces detailed results</p>
                        </div>
                      </div>
                      <div className="flex gap-3">
                        <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-sm font-bold shrink-0">4</div>
                        <div>
                          <p className="text-sm font-medium text-slate-800">Review Results</p>
                          <p className="text-xs text-slate-500 mt-0.5">See pass/fail status with detailed step-by-step execution</p>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>

          {/* Test Cases Tab */}
          <TabsContent value="tests">
            <div className="space-y-4">
              {/* Execution Mode Selector */}
              <Card className="border-indigo-100">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Execution Mode</CardTitle>
                  <CardDescription>Choose how to execute the generated test cases</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <button
                      onClick={() => setExecutionMode('ai')}
                      className={`flex items-center gap-3 p-4 rounded-lg border-2 transition-all text-left ${
                        executionMode === 'ai'
                          ? 'border-indigo-500 bg-indigo-50'
                          : 'border-slate-200 hover:border-slate-300 bg-white'
                      }`}
                    >
                      <Cpu className={executionMode === 'ai' ? 'text-indigo-600' : 'text-slate-400'} size={24} />
                      <div>
                        <p className={`text-sm font-semibold ${executionMode === 'ai' ? 'text-indigo-900' : 'text-slate-700'}`}>AI Simulation</p>
                        <p className="text-xs text-slate-500">AI reasons about pass/fail</p>
                      </div>
                    </button>
                    <button
                      onClick={() => setExecutionMode('http')}
                      className={`flex items-center gap-3 p-4 rounded-lg border-2 transition-all text-left ${
                        executionMode === 'http'
                          ? 'border-emerald-500 bg-emerald-50'
                          : 'border-slate-200 hover:border-slate-300 bg-white'
                      }`}
                    >
                      <Globe className={executionMode === 'http' ? 'text-emerald-600' : 'text-slate-400'} size={24} />
                      <div>
                        <p className={`text-sm font-semibold ${executionMode === 'http' ? 'text-emerald-900' : 'text-slate-700'}`}>HTTP Testing</p>
                        <p className="text-xs text-slate-500">Real HTTP requests to URL</p>
                      </div>
                    </button>
                    <button
                      onClick={() => setExecutionMode('browser')}
                      className={`flex items-center gap-3 p-4 rounded-lg border-2 transition-all text-left ${
                        executionMode === 'browser'
                          ? 'border-purple-500 bg-purple-50'
                          : 'border-slate-200 hover:border-slate-300 bg-white'
                      }`}
                    >
                      <Monitor className={executionMode === 'browser' ? 'text-purple-600' : 'text-slate-400'} size={24} />
                      <div>
                        <p className={`text-sm font-semibold ${executionMode === 'browser' ? 'text-purple-900' : 'text-slate-700'}`}>Browser Testing</p>
                        <p className="text-xs text-slate-500">Headless Chromium via Playwright</p>
                      </div>
                    </button>
                  </div>

                  {executionMode !== 'ai' && (
                    <div>
                      <label className="text-sm font-medium text-slate-700 mb-1.5 block">
                        Target URL <span className="text-red-500">*</span>
                      </label>
                      <Input
                        placeholder="https://example.com"
                        value={targetUrl}
                        onChange={(e) => setTargetUrl(e.target.value)}
                        className="border-slate-200 focus:border-indigo-300 focus:ring-indigo-200"
                      />
                      <p className="text-xs text-slate-500 mt-1">
                        {executionMode === 'http'
                          ? 'The backend will make real HTTP requests to this URL to test your application.'
                          : 'A headless Chromium browser will navigate to this URL and interact with the page.'}
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>

              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-900">Generated Test Cases</h2>
                <Button
                  onClick={handleExecuteTests}
                  disabled={isExecuting || testCases.length === 0 || (executionMode !== 'ai' && !targetUrl.trim())}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white"
                >
                  {isExecuting ? (
                    <>
                      <Loader2 className="animate-spin" size={18} />
                      {executionMode === 'ai' ? 'Simulating...' : executionMode === 'http' ? 'Testing via HTTP...' : 'Testing via Browser...'}
                    </>
                  ) : (
                    <>
                      <Play size={18} />
                      Execute All Tests
                    </>
                  )}
                </Button>
              </div>

              {testCases.map((tc) => (
                <Card key={tc.id} className="overflow-hidden">
                  <CardHeader className="pb-3">
                    <div className="flex items-center gap-3">
                      {getTypeBadge(tc.type)}
                      <CardTitle className="text-base">{tc.title}</CardTitle>
                    </div>
                    <CardDescription className="mt-2">{tc.description}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      <div>
                        <p className="text-sm font-medium text-slate-700 mb-2">Steps:</p>
                        <ol className="space-y-1.5">
                          {tc.steps.map((step, idx) => (
                            <li key={idx} className="flex gap-2 text-sm text-slate-600">
                              <span className="text-indigo-500 font-medium shrink-0">{idx + 1}.</span>
                              {step}
                            </li>
                          ))}
                        </ol>
                      </div>
                      <Separator />
                      <div>
                        <p className="text-sm font-medium text-slate-700 mb-1">Expected Result:</p>
                        <p className="text-sm text-slate-600 bg-slate-50 rounded-md p-3">{tc.expected_result}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* Results Tab */}
          <TabsContent value="results">
            <div className="space-y-6">
              {/* Execution Mode Banner */}
              {executionModeLabel && (
                <div className="p-3 bg-indigo-50 border border-indigo-200 rounded-lg flex items-center gap-2">
                  {executionMode === 'ai' ? <Cpu size={16} className="text-indigo-600" /> :
                   executionMode === 'http' ? <Globe size={16} className="text-emerald-600" /> :
                   <Monitor size={16} className="text-purple-600" />}
                  <span className="text-sm font-medium text-slate-700">Execution Mode: {executionModeLabel}</span>
                  {targetUrl && executionMode !== 'ai' && (
                    <span className="text-sm text-slate-500">| Target: {targetUrl}</span>
                  )}
                </div>
              )}

              {/* Summary Cards */}
              {summary && (
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  <Card className="bg-slate-50">
                    <CardContent className="p-4 text-center">
                      <p className="text-2xl font-bold text-slate-900">{summary.total}</p>
                      <p className="text-xs text-slate-500 mt-1">Total Tests</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-emerald-50 border-emerald-100">
                    <CardContent className="p-4 text-center">
                      <p className="text-2xl font-bold text-emerald-700">{summary.passed}</p>
                      <p className="text-xs text-emerald-600 mt-1">Passed</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-red-50 border-red-100">
                    <CardContent className="p-4 text-center">
                      <p className="text-2xl font-bold text-red-700">{summary.failed}</p>
                      <p className="text-xs text-red-600 mt-1">Failed</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-amber-50 border-amber-100">
                    <CardContent className="p-4 text-center">
                      <p className="text-2xl font-bold text-amber-700">{summary.errored}</p>
                      <p className="text-xs text-amber-600 mt-1">Errors</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-indigo-50 border-indigo-100">
                    <CardContent className="p-4 text-center">
                      <p className="text-2xl font-bold text-indigo-700">{summary.pass_rate}</p>
                      <p className="text-xs text-indigo-600 mt-1">Pass Rate</p>
                    </CardContent>
                  </Card>
                </div>
              )}

              {/* Detailed Results */}
              <div className="space-y-4">
                <h2 className="text-lg font-semibold text-slate-900">Detailed Results</h2>
                {testResults.map((result) => (
                  <Card key={result.test_case_id} className="overflow-hidden">
                    <div
                      className="flex items-center gap-3 p-4 cursor-pointer hover:bg-slate-50 transition-colors"
                      onClick={() => toggleResultExpanded(result.test_case_id)}
                    >
                      {getStatusIcon(result.status)}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-sm text-slate-900">{result.test_case_title}</span>
                          {getTypeBadge(result.test_type)}
                          {getStatusBadge(result.status)}
                        </div>
                        <p className="text-xs text-slate-500 mt-1 truncate">{result.actual_result}</p>
                      </div>
                      {expandedResults.has(result.test_case_id) ? (
                        <ChevronUp className="text-slate-400 shrink-0" size={18} />
                      ) : (
                        <ChevronDown className="text-slate-400 shrink-0" size={18} />
                      )}
                    </div>

                    {expandedResults.has(result.test_case_id) && (
                      <div className="border-t bg-slate-50/50">
                        <div className="p-4 space-y-4">
                          <div>
                            <p className="text-sm font-medium text-slate-700 mb-1">Details</p>
                            <p className="text-sm text-slate-600">{result.details}</p>
                          </div>
                          <Separator />
                          <div>
                            <p className="text-sm font-medium text-slate-700 mb-2">Step-by-Step Execution</p>
                            <div className="space-y-2">
                              {result.steps_executed.map((step, idx) => (
                                <div
                                  key={idx}
                                  className={`flex items-start gap-3 p-3 rounded-lg border ${
                                    step.status === 'PASS'
                                      ? 'bg-emerald-50/50 border-emerald-100'
                                      : step.status === 'FAIL'
                                      ? 'bg-red-50/50 border-red-100'
                                      : 'bg-amber-50/50 border-amber-100'
                                  }`}
                                >
                                  {step.status === 'PASS' ? (
                                    <CheckCircle2 className="text-emerald-500 mt-0.5 shrink-0" size={16} />
                                  ) : step.status === 'FAIL' ? (
                                    <XCircle className="text-red-500 mt-0.5 shrink-0" size={16} />
                                  ) : (
                                    <AlertTriangle className="text-amber-500 mt-0.5 shrink-0" size={16} />
                                  )}
                                  <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium text-slate-800">{step.step}</p>
                                    <p className="text-xs text-slate-500 mt-0.5">{step.output}</p>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </main>

      {/* Footer */}
      <footer className="border-t bg-white/60 mt-12">
        <div className="max-w-6xl mx-auto px-4 py-4 text-center text-sm text-slate-500">
          AI Test Automation - Powered by Google Gemini
        </div>
      </footer>
    </div>
  )
}

export default App
