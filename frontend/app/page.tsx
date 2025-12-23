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
}

interface IngestResult {
  doc_id: string
  pages_total: number
  pages_ingested: number
  failed_pages: Array<{ page: number; error: string }>
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [ingestResult, setIngestResult] = useState<IngestResult | null>(null)
  const [docId, setDocId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [currentQuestion, setCurrentQuestion] = useState("")
  const [isAsking, setIsAsking] = useState(false)
  const [evidence, setEvidence] = useState<RetrievedPage[]>([])
  const [topK, setTopK] = useState(8)
  const [maxCharsPerPage, setMaxCharsPerPage] = useState(1500)
  const [backendStatus, setBackendStatus] = useState<"checking" | "online" | "offline">("checking")

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
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
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
      setDocId(data.doc_id)
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

  const handleAsk = async () => {
    if (!docId || !currentQuestion.trim()) return

    const question = currentQuestion.trim()
    const userMessage: Message = { role: "user", content: question }
    setMessages((prev) => [...prev, userMessage])
    setCurrentQuestion("")
    setIsAsking(true)

    try {
      const response = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          doc_id: docId,
          question: question,
          top_k: topK,
          max_chars_per_page: maxCharsPerPage,
        }),
      })

      if (!response.ok) {
        throw new Error(`Chat failed: ${response.statusText}`)
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
            <CardTitle>Upload Document</CardTitle>
            <CardDescription>Upload a PDF file to process and ingest</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-4">
              <Input
                type="file"
                accept=".pdf"
                onChange={handleFileChange}
                disabled={isUploading}
                className="flex-1"
              />
              <Button
                onClick={handleIngest}
                disabled={!file || isUploading}
              >
                {isUploading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <Upload className="mr-2 h-4 w-4" />
                    Process & Ingest
                  </>
                )}
              </Button>
            </div>

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
                  <div className="mt-2">
                    <span className="font-semibold text-destructive">Failed Pages:</span>
                    <ul className="list-disc list-inside mt-1">
                      {ingestResult.failed_pages.map((fp) => (
                        <li key={fp.page} className="text-sm">
                          Page {fp.page}: {fp.error}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Main Layout: Chat + Evidence */}
        {docId && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left: Chat */}
            <Card className="flex flex-col">
              <CardHeader>
                <CardTitle>Chat</CardTitle>
                <CardDescription>Ask questions about the document</CardDescription>
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
                <CardTitle>Evidence</CardTitle>
                <CardDescription>Retrieved pages from the document</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3 max-h-[700px] overflow-y-auto">
                  {evidence.length === 0 ? (
                    <div className="text-center text-muted-foreground py-8">
                      No evidence retrieved yet. Ask a question to see relevant pages.
                    </div>
                  ) : (
                    evidence.map((item, idx) => (
                      <Card key={idx} className="bg-muted/50">
                        <CardContent className="p-4">
                          <div className="flex items-start justify-between mb-2">
                            <span className="font-semibold text-sm">Page {item.page}</span>
                            <code className="text-xs bg-background px-2 py-1 rounded">
                              {item.memory_id.slice(0, 8)}...
                            </code>
                          </div>
                          <p className="text-sm text-muted-foreground line-clamp-3">
                            {item.excerpt}
                          </p>
                        </CardContent>
                      </Card>
                    ))
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}

