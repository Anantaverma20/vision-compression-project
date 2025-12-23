"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Upload, Send, FileText, Loader2, AlertCircle, CheckCircle2 } from "lucide-react"

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"

interface Message {
  role: "user" | "assistant"
  content: string
}

interface RetrievedPage {
  page: number
  memory_id: string
  excerpt: string
  full_content?: string
}

interface IngestResult {
  doc_id: string
  pages_total: number
  pages_ingested: number
  failed_pages: Array<{ page: number; error: string }>
}

interface DocIngestResult {
  doc_id: string
  pages_total: number
  pages_ingested: number
  failed_pages: Array<{ page: number; error: string }>
}

interface CorpusIngestResult {
  corpus_id: string
  docs: DocIngestResult[]
  total_pages: number
  eval_status?: string
  eval_run_id?: string
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [isMultiMode, setIsMultiMode] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [ingestResult, setIngestResult] = useState<IngestResult | null>(null)
  const [corpusIngestResult, setCorpusIngestResult] = useState<CorpusIngestResult | null>(null)
  const [docId, setDocId] = useState<string | null>(null)
  const [corpusId, setCorpusId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [currentQuestion, setCurrentQuestion] = useState("")
  const [isAsking, setIsAsking] = useState(false)
  const [evidence, setEvidence] = useState<RetrievedPage[]>([])
  const [topK, setTopK] = useState(8)
  const [maxCharsPerPage, setMaxCharsPerPage] = useState(1500)
  const [backendStatus, setBackendStatus] = useState<"checking" | "online" | "offline">("checking")
  const [expandedEvidence, setExpandedEvidence] = useState<Set<number>>(new Set())
  const [evalResults, setEvalResults] = useState<any>(null)

  // Check backend status on mount
  useEffect(() => {
    const checkBackend = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/health`)
        if (response.ok) {
          setBackendStatus("online")
        } else {
          setBackendStatus("offline")
        }
      } catch (error) {
        setBackendStatus("offline")
      }
    }
    checkBackend()
  }, [])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      if (isMultiMode) {
        setFiles(Array.from(e.target.files))
        setFile(null) // Clear single file
      } else {
        setFile(e.target.files[0] || null)
        setFiles([]) // Clear multiple files
      }
    }
  }

  const handleIngest = async () => {
    if (!file) return

    setIsUploading(true)
    const formData = new FormData()
    formData.append("file", file)

    try {
      // First check if backend is reachable
      try {
        const healthCheck = await fetch(`${BACKEND_URL}/health`)
        if (!healthCheck.ok) {
          throw new Error(`Backend health check failed: ${healthCheck.status} ${healthCheck.statusText}`)
        }
      } catch (healthError) {
        throw new Error(`Cannot reach backend at ${BACKEND_URL}. Make sure the backend is running. Error: ${healthError instanceof Error ? healthError.message : "Network error"}`)
      }

      // Create AbortController for timeout
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 600000) // 10 minutes timeout

      let response: Response
      try {
        response = await fetch(`${BACKEND_URL}/ingest`, {
          method: "POST",
          body: formData,
          signal: controller.signal,
          // Don't set Content-Type header - browser will set it with boundary for multipart/form-data
        })
        clearTimeout(timeoutId)
      } catch (fetchError) {
        clearTimeout(timeoutId)
        // Check if it's a network error
        if (fetchError instanceof TypeError && fetchError.message.includes("Failed to fetch")) {
          throw new Error(`Network error: Cannot reach backend at ${BACKEND_URL}/ingest. This might be a CORS issue or the endpoint is not responding. Check browser console (F12) for details.`)
        }
        throw fetchError
      }

      if (!response.ok) {
        const errorText = await response.text()
        let errorMessage = `Upload failed: ${response.status} ${response.statusText}`
        try {
          const errorJson = JSON.parse(errorText)
          if (errorJson.detail) {
            errorMessage += ` - ${errorJson.detail}`
          }
        } catch {
          if (errorText) {
            errorMessage += ` - ${errorText}`
          }
        }
        throw new Error(errorMessage)
      }

      const data: IngestResult = await response.json()
      setIngestResult(data)
      setCorpusIngestResult(null) // Clear corpus result
      setDocId(data.doc_id)
      setCorpusId(null) // Clear corpus ID
      setMessages([])
      setEvidence([])
    } catch (error) {
      console.error("Error uploading file:", error)
      let errorMessage = "Unknown error"
      if (error instanceof Error) {
        if (error.name === "AbortError") {
          errorMessage = "Request timed out after 10 minutes. The PDF might be too large or processing is taking too long. Please check Cloud Run logs or try with a smaller PDF."
        } else if (error.message.includes("Failed to fetch") || error.message.includes("NetworkError")) {
          errorMessage = `Cannot connect to backend at ${BACKEND_URL}. Please check:
1. Is the backend URL correct in .env.local?
2. Is Cloud Run service running?
3. Check browser console (F12) for more details`
        } else {
          errorMessage = error.message
        }
      }
      alert(`Failed to upload file: ${errorMessage}`)
    } finally {
      setIsUploading(false)
    }
  }

  const handleCorpusIngest = async () => {
    if (files.length === 0) return

    setIsUploading(true)
    const formData = new FormData()
    
    // Append all files
    files.forEach((file) => {
      formData.append("files", file)
    })

    formData.append("auto_eval", "true")
    formData.append("eval_mode", "text_rag")  // or "optical", "hybrid", "all"
    formData.append("eval_judge", "rule")      // or "llm"
  

    try {
      // First check if backend is reachable
      try {
        const healthCheck = await fetch(`${BACKEND_URL}/health`)
        if (!healthCheck.ok) {
          throw new Error(`Backend health check failed: ${healthCheck.status} ${healthCheck.statusText}`)
        }
      } catch (healthError) {
        throw new Error(`Cannot reach backend at ${BACKEND_URL}. Make sure the backend is running. Error: ${healthError instanceof Error ? healthError.message : "Network error"}`)
      }

      // Create AbortController for timeout
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 600000) // 10 minutes timeout

      let response: Response
      try {
        response = await fetch(`${BACKEND_URL}/ingest-corpus`, {
          method: "POST",
          body: formData,
          signal: controller.signal,
        })
        clearTimeout(timeoutId)
      } catch (fetchError) {
        clearTimeout(timeoutId)
        if (fetchError instanceof TypeError && fetchError.message.includes("Failed to fetch")) {
          throw new Error(`Network error: Cannot reach backend at ${BACKEND_URL}/ingest-corpus. This might be a CORS issue or the endpoint is not responding. Check browser console (F12) for details.`)
        }
        throw fetchError
      }

      if (!response.ok) {
        const errorText = await response.text()
        let errorMessage = `Upload failed: ${response.status} ${response.statusText}`
        try {
          const errorJson = JSON.parse(errorText)
          if (errorJson.detail) {
            errorMessage += ` - ${errorJson.detail}`
          }
        } catch {
          if (errorText) {
            errorMessage += ` - ${errorText}`
          }
        }
        throw new Error(errorMessage)
      }

      const data: CorpusIngestResult = await response.json()
      setCorpusIngestResult(data)
      setIngestResult(null) // Clear single doc result
      setCorpusId(data.corpus_id)
      setDocId(null) // Clear single doc ID
      setMessages([])
      setEvidence([])
      
      // Show success message
      alert(`Corpus "${data.corpus_id}" created successfully!\n\n${data.docs.length} documents processed\n${data.total_pages} total pages ingested`)
    } catch (error) {
      console.error("Error uploading files:", error)
      let errorMessage = "Unknown error"
      if (error instanceof Error) {
        if (error.name === "AbortError") {
          errorMessage = "Request timed out after 10 minutes. The PDFs might be too large or processing is taking too long."
        } else if (error.message.includes("Failed to fetch") || error.message.includes("NetworkError")) {
          errorMessage = `Cannot connect to backend at ${BACKEND_URL}. Please check:
1. Is the backend URL correct in .env.local?
2. Is Cloud Run service running?
3. Check browser console (F12) for more details`
        } else {
          errorMessage = error.message
        }
      }
      alert(`Failed to upload files: ${errorMessage}`)
    } finally {
      setIsUploading(false)
    }
  }

  const [isLoadingEval, setIsLoadingEval] = useState(false)
  const [isRunningEval, setIsRunningEval] = useState(false)
  
  const runEvaluation = async (corpusId: string, mode: string = "text_rag") => {
    setIsRunningEval(true)
    try {
      const response = await fetch(`${BACKEND_URL}/run-eval/${corpusId}?mode=${mode}&judge=rule`, {
        method: 'POST'
      })
      if (response.ok) {
        const data = await response.json()
        alert(`Evaluation started! Status: ${data.status}\nRun ID: ${data.run_id || 'N/A'}\n\nResults will be available shortly. You can check back in a few moments.`)
        // Optionally fetch results after a delay
        setTimeout(() => {
          fetchEvalResults(corpusId)
        }, 2000)
      } else {
        const errorText = await response.text()
        alert(`Failed to start evaluation: ${response.status} ${response.statusText}\n\n${errorText}`)
      }
    } catch (error) {
      console.error("Failed to start evaluation:", error)
      alert(`Failed to start evaluation: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setIsRunningEval(false)
    }
  }
  
  const fetchEvalResults = async (corpusId: string) => {
    setIsLoadingEval(true)
    try {
      const response = await fetch(`${BACKEND_URL}/eval-results/${corpusId}`)
      if (response.ok) {
        const data = await response.json()
        // Check if results are not ready yet
        if (data.status === "not_ready") {
          // Set evalResults to show "not ready" message
          setEvalResults({ status: "not_ready", message: data.message })
        } else {
          setEvalResults(data)
          // Scroll to results only if we have actual results
          if (data.results || data.summary) {
            setTimeout(() => {
              const resultsElement = document.getElementById('eval-results')
              if (resultsElement) {
                resultsElement.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }
            }, 100)
          }
        }
      } else {
        const errorText = await response.text()
        alert(`Failed to fetch evaluation results: ${response.status} ${response.statusText}\n\n${errorText}`)
        setEvalResults(null)
      }
    } catch (error) {
      console.error("Failed to fetch eval results:", error)
      alert(`Failed to fetch evaluation results: ${error instanceof Error ? error.message : 'Unknown error'}`)
      setEvalResults(null)
    } finally {
      setIsLoadingEval(false)
    }
  }

  const handleAsk = async () => {
    // Check if we have either docId (single doc) or corpusId (multiple docs)
    if ((!docId && !corpusId) || !currentQuestion.trim()) return

    const question = currentQuestion.trim()
    const userMessage: Message = { role: "user", content: question }
    setMessages((prev) => [...prev, userMessage])
    setCurrentQuestion("")
    setIsAsking(true)
    setExpandedEvidence(new Set()) // Reset expanded evidence

    try {
      // Build request body - use corpus_id if available, otherwise doc_id
      const requestBody: {
        doc_id?: string
        corpus_id?: string
        question: string
        top_k: number
        max_chars_per_page: number
      } = {
        question: question,
        top_k: topK,
        max_chars_per_page: maxCharsPerPage,
      }

      if (corpusId) {
        requestBody.corpus_id = corpusId
      } else if (docId) {
        requestBody.doc_id = docId
      }

      const response = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
      })

      if (!response.ok) {
        const errorText = await response.text()
        let errorMessage = `Chat failed: ${response.status} ${response.statusText}`
        try {
          const errorJson = JSON.parse(errorText)
          if (errorJson.detail) {
            errorMessage += ` - ${errorJson.detail}`
          }
        } catch {
          if (errorText) {
            errorMessage += ` - ${errorText}`
          }
        }
        throw new Error(errorMessage)
      }

      const data = await response.json()
      const assistantMessage: Message = { role: "assistant", content: data.answer_md }
      setMessages((prev) => [...prev, assistantMessage])
      setEvidence(data.retrieved || [])
    } catch (error) {
      console.error("Error asking question:", error)
      const errorMessage: Message = {
        role: "assistant",
        content: `Error: ${error instanceof Error ? error.message : "Failed to get response"}`,
      }
      setMessages((prev) => [...prev, errorMessage])
    } finally {
      setIsAsking(false)
    }
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold">Vision Compression Document Chat</h1>
            <div className="flex items-center gap-2 text-sm">
              {backendStatus === "checking" && (
                <>
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  <span className="text-muted-foreground">Checking backend...</span>
                </>
              )}
              {backendStatus === "online" && (
                <>
                  <CheckCircle2 className="h-4 w-4 text-green-600" />
                  <span className="text-green-600">Backend online</span>
                </>
              )}
              {backendStatus === "offline" && (
                <>
                  <AlertCircle className="h-4 w-4 text-red-600" />
                  <span className="text-red-600">Backend offline</span>
                  <span className="text-muted-foreground text-xs">({BACKEND_URL})</span>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-6 space-y-6">
        {/* Upload Card */}
        <Card>
          <CardHeader>
            <CardTitle>Upload Document{isMultiMode ? "s" : ""}</CardTitle>
            <CardDescription>
              {isMultiMode 
                ? "Upload multiple PDF files to create a corpus" 
                : "Upload a PDF file to process and ingest"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-2 mb-2">
              <input
                type="checkbox"
                id="multi-mode"
                checked={isMultiMode}
                onChange={(e) => {
                  setIsMultiMode(e.target.checked)
                  setFile(null)
                  setFiles([])
                  setIngestResult(null)
                  setCorpusIngestResult(null)
                }}
                className="w-4 h-4"
              />
              <label htmlFor="multi-mode" className="text-sm cursor-pointer">
                Upload multiple PDFs (create corpus)
              </label>
            </div>
            <div className="flex gap-4">
              <Input
                type="file"
                accept=".pdf"
                multiple={isMultiMode}
                onChange={handleFileChange}
                disabled={isUploading}
                className="flex-1"
              />
              <Button
                onClick={isMultiMode ? handleCorpusIngest : handleIngest}
                disabled={isMultiMode ? files.length === 0 : !file || isUploading}
              >
                {isUploading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <Upload className="mr-2 h-4 w-4" />
                    {isMultiMode ? `Process ${files.length} File${files.length !== 1 ? 's' : ''}` : "Process & Ingest"}
                  </>
                )}
              </Button>
            </div>
            {isMultiMode && files.length > 0 && (
              <div className="text-sm text-muted-foreground">
                Selected: {files.length} file{files.length !== 1 ? 's' : ''} ({files.map(f => f.name).join(", ")})
              </div>
            )}

            {ingestResult && (
              <div className="mt-4 p-4 bg-muted rounded-md space-y-2">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  <span className="font-semibold">Document ID:</span>
                  <code className="px-2 py-1 bg-background rounded text-sm">{ingestResult.doc_id}</code>
                </div>
                <div>
                  <span className="font-semibold">Pages:</span>{" "}
                  {ingestResult.pages_ingested} / {ingestResult.pages_total} ingested
                </div>
                {ingestResult.failed_pages.length > 0 && (
                  <div className="mt-2 p-3 bg-destructive/10 rounded-md border border-destructive/20">
                    <span className="font-semibold text-destructive">Failed Pages ({ingestResult.failed_pages.length}):</span>
                    <ul className="list-disc list-inside mt-2 space-y-1">
                      {ingestResult.failed_pages.map((fp) => (
                        <li key={fp.page} className="text-sm">
                          <span className="font-medium">Page {fp.page}:</span>{" "}
                          <span className="text-muted-foreground">{fp.error}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {corpusIngestResult && (
              <div className="mt-4 p-4 bg-muted rounded-md space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    <span className="font-semibold">Corpus ID:</span>
                    <code className="px-2 py-1 bg-background rounded text-sm">{corpusIngestResult.corpus_id}</code>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="default"
                      size="sm"
                      onClick={() => runEvaluation(corpusIngestResult.corpus_id, "text_rag")}
                      disabled={isRunningEval || isLoadingEval}
                    >
                      {isRunningEval ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Running...
                        </>
                      ) : (
                        "Run Evaluation"
                      )}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => fetchEvalResults(corpusIngestResult.corpus_id)}
                      disabled={isLoadingEval || isRunningEval}
                    >
                      {isLoadingEval ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Loading...
                        </>
                      ) : (
                        "View Results"
                      )}
                    </Button>
                  </div>
                </div>
                <div>
                  <span className="font-semibold">Total:</span>{" "}
                  {corpusIngestResult.docs.length} document{corpusIngestResult.docs.length !== 1 ? 's' : ''}, {corpusIngestResult.total_pages} pages ingested
                </div>
                <div className="space-y-2">
                  <span className="font-semibold">Documents:</span>
                  {corpusIngestResult.docs.map((doc, idx) => (
                    <div key={idx} className="pl-4 border-l-2 border-primary/20">
                      <div className="text-sm">
                        <span className="font-medium">Doc {idx + 1}:</span>{" "}
                        <code className="px-1 py-0.5 bg-background rounded text-xs">{doc.doc_id}</code>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {doc.pages_ingested} / {doc.pages_total} pages
                        {doc.failed_pages.length > 0 && (
                          <>
                            <span className="text-destructive ml-2">
                              ({doc.failed_pages.length} failed)
                            </span>
                            <div className="mt-1 p-2 bg-destructive/10 rounded border border-destructive/20">
                              <span className="font-semibold text-destructive text-xs">Failed Pages:</span>
                              <ul className="list-disc list-inside mt-1 space-y-0.5">
                                {doc.failed_pages.map((fp) => (
                                  <li key={fp.page} className="text-xs">
                                    <span className="font-medium">Page {fp.page}:</span>{" "}
                                    <span className="text-muted-foreground">{fp.error}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Main Layout: Chat + Evidence */}
        {(docId || corpusId) && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left: Chat */}
            <Card className="flex flex-col">
              <CardHeader>
                <CardTitle>Chat</CardTitle>
                <CardDescription>
                  {corpusId 
                    ? "Ask questions about the documents in the corpus" 
                    : "Ask questions about the document"}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col space-y-4">
                {/* Chat History */}
                <div className="flex-1 overflow-y-auto space-y-4 min-h-[400px] max-h-[600px] border rounded-md p-4 bg-muted/30">
                  {messages.length === 0 ? (
                    <div className="text-center text-muted-foreground py-8">
                      Start a conversation by asking a question about the document.
                    </div>
                  ) : (
                    messages.map((msg, idx) => (
                      <div
                        key={idx}
                        className={`flex ${
                          msg.role === "user" ? "justify-end" : "justify-start"
                        }`}
                      >
                        <div
                          className={`max-w-[80%] rounded-lg p-3 ${
                            msg.role === "user"
                              ? "bg-primary text-primary-foreground"
                              : "bg-card border"
                          }`}
                        >
                          {msg.role === "assistant" ? (
                            <div className="prose prose-sm max-w-none dark:prose-invert">
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {msg.content}
                              </ReactMarkdown>
                            </div>
                          ) : (
                            <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                  {isAsking && (
                    <div className="flex justify-start">
                      <div className="bg-card border rounded-lg p-3">
                        <Loader2 className="h-4 w-4 animate-spin" />
                      </div>
                    </div>
                  )}
                </div>

                {/* Chat Input */}
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <Textarea
                      value={currentQuestion}
                      onChange={(e) => setCurrentQuestion(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault()
                          handleAsk()
                        }
                      }}
                      placeholder="Ask a question about the document..."
                      disabled={isAsking}
                      rows={3}
                      className="flex-1"
                    />
                    <Button
                      onClick={handleAsk}
                      disabled={!currentQuestion.trim() || isAsking}
                      size="icon"
                      className="self-end"
                    >
                      <Send className="h-4 w-4" />
                    </Button>
                  </div>
                  <div className="flex gap-4 text-sm text-muted-foreground">
                    <label className="flex items-center gap-2">
                      Top K:
                      <Input
                        type="number"
                        min={1}
                        max={50}
                        value={topK}
                        onChange={(e) => setTopK(parseInt(e.target.value) || 8)}
                        className="w-20 h-8"
                      />
                    </label>
                    <label className="flex items-center gap-2">
                      Max Chars/Page:
                      <Input
                        type="number"
                        min={100}
                        max={10000}
                        value={maxCharsPerPage}
                        onChange={(e) => setMaxCharsPerPage(parseInt(e.target.value) || 1500)}
                        className="w-32 h-8"
                      />
                    </label>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Right: Evidence Panel */}
            <Card>
              <CardHeader>
                <CardTitle>Evidence & Proof</CardTitle>
                <CardDescription>Retrieved pages from the document with full text proof</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3 max-h-[700px] overflow-y-auto">
                  {evidence.length === 0 ? (
                    <div className="text-center text-muted-foreground py-8">
                      No evidence retrieved yet. Ask a question to see relevant pages.
                    </div>
                  ) : (
                    evidence.map((item, idx) => {
                      const isExpanded = expandedEvidence.has(idx)
                      const displayContent = isExpanded && item.full_content ? item.full_content : item.excerpt
                      
                      return (
                        <Card key={idx} className="bg-muted/50">
                          <CardContent className="p-4">
                            <div className="flex items-start justify-between mb-2">
                              <span className="font-semibold text-sm">Page {item.page}</span>
                              <div className="flex items-center gap-2">
                                <code className="text-xs bg-background px-2 py-1 rounded">
                                  {item.memory_id.slice(0, 8)}...
                                </code>
                                {item.full_content && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => {
                                      const newExpanded = new Set(expandedEvidence)
                                      if (isExpanded) {
                                        newExpanded.delete(idx)
                                      } else {
                                        newExpanded.add(idx)
                                      }
                                      setExpandedEvidence(newExpanded)
                                    }}
                                    className="h-6 text-xs"
                                  >
                                    {isExpanded ? "Show Less" : "Show Full Text"}
                                  </Button>
                                )}
                              </div>
                            </div>
                            <div className="text-sm text-muted-foreground">
                              {isExpanded && item.full_content ? (
                                <div className="prose prose-sm max-w-none dark:prose-invert whitespace-pre-wrap bg-background/50 p-3 rounded border">
                                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                    {item.full_content}
                                  </ReactMarkdown>
                                </div>
                              ) : (
                                <p className="line-clamp-3">{item.excerpt}</p>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      )
                    })
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        )}
        
        {/* Evaluation Results */}
        {evalResults && (
          <Card id="eval-results" className="mt-6">
            <CardHeader>
              <CardTitle>Evaluation Results</CardTitle>
              <CardDescription>Quality scores and metrics for the corpus</CardDescription>
            </CardHeader>
            <CardContent>
              {evalResults.status === "not_ready" ? (
                <div className="text-muted-foreground">
                  <p>{evalResults.message || "No evaluation results available yet. Evaluation may still be running."}</p>
                  <p className="mt-2 text-sm">You can check back later or refresh the page.</p>
                </div>
              ) : evalResults.metadata && (
                <div className="mb-4 p-3 bg-muted rounded text-sm">
                  <div className="font-semibold mb-2">Evaluation Metadata</div>
                  <div className="space-y-1 text-muted-foreground">
                    {evalResults.metadata.run_timestamp && (
                      <div><strong>Run Time:</strong> {new Date(evalResults.metadata.run_timestamp).toLocaleString()}</div>
                    )}
                    {evalResults.metadata.questions_source && (
                      <div><strong>Questions Source:</strong> {evalResults.metadata.questions_source}</div>
                    )}
                    {evalResults.metadata.total_questions && (
                      <div><strong>Total Questions:</strong> {evalResults.metadata.total_questions}</div>
                    )}
                    {evalResults.metadata.modes_evaluated && (
                      <div><strong>Modes Evaluated:</strong> {evalResults.metadata.modes_evaluated.join(", ")}</div>
                    )}
                  </div>
                </div>
              )}
              {evalResults.summary ? (
                <div className="prose prose-sm max-w-none dark:prose-invert">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {evalResults.summary}
                  </ReactMarkdown>
                </div>
              ) : evalResults.results && Array.isArray(evalResults.results) && evalResults.results.length > 0 ? (
                <div className="space-y-4">
                  {evalResults.results.slice(0, 20).map((result: any, idx: number) => (
                    <div key={idx} className="p-3 bg-muted rounded border">
                      <div className="font-semibold text-sm mb-2">{result.question}</div>
                      <div className="text-xs space-y-1">
                        <div className="flex gap-4">
                          <div>Score: <span className="font-medium">{(result.judge?.score * 100 || 0).toFixed(1)}%</span></div>
                          <div>Citation: <span className="font-medium">{(result.judge?.citation_correctness * 100 || 0).toFixed(1)}%</span></div>
                          <div>Coverage: <span className="font-medium">{(result.judge?.coverage * 100 || 0).toFixed(1)}%</span></div>
                        </div>
                        {result.judge?.rationale && (
                          <div className="text-muted-foreground mt-2 text-xs">{result.judge.rationale}</div>
                        )}
                        {result.answer && (
                          <div className="mt-2 p-2 bg-background/50 rounded text-xs">
                            <div className="font-medium mb-1">Answer:</div>
                            <div className="prose prose-xs max-w-none">{result.answer}</div>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-muted-foreground">No evaluation results available yet. Evaluation may still be running.</div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

