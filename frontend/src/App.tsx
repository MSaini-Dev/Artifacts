import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  Activity,
  Brain,
  Check,
  ChevronDown,
  CircleAlert,
  Clock3,
  Code2,
  Cpu,
  Database,
  FilePlus2,
  GitBranch,
  History,
  KeyRound,
  LoaderCircle,
  Maximize2,
  MessageSquare,
  Minimize2,
  MoreHorizontal,
  Moon,
  Network,
  PanelLeft,
  Pencil,
  Play,
  Plus,
  Copy,
  RefreshCw,
  ScrollText,
  Search,
  Send,
  Server,
  Sun,
  Trash2,
  Wrench,
  type LucideIcon,
} from "lucide-react"
import { useTheme } from "next-themes"
import { toast } from "sonner"
import {
  apiRequest,
  jsonBody,
  type ApiKey,
  type ChatMessage,
  type Conversation,
  type LogConversation,
  type LogDetails,
  type LogExecutionRecord,
  type LogInteractive,
  type Model,
  type Provider,
  type SystemStats,
  type LogTask,
  type LogToolExecution,
  type ToolInfo,
} from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { Toaster } from "@/components/ui/sonner"
import WorkflowPage from "@/components/WorkflowPage"
import MeshPage from "@/components/MeshPage"
import "./components/MeshPage.css"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

type Page = "chat" | "mesh" | "tools" | "db" | "logs" | "flow"
type EntityKind = "provider" | "model" | "key"
type EntityRecord = Provider | Model | ApiKey
type EntityForm = Record<string, string>
type LogViewMode = "simple" | "full"
type LoggedToolCall = { id?: string; name: string; arguments: unknown }
type LoggedToolResult = { id: string; name?: string; content: unknown }
type ConversationActivity = { interaction_id: number | null; tools: LogToolExecution[] }
type ActivitySocketEvent = {
  type: "snapshot" | "tool_update" | "pong"
  interaction_id?: number
  tools?: LogToolExecution[]
  tool?: LogToolExecution
}

const navigation: { id: Page; label: string; icon: LucideIcon }[] = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "mesh", label: "Mesh", icon: Network },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "db", label: "Database", icon: Database },
  { id: "logs", label: "Logs", icon: ScrollText },
  { id: "flow", label: "Flow", icon: GitBranch },
]

function pageFromHash(): Page {
  const hash = window.location.hash.slice(1)
  return navigation.find(({ id }) => id === hash)?.id ?? "chat"
}

const pageCopy: Record<Page, { title: string; description: string }> = {
  chat: { title: "Chat", description: "Talk to your assistant or hand off a task." },
  mesh: { title: "Mesh", description: "A split workspace with a dedicated assistant chat." },
  tools: { title: "Tools", description: "Inspect registered tools and run them on demand." },
  db: { title: "Database", description: "Manage providers, models, and environment key references." },
  logs: { title: "Execution logs", description: "Trace conversations, LLM tasks, retries, and tool executions." },
  flow: { title: "Project flow", description: "Explore the main API routing and recovery path." },
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function formatTime(value?: string): string {
  if (!value) return ""
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" })
}

function formatPayload(payload: string | null | undefined): string {
  if (!payload) return "No payload was recorded."
  try {
    return JSON.stringify(JSON.parse(payload), null, 2)
  } catch {
    return payload
  }
}

function getToolCalls(response: string | null): LoggedToolCall[] {
  if (!response) return []
  let parsed: unknown
  try {
    parsed = JSON.parse(response)
  } catch {
    return []
  }

  const entries = Array.isArray(parsed)
    ? parsed
    : typeof parsed === "object" && parsed !== null && "tool_calls" in parsed && Array.isArray(parsed.tool_calls)
      ? parsed.tool_calls
      : []

  return entries.flatMap((entry): LoggedToolCall[] => {
    if (typeof entry !== "object" || entry === null) return []
    const item = entry as Record<string, unknown>
    const functionInfo =
      typeof item.function === "object" && item.function !== null
        ? item.function as Record<string, unknown>
        : null
    const name = item.name ?? functionInfo?.name
    if (typeof name !== "string" || !name) return []

    let args: unknown = item.arguments ?? item.args ?? functionInfo?.arguments ?? {}
    if (typeof args === "string") {
      try {
        args = JSON.parse(args) as unknown
      } catch {
        // Keep malformed arguments visible instead of hiding the requested tool call.
      }
    }

    return [{
      id: typeof item.id === "string" ? item.id : undefined,
      name,
      arguments: args,
    }]
  })
}

function getToolResults(tasks: LogTask[]): LoggedToolResult[] {
  const results = new Map<string, LoggedToolResult>()
  for (const task of tasks) {
    for (const call of task.api_calls || []) {
      if (!call.Payload) continue
      let payload: unknown
      try {
        payload = JSON.parse(call.Payload)
      } catch {
        continue
      }
      if (typeof payload !== "object" || payload === null || !("messages" in payload) || !Array.isArray(payload.messages)) {
        continue
      }
      for (const message of payload.messages) {
        if (
          typeof message !== "object" ||
          message === null ||
          !("role" in message) ||
          message.role !== "tool" ||
          !("tool_call_id" in message) ||
          typeof message.tool_call_id !== "string"
        ) {
          continue
        }
        const toolMessage = message as Record<string, unknown>
        if (!results.has(message.tool_call_id)) {
          results.set(message.tool_call_id, {
            id: message.tool_call_id,
            name: typeof toolMessage.name === "string" ? toolMessage.name : undefined,
            content: toolMessage.content ?? "",
          })
        }
      }
    }
  }
  return [...results.values()]
}

function displayToolValue(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2)
}

function cleanRestoredUserMessage(content: string): string {
  let text = content.trim()
  const transcriptMarkers = [...text.matchAll(/(?:^|\n)\s*User:\s*/g)]
  const hasAssistantTurn = /(?:^|\n)\s*Assistant:\s*/.test(text)

  if (hasAssistantTurn && transcriptMarkers.length > 0) {
    const lastMarker = transcriptMarkers[transcriptMarkers.length - 1]
    const markerEnd = (lastMarker.index ?? 0) + lastMarker[0].length
    text = text.slice(markerEnd).trim()
  }

  return text.replace(/^(?:User:\s*)+/i, "").trim()
}

function normalizeRestoredMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages.map((message) =>
    message.role === "user"
      ? { ...message, content: cleanRestoredUserMessage(message.content) }
      : message,
  )
}

function StatusBadge({ status }: { status: string }) {
  const variant = ["disabled", "Failed", "error"].includes(status)
    ? "destructive"
    : ["active", "Final", "Success", "valid"].includes(status)
      ? "default"
      : "secondary"

  return <Badge variant={variant}>{status}</Badge>
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string
  htmlFor: string
  children: ReactNode
}) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  )
}

function getExecutionRecords(interactive: LogInteractive): LogExecutionRecord[] {
  if (interactive.execution_records) return interactive.execution_records
  const tasks = interactive.tasks ?? (interactive.iterations || []).map((iteration) => {
    const calls = iteration.api_calls || []
    const successfulCalls = calls.filter((call) => call.Request_Status === "Success")
    const durations = calls.flatMap((call) => call.Duration == null ? [] : [call.Duration])
    return {
      ID: iteration.ID,
      Name: "LLM API",
      Model: calls.slice().reverse().find((call) => call.Model)?.Model ?? null,
      Timestamp: calls[0]?.Timestamp ?? interactive.Created_At,
      Duration_Seconds: durations.length ? durations.reduce((sum, duration) => sum + duration, 0) : null,
      Status: calls.some((call) => call.Is_Complete === 0)
        ? "Running" as const
        : successfulCalls.length
          ? "Success" as const
          : "Failed" as const,
      Request: calls.find((call) => call.Payload)?.Payload ?? null,
      Final_Response: successfulCalls.slice().reverse().find((call) => call.Response)?.Response ?? null,
      api_calls: calls,
    }
  })

  return tasks.map((task) => ({
    type: "task",
    Timestamp: task.Timestamp,
    ID: task.ID,
    task,
  }))
}

function TaskExecutionCard({
  task,
  index,
  toolExecutions,
  toolResults,
}: {
  task: LogTask
  index: number
  toolExecutions: LogToolExecution[]
  toolResults: LoggedToolResult[]
}) {
  const calls = task.api_calls || []
  const successfulCount = calls.filter((call) => call.Is_Complete !== 0 && call.Request_Status === "Success").length
  const failedCount = calls.filter((call) => call.Is_Complete !== 0 && call.Request_Status === "Failed").length
  const runningCount = calls.length - successfulCount - failedCount
  const requestedTools = getToolCalls(task.Final_Response)
  const matchedToolIds = new Set<number>()
  const toolCalls = requestedTools.map((call) => {
    const execution = toolExecutions.find((tool) =>
      !matchedToolIds.has(tool.ID) && (
        (call.id != null && tool.Tool_Call_Id === call.id) ||
        (call.id == null && tool.Name === call.name)
      ),
    )
    if (execution) matchedToolIds.add(execution.ID)
    const requestResult = call.id
      ? toolResults.find((result) => result.id === call.id)
      : undefined
    return { call, execution, requestResult }
  })
  const unmatchedExecutions = toolExecutions.filter((tool) => !matchedToolIds.has(tool.ID))

  return (
    <details className="grid gap-2">
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 rounded-md py-1">
        <span className="flex flex-wrap items-center gap-2">
          <Activity className="size-4 text-muted-foreground" />
          <span className="font-medium">Task {index + 1} · {task.Name || "LLM API"}</span>
          <StatusBadge status={task.Status} />
          <span className="text-xs text-muted-foreground">
            {calls.length} attempt{calls.length === 1 ? "" : "s"} · {successfulCount} succeeded · {failedCount} failed{runningCount ? ` · ${runningCount} running` : ""}{toolExecutions.length ? ` · ${toolExecutions.length} tool${toolExecutions.length === 1 ? "" : "s"}` : ""}
          </span>
        </span>
        <span className="text-xs text-muted-foreground">
          {formatTime(task.Timestamp)} · {task.Duration_Seconds == null ? "Duration not recorded" : `${task.Duration_Seconds.toFixed(2)} sec`}
        </span>
      </summary>
      <article className="grid gap-4 rounded-lg border p-3 sm:p-4">
        {task.Model && <p className="text-xs text-muted-foreground">Model: {task.Model} · Task #{task.ID}</p>}
        <div className="grid gap-2">
          <p className="text-xs font-medium text-muted-foreground">Request</p>
          <pre className="max-h-64 min-h-16 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/40 p-3 font-mono text-xs leading-5">
            {task.Request ? formatPayload(task.Request) : "No request payload was recorded."}
          </pre>
        </div>
        <div className="grid gap-2">
          <p className="text-xs font-medium text-muted-foreground">Final response from the last successful attempt</p>
          <pre className="max-h-64 min-h-16 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/40 p-3 font-mono text-xs leading-5">
            {task.Final_Response ?? (task.Status === "Running" ? "Task is still running." : "No successful response was recorded.")}
          </pre>
        </div>
        {(toolCalls.length > 0 || unmatchedExecutions.length > 0) && (
          <div className="grid gap-2">
            <p className="text-xs font-medium text-muted-foreground">
              Tool calls ({toolCalls.length + unmatchedExecutions.length})
            </p>
            {toolCalls.map(({ call, execution, requestResult }, toolIndex) => {
              const storedResponse = execution?.Response
              const responseFromRequest = storedResponse ? null : requestResult
              const responseText = execution?.Error
                ?? storedResponse
                ?? (responseFromRequest ? displayToolValue(responseFromRequest.content) : null)
              return (
                <details key={call.id || `${call.name}-${toolIndex}`} className="rounded-md border px-3 py-2">
                  <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2">
                    <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      <Wrench className="size-4 text-muted-foreground" />
                      {call.name}
                      {execution && <StatusBadge status={execution.Status} />}
                    </span>
                    {execution?.Duration != null && (
                      <span className="text-xs text-muted-foreground">{execution.Duration.toFixed(2)} sec</span>
                    )}
                  </summary>
                  <div className="mt-3 grid gap-3">
                    <div className="grid gap-2">
                      <p className="text-xs font-medium text-muted-foreground">Parameters</p>
                      <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/50 p-3 font-mono text-xs">
                        {typeof call.arguments === "string" ? call.arguments : JSON.stringify(call.arguments, null, 2)}
                      </pre>
                    </div>
                    <div className="grid gap-2">
                      <p className="text-xs font-medium text-muted-foreground">
                        {execution?.Status === "Failed" && execution.Error
                          ? "Tool error"
                          : responseFromRequest
                            ? `Tool response · recorded in Task request${responseFromRequest.name ? ` (${responseFromRequest.name})` : ""}`
                            : "Tool response"}
                      </p>
                      <pre className="max-h-64 min-h-16 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/50 p-3 font-mono text-xs">
                        {responseText ?? (
                          execution?.Status === "Running"
                            ? "Tool is still running."
                            : "No tool response was recorded."
                        )}
                      </pre>
                    </div>
                  </div>
                </details>
              )
            })}
            {unmatchedExecutions.map((tool) => (
              <ToolExecutionCard key={tool.ID} tool={tool} />
            ))}
          </div>
        )}
        <div className="grid gap-2">
          <p className="text-xs font-medium text-muted-foreground">Iterations ({calls.length})</p>
          {calls.map((call, attemptIndex) => (
            <details key={call.API_Call_Id} className="rounded-md border px-3 py-2">
              <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2">
                <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
                  Iteration {attemptIndex + 1}
                  {call.Final_Response === 1 && <Badge>Final</Badge>}
                  <StatusBadge status={call.Is_Complete === 0 ? "Running" : call.Request_Status} />
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatTime(call.Timestamp)} · {call.Duration == null ? "Duration not recorded" : `${call.Duration.toFixed(2)} sec`}
                </span>
              </summary>
              <div className="mt-3 grid gap-3">
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span>API call #{call.API_Call_Id}</span>
                  {call.Model && <span>{call.Model}</span>}
                  {call.API_Name && <span>{call.API_Name}</span>}
                  {call.URL && <span className="max-w-full truncate">{call.URL}</span>}
                  {call.Legacy_Record ? <span>Approximate legacy timestamp</span> : null}
                </div>
                <div className="grid gap-2">
                  <p className="text-xs font-medium text-muted-foreground">API response or error</p>
                  <pre className="max-h-64 min-h-16 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/50 p-3 font-mono text-xs">
                    {call.Response ?? (call.Is_Complete === 0 ? "Attempt is still running." : "No response was recorded.")}
                  </pre>
                </div>
                {(call.Recovery_Request || call.Recovery_Action || call.Recovery_Mode || call.Wait_Duration_Seconds != null) && (
                  <div className="grid gap-2 rounded-md bg-muted/50 p-3 text-xs">
                    <p className="font-medium">Recovery decision · {call.Recovery_Mode || "Parser"}</p>
                    <span>{call.Recovery_Action || "No action recorded"}</span>
                    {call.Recovery_Request && <pre className="overflow-auto whitespace-pre-wrap break-words font-mono">{call.Recovery_Request}</pre>}
                    {call.Wait_Duration_Seconds != null && <span>Cooldown wait: {call.Wait_Duration_Seconds.toFixed(2)} sec</span>}
                  </div>
                )}
              </div>
            </details>
          ))}
        </div>
      </article>
    </details>
  )
}

function ToolExecutionCard({ tool }: { tool: LogToolExecution }) {
  return (
    <details className="grid gap-2">
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 rounded-md py-1">
        <span className="flex flex-wrap items-center gap-2">
          <Wrench className="size-4 text-muted-foreground" />
          <span className="font-medium">Tool · {tool.Name || "Unknown tool"}</span>
          <StatusBadge status={tool.Status} />
        </span>
        <span className="text-xs text-muted-foreground">
          {formatTime(tool.Timestamp)} · {tool.Duration == null ? "Duration not recorded" : `${tool.Duration.toFixed(2)} sec`}
        </span>
      </summary>
      <article className="grid gap-3 rounded-lg border p-3 sm:p-4">
        <p className="text-xs text-muted-foreground">
          {tool.Task_Id == null ? "Task association was not recorded." : `Triggered by Task #${tool.Task_Id}`}
          {tool.Tool_Call_Id ? ` · Call ${tool.Tool_Call_Id}` : ""}
        </p>
        <div className="grid gap-2">
          <p className="text-xs font-medium text-muted-foreground">Parameters</p>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/50 p-3 font-mono text-xs">
            {tool.Parameters ? formatPayload(tool.Parameters) : "No parameters were recorded."}
          </pre>
        </div>
        <div className="grid gap-2">
          <p className="text-xs font-medium text-muted-foreground">{tool.Status === "Failed" ? "Tool error" : "Tool response"}</p>
          <pre className="max-h-64 min-h-16 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/50 p-3 font-mono text-xs">
            {tool.Error ?? tool.Response ?? (tool.Status === "Running" ? "Tool is still running." : "No tool response was recorded.")}
          </pre>
        </div>
      </article>
    </details>
  )
}

function ToolActivityPanel({
  tools,
  pending = false,
  error,
}: {
  tools: LogToolExecution[]
  pending?: boolean
  error?: string | null
}) {
  const latestTool = tools[tools.length - 1]

  if (tools.length === 0) {
    if (!pending && !error) return null
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {pending && <LoaderCircle className="size-3.5 animate-spin" />}
        {error ? `Live tool activity unavailable: ${error}` : "Agent is working · waiting for a tool call"}
      </div>
    )
  }

  return (
    <details className="rounded-lg border px-3 py-2">
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 text-xs">
        <span className="flex flex-wrap items-center gap-2">
          {pending && <LoaderCircle className="size-3.5 animate-spin text-muted-foreground" />}
          <Wrench className="size-3.5 text-muted-foreground" />
          <span className="font-medium">Latest tool: {latestTool.Name}</span>
          <StatusBadge status={latestTool.Status} />
          <span className="text-muted-foreground">
            {tools.length} call{tools.length === 1 ? "" : "s"} · expand to see all
          </span>
        </span>
        {error && <span className="text-destructive">Live updates unavailable</span>}
      </summary>
      <div className="mt-2 grid gap-2">
        {tools.map((tool) => (
          <ToolExecutionCard key={tool.ID} tool={tool} />
        ))}
        {error && <p className="text-xs text-destructive">Live tool activity unavailable: {error}</p>}
      </div>
    </details>
  )
}

function AssistantChatBubble({ message }: { message: ChatMessage }) {
  const [expanded, setExpanded] = useState(false)
  const [toolsVisible, setToolsVisible] = useState(false)
  const [copied, setCopied] = useState(false)
  const tools = message.tool_activity || []

  const copyResponse = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch (error) {
      toast.error(`Could not copy response: ${messageOf(error)}`)
    }
  }

  return (
    <div className={`max-w-[90%] min-w-0 overflow-y-auto rounded-2xl bg-muted sm:max-w-[82%] ${expanded ? "max-h-[75vh]" : "max-h-80"}`}>
      <div className="space-y-2 px-4 pt-3">
        <div className="break-words text-sm leading-7">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
      </div>
      <div className="sticky bottom-0 flex items-center gap-1 border-t border-border/50 bg-muted/95 px-3 py-2 backdrop-blur">
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={copied ? "Response copied" : "Copy response"}
          title={copied ? "Copied" : "Copy response"}
          onClick={() => void copyResponse()}
        >
          {copied ? <Check /> : <Copy />}
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={expanded ? "Collapse response" : "Expand response"}
          title={expanded ? "Collapse response" : "Expand response"}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <Minimize2 /> : <Maximize2 />}
        </Button>
        {tools.length > 0 && (
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={toolsVisible ? "Hide executed tools" : "Show executed tools"}
            title={toolsVisible ? "Hide executed tools" : `Show ${tools.length} executed tools`}
            aria-pressed={toolsVisible}
            onClick={() => setToolsVisible((value) => !value)}
          >
            <MoreHorizontal />
          </Button>
        )}
      </div>
      {toolsVisible && tools.length > 0 && (
        <div className="grid gap-2 px-3 pb-3" aria-label="Executed tools">
          {tools.map((tool) => <ToolExecutionCard key={tool.ID} tool={tool} />)}
        </div>
      )}
    </div>
  )
}

function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon
  title: string
  description: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex min-h-56 flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="rounded-full bg-muted p-3 text-muted-foreground">
        <Icon className="size-5" />
      </div>
      <div className="space-y-1">
        <h3 className="font-medium">{title}</h3>
        <p className="max-w-md text-sm text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  )
}

function App() {
  const { resolvedTheme, setTheme } = useTheme()
  const [page, setPage] = useState<Page>(pageFromHash)
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historySearch, setHistorySearch] = useState("")
  const [renameOpen, setRenameOpen] = useState(false)
  const [renameTitle, setRenameTitle] = useState("")
  const [chatText, setChatText] = useState("")
  const [chatMode, setChatMode] = useState("agent")
  const [temperature, setTemperature] = useState("0.2")
  const [maxTurns, setMaxTurns] = useState("20")
  const [sending, setSending] = useState(false)
  const [sendingConversationId, setSendingConversationId] = useState<number | null>(null)
  const [sendingMode, setSendingMode] = useState<string | null>(null)
  const [activityBaseline, setActivityBaseline] = useState(0)
  const [liveToolActivity, setLiveToolActivity] = useState<LogToolExecution[]>([])
  const [liveActivityError, setLiveActivityError] = useState<string | null>(null)
  const liveToolActivityRef = useRef<LogToolExecution[]>([])

  const [tools, setTools] = useState<Record<string, ToolInfo>>({})
  const [toolSearch, setToolSearch] = useState("")
  const [selectedTool, setSelectedTool] = useState("")
  const [toolArgs, setToolArgs] = useState<Record<string, string>>({})
  const [toolJsonMode, setToolJsonMode] = useState(false)
  const [toolJson, setToolJson] = useState("{}")
  const [toolOutput, setToolOutput] = useState("")
  const [toolDuration, setToolDuration] = useState<number | null>(null)
  const [toolRunStatus, setToolRunStatus] = useState<string | null>(null)
  const [runningTool, setRunningTool] = useState(false)
  const [updatingTool, setUpdatingTool] = useState<string | null>(null)
  const [createToolOpen, setCreateToolOpen] = useState(false)
  const [newToolFile, setNewToolFile] = useState("")
  const [newToolCode, setNewToolCode] = useState("")

  const [providers, setProviders] = useState<Provider[]>([])
  const [models, setModels] = useState<Model[]>([])
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([])
  const [dbSearch, setDbSearch] = useState({ providers: "", models: "", keys: "" })
  const [editingEntity, setEditingEntity] = useState<{ kind: EntityKind; record?: EntityRecord } | null>(null)
  const [entityForm, setEntityForm] = useState<EntityForm>({})
  const [savingEntity, setSavingEntity] = useState(false)

  const [logConversations, setLogConversations] = useState<LogConversation[]>([])
  const [logDetails, setLogDetails] = useState<Record<number, LogDetails>>({})
  const [expandedLogId, setExpandedLogId] = useState<number | null>(null)
  const [loadingLogId, setLoadingLogId] = useState<number | null>(null)
  const [logViewMode, setLogViewMode] = useState<LogViewMode>("full")

  const currentConversation = conversations.find((item) => item.ID === activeConversationId)
  const currentPageCopy = pageCopy[page]
  const selectedToolInfo = selectedTool ? tools[selectedTool] : undefined

  useEffect(() => {
    const syncPage = () => setPage(pageFromHash())
    window.addEventListener("hashchange", syncPage)
    return () => window.removeEventListener("hashchange", syncPage)
  }, [])

  const loadStats = useCallback(async () => {
    try {
      setStats(await apiRequest<SystemStats>("/api/stats"))
      setApiError(null)
    } catch (error) {
      setApiError(messageOf(error))
    }
  }, [])

  const loadConversations = useCallback(async () => {
    try {
      setConversations(await apiRequest<Conversation[]>("/api/conversations"))
      setApiError(null)
    } catch (error) {
      setApiError(messageOf(error))
    }
  }, [])

  const loadMessages = useCallback(async (conversationId: number) => {
    setMessagesLoading(true)
    try {
      const result = await apiRequest<{ messages: ChatMessage[] }>(
        `/api/conversations/${conversationId}/messages`,
      )
      setMessages(normalizeRestoredMessages(result.messages))
      setApiError(null)
    } catch (error) {
      toast.error(`Could not load conversation: ${messageOf(error)}`)
    } finally {
      setMessagesLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!sending || sendingMode !== "agent" || sendingConversationId === null) return

    let cancelled = false
    let socket: WebSocket | null = null
    let pollTimer: ReturnType<typeof setTimeout> | undefined
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    let heartbeat: ReturnType<typeof setInterval> | undefined

    const isSocketOpen = () => socket !== null && socket.readyState === 1

    const applyActivity = (interactionId: number | null, incoming: LogToolExecution[]) => {
      if (interactionId === null || interactionId <= activityBaseline) return
      const merged = new Map(liveToolActivityRef.current.map((tool) => [tool.ID, tool]))
      for (const tool of incoming) merged.set(tool.ID, tool)
      const nextTools = [...merged.values()].sort((left, right) => left.ID - right.ID)
      liveToolActivityRef.current = nextTools
      setLiveToolActivity(nextTools)
      setLiveActivityError(null)
    }

    const pollActivity = async () => {
      if (cancelled || isSocketOpen()) return
      try {
        const activity = await apiRequest<ConversationActivity>(
          `/api/conversations/${sendingConversationId}/activity?after_interaction_id=${activityBaseline}`,
        )
        if (!cancelled) applyActivity(activity.interaction_id, activity.tools)
      } catch (error) {
        if (!cancelled) setLiveActivityError(messageOf(error))
      }

      if (!cancelled && !isSocketOpen()) {
        pollTimer = setTimeout(() => void pollActivity(), 1200)
      }
    }

    const connect = () => {
      if (cancelled) return
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
      const url = `${protocol}//${window.location.host}/ws/conversations/${sendingConversationId}/activity?after_interaction_id=${activityBaseline}`
      const currentSocket = new WebSocket(url)
      socket = currentSocket

      currentSocket.onopen = () => {
        if (cancelled) return
        if (pollTimer) clearTimeout(pollTimer)
        setLiveActivityError(null)
        currentSocket.send(JSON.stringify({ type: "ping" }))
        heartbeat = setInterval(() => {
          if (currentSocket.readyState === WebSocket.OPEN) {
            currentSocket.send(JSON.stringify({ type: "ping" }))
          }
        }, 25000)
      }

      currentSocket.onmessage = (event) => {
        try {
          const activity = JSON.parse(event.data) as ActivitySocketEvent
          if (activity.type === "snapshot" && activity.interaction_id != null) {
            applyActivity(activity.interaction_id, activity.tools || [])
          } else if (activity.type === "tool_update" && activity.interaction_id != null && activity.tool) {
            applyActivity(activity.interaction_id, [activity.tool])
          }
        } catch (error) {
          setLiveActivityError(`Invalid activity update: ${messageOf(error)}`)
        }
      }

      currentSocket.onclose = () => {
        if (socket === currentSocket && heartbeat) clearInterval(heartbeat)
        if (socket === currentSocket) heartbeat = undefined
        if (cancelled) return
        void pollActivity()
        reconnectTimer = setTimeout(connect, 2000)
      }

      currentSocket.onerror = () => currentSocket.close()
    }

    connect()
    return () => {
      cancelled = true
      if (pollTimer) clearTimeout(pollTimer)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (heartbeat) clearInterval(heartbeat)
      socket?.close()
    }
  }, [activityBaseline, sending, sendingConversationId, sendingMode])

  const loadDatabase = useCallback(async () => {
    try {
      const [nextProviders, nextModels, nextKeys] = await Promise.all([
        apiRequest<Provider[]>("/api/providers"),
        apiRequest<Model[]>("/api/models"),
        apiRequest<ApiKey[]>("/api/api-keys"),
      ])
      setProviders(nextProviders)
      setModels(nextModels)
      setApiKeys(nextKeys)
      setApiError(null)
    } catch (error) {
      toast.error(`Could not load database records: ${messageOf(error)}`)
    }
  }, [])

  const loadTools = useCallback(async () => {
    try {
      const nextTools = await apiRequest<Record<string, ToolInfo>>("/api/tools")
      setTools(nextTools)
      setApiError(null)
      if (!selectedTool || !(selectedTool in nextTools)) {
        const firstValid = Object.entries(nextTools).find(([, info]) => info.status === "valid")
        const firstName = firstValid?.[0] ?? Object.keys(nextTools)[0] ?? ""
        setSelectedTool(firstName)
        const defaults = Object.fromEntries(
          Object.entries(nextTools[firstName]?.parameter || {}).map(([key, info]) => [
            key,
            info.default === undefined ? "" : String(info.default),
          ]),
        )
        setToolArgs(defaults)
        setToolJson(JSON.stringify(defaults, null, 2))
      }
    } catch (error) {
      toast.error(`Could not load tools: ${messageOf(error)}`)
    }
  }, [selectedTool])

  const loadLogs = useCallback(async () => {
    try {
      setLogConversations(await apiRequest<LogConversation[]>("/api/logs/conversations?limit=25"))
      setApiError(null)
    } catch (error) {
      toast.error(`Could not load logs: ${messageOf(error)}`)
    }
  }, [])

  useEffect(() => {
    void loadStats()
    void loadConversations()
  }, [loadConversations, loadStats])

  useEffect(() => {
    if (page === "tools") void loadTools()
    if (page === "db") void loadDatabase()
    if (page === "logs") void loadLogs()
  }, [loadDatabase, loadLogs, loadTools, page])

  useEffect(() => {
    if (activeConversationId === null && conversations.length > 0) {
      const firstConversation = conversations[0]
      setActiveConversationId(firstConversation.ID)
      void loadMessages(firstConversation.ID)
    }
  }, [activeConversationId, conversations, loadMessages])

  const refreshAll = async () => {
    setRefreshing(true)
    await Promise.all([loadStats(), loadConversations(), loadTools(), loadDatabase(), loadLogs()])
    setRefreshing(false)
    toast.success("Workspace refreshed")
  }

  const createConversation = async () => {
    try {
      const created = await apiRequest<{ id: number }>("/api/conversations", {
        method: "POST",
        body: jsonBody({ title: "New Chat" }),
      })
      setActiveConversationId(created.id)
      setMessages([])
      setHistoryOpen(false)
      await loadConversations()
    } catch (error) {
      toast.error(`Could not create conversation: ${messageOf(error)}`)
    }
  }

  const openConversation = async (conversationId: number) => {
    setActiveConversationId(conversationId)
    setHistoryOpen(false)
    await loadMessages(conversationId)
  }

  const renameConversation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (activeConversationId === null || !renameTitle.trim()) return
    try {
      await apiRequest(`/api/conversations/${activeConversationId}`, {
        method: "PATCH",
        body: jsonBody({ title: renameTitle.trim() }),
      })
      await loadConversations()
      setRenameOpen(false)
      toast.success("Conversation renamed")
    } catch (error) {
      toast.error(`Could not rename conversation: ${messageOf(error)}`)
    }
  }

  const deleteConversation = async (conversationId: number) => {
    if (!window.confirm("Delete this conversation and its history?")) return
    try {
      await apiRequest(`/api/conversations/${conversationId}`, { method: "DELETE" })
      const wasActive = conversationId === activeConversationId
      await loadConversations()
      if (wasActive) {
        setActiveConversationId(null)
        setMessages([])
      }
      await loadStats()
      toast.success("Conversation deleted")
    } catch (error) {
      toast.error(`Could not delete conversation: ${messageOf(error)}`)
    }
  }

  const sendMessage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const text = chatText.trim()
    if (!text || sending) return

    setSending(true)
    setChatText("")
    const requestMode = chatMode
    const baseline = messages.reduce(
      (latest, message) => Math.max(latest, message.interactive_id || 0),
      0,
    )
    setActivityBaseline(baseline)
    setLiveToolActivity([])
    liveToolActivityRef.current = []
    setLiveActivityError(null)
    setSendingMode(requestMode)
    const optimisticMessage: ChatMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content: text,
    }
    setMessages((current) => [...current, optimisticMessage])

    try {
      let conversationId = activeConversationId
      if (conversationId === null) {
        const created = await apiRequest<{ id: number }>("/api/conversations", {
          method: "POST",
          body: jsonBody({ title: text.slice(0, 50) || "New Chat" }),
        })
        conversationId = created.id
        setActiveConversationId(conversationId)
      }
      setSendingConversationId(conversationId)

      const result = await apiRequest<{
        success: boolean
        response: string | null
        error?: string
        duration_ms?: number
        conversation_id?: number
        chosen?: ChatMessage["chosen"]
        mode?: string
      }>("/api/chat", {
        method: "POST",
        body: jsonBody({
          message: text,
          mode: requestMode,
          temperature: Number(temperature) || 0.2,
          max_turns: Number(maxTurns) || 20,
          conversation_id: conversationId,
        }),
      })

      if (!result.success) throw new Error(result.error || "Chat request failed")
      const responseConversationId = result.conversation_id ?? conversationId
      if (responseConversationId) setActiveConversationId(responseConversationId)
      let toolActivity = liveToolActivityRef.current
      let responseInteractionId = baseline + 1
      if (requestMode === "agent" && responseConversationId) {
        try {
          const activity = await apiRequest<ConversationActivity>(
            `/api/conversations/${responseConversationId}/activity?after_interaction_id=${baseline}`,
          )
          toolActivity = activity.tools
          responseInteractionId = activity.interaction_id ?? responseInteractionId
          liveToolActivityRef.current = activity.tools
          setLiveToolActivity(activity.tools)
          setLiveActivityError(null)
        } catch (error) {
          setLiveActivityError(messageOf(error))
        }
      }
      setMessages((current) => [
        ...current,
        {
          id: `reply-${Date.now()}`,
          role: "assistant",
          content: result.response || "",
          duration_ms: result.duration_ms,
          chosen: result.chosen,
          mode: result.mode || requestMode,
          interactive_id: responseInteractionId,
          tool_activity: toolActivity,
        },
      ])
      await Promise.all([loadConversations(), loadStats()])
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: `Request failed: ${messageOf(error)}`,
          mode: requestMode,
          tool_activity: liveToolActivityRef.current,
        },
      ])
      toast.error(`Chat request failed: ${messageOf(error)}`)
    } finally {
      setSending(false)
      setSendingConversationId(null)
      setSendingMode(null)
    }
  }

  const selectToolByName = (name: string) => {
    setSelectedTool(name)
    const params = tools[name]?.parameter || {}
    const defaults = Object.fromEntries(
      Object.entries(params).map(([key, info]) => [
        key,
        info.default === undefined ? "" : String(info.default),
      ]),
    )
    setToolArgs(defaults)
    setToolJson(JSON.stringify(defaults, null, 2))
    setToolOutput("")
    setToolDuration(null)
    setToolRunStatus(null)
    setToolJsonMode(false)
  }

  const toggleToolEnabled = async (name: string) => {
    const enabled = tools[name]?.enabled !== false
    setUpdatingTool(name)
    try {
      const updated = await apiRequest<ToolInfo>(`/api/tools/${encodeURIComponent(name)}/enabled`, {
        method: "PUT",
        body: jsonBody({ enabled: !enabled }),
      })
      setTools((current) => ({ ...current, [name]: updated }))
      toast.success(`${name} ${updated.enabled === false ? "disabled" : "enabled"} for the LLM`)
    } catch (error) {
      toast.error(`Could not update ${name}: ${messageOf(error)}`)
    } finally {
      setUpdatingTool(null)
    }
  }

  const executeTool = async () => {
    if (!selectedTool) return
    let args: Record<string, unknown>
    try {
      if (toolJsonMode) {
        const parsed: unknown = JSON.parse(toolJson || "{}")
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          throw new Error("Arguments must be a JSON object")
        }
        args = parsed as Record<string, unknown>
      } else {
        args = Object.fromEntries(
          Object.entries(toolArgs).map(([key, value]) => {
            const parameterType = selectedToolInfo?.parameter?.[key]?.type?.toLowerCase()
            if (parameterType === "bool" || parameterType === "boolean") {
              return [key, value === "true"]
            }
            if (["int", "integer", "float", "number"].includes(parameterType || "")) {
              return [key, value.trim() ? Number(value) : null]
            }
            return [key, value]
          }),
        )
      }
    } catch (error) {
      toast.error(`Invalid tool arguments: ${messageOf(error)}`)
      return
    }

    setRunningTool(true)
    setToolOutput("Running tool…")
    setToolRunStatus(null)
    try {
      const result = await apiRequest<{
        success: boolean
        result?: unknown
        error?: string
        duration_ms: number
      }>("/api/tools/execute", {
        method: "POST",
        body: jsonBody({ tool_name: selectedTool, arguments: args }),
      })
      setToolDuration(result.duration_ms)
      if (result.success) {
        setToolRunStatus("Success")
        setToolOutput(
          typeof result.result === "string"
            ? result.result
            : JSON.stringify(result.result, null, 2),
        )
        toast.success(`Executed ${selectedTool}`)
      } else {
        setToolRunStatus("Failed")
        setToolOutput(result.error || "Tool execution failed")
        toast.error(result.error || "Tool execution failed")
      }
    } catch (error) {
      setToolRunStatus("Failed")
      setToolOutput(messageOf(error))
      toast.error(`Tool execution failed: ${messageOf(error)}`)
    } finally {
      setRunningTool(false)
    }
  }

  const createTool = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!newToolFile.trim() || !newToolCode.trim()) {
      toast.error("Enter a file name and Python code")
      return
    }
    try {
      await apiRequest("/api/tools/create", {
        method: "POST",
        body: jsonBody({ file_name: newToolFile.trim(), content: newToolCode }),
      })
      setCreateToolOpen(false)
      setNewToolFile("")
      setNewToolCode("")
      await Promise.all([loadTools(), loadStats()])
      toast.success("Tool created and registered")
    } catch (error) {
      toast.error(`Could not create tool: ${messageOf(error)}`)
    }
  }

  const openEntityEditor = (kind: EntityKind, record?: EntityRecord) => {
    setEditingEntity({ kind, record })
    if (kind === "provider") {
      const provider = record as Provider | undefined
      setEntityForm({
        name: provider?.name || "",
        base_url: provider?.base_url || "",
        status: provider?.status || "active",
      })
    } else if (kind === "model") {
      const model = record as Model | undefined
      setEntityForm({
        provider_id: model ? String(model.provider_id) : providers[0] ? String(providers[0].id) : "",
        name: model?.name || "",
        model_size: model?.model_size == null ? "" : String(model.model_size),
        RPM: model?.RPM == null ? "" : String(model.RPM),
        TPM: model?.TPM == null ? "" : String(model.TPM),
        status: model?.status || "active",
      })
    } else {
      const key = record as ApiKey | undefined
      setEntityForm({
        provider_id: key ? String(key.provider_id) : providers[0] ? String(providers[0].id) : "",
        unique_name: key?.unique_name || "",
        env_key: key?.env_key || "",
        status: key?.status || "active",
      })
    }
  }

  const saveEntity = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!editingEntity) return
    const { kind, record } = editingEntity
    const resource = kind === "provider" ? "providers" : kind === "model" ? "models" : "api-keys"
    const id = record?.id
    const endpoint = id ? `/api/${resource}/${id}` : `/api/${resource}`
    const optionalNumber = (value: string) => (value.trim() ? Number(value) : null)
    let payload: Record<string, unknown>

    if (kind === "provider") {
      payload = {
        name: entityForm.name?.trim(),
        base_url: entityForm.base_url?.trim(),
        status: entityForm.status || "active",
      }
    } else if (kind === "model") {
      payload = {
        provider_id: Number(entityForm.provider_id),
        name: entityForm.name?.trim(),
        model_size: optionalNumber(entityForm.model_size || ""),
        RPM: optionalNumber(entityForm.RPM || ""),
        TPM: optionalNumber(entityForm.TPM || ""),
        status: entityForm.status || "active",
      }
    } else {
      payload = {
        provider_id: Number(entityForm.provider_id),
        unique_name: entityForm.unique_name?.trim(),
        env_key: entityForm.env_key?.trim(),
        status: entityForm.status || "active",
      }
    }

    setSavingEntity(true)
    try {
      await apiRequest(endpoint, {
        method: id ? "PUT" : "POST",
        body: jsonBody(payload),
      })
      setEditingEntity(null)
      await Promise.all([loadDatabase(), loadStats()])
      toast.success(`${kind === "key" ? "API key reference" : kind} ${id ? "updated" : "created"}`)
    } catch (error) {
      toast.error(`Could not save ${kind}: ${messageOf(error)}`)
    } finally {
      setSavingEntity(false)
    }
  }

  const deleteEntity = async (kind: EntityKind, record: EntityRecord) => {
    const label = kind === "provider" ? "provider" : kind === "model" ? "model" : "API key reference"
    if (!window.confirm(`Delete this ${label}?`)) return
    const resource = kind === "provider" ? "providers" : kind === "model" ? "models" : "api-keys"
    try {
      await apiRequest(`/api/${resource}/${record.id}`, { method: "DELETE" })
      await Promise.all([loadDatabase(), loadStats()])
      toast.success(`${label} deleted`)
    } catch (error) {
      toast.error(`Could not delete ${label}: ${messageOf(error)}`)
    }
  }

  const cycleEntityStatus = async (kind: EntityKind, record: EntityRecord) => {
    const status = record.status === "active"
      ? "cooldown"
      : record.status === "cooldown"
        ? "disabled"
        : "active"
    const resource = kind === "provider" ? "providers" : kind === "model" ? "models" : "api-keys"
    try {
      await apiRequest(`/api/${resource}/${record.id}`, {
        method: "PUT",
        body: jsonBody({ status }),
      })
      await Promise.all([loadDatabase(), loadStats()])
      toast.success(`Status changed to ${status}`)
    } catch (error) {
      toast.error(`Could not update status: ${messageOf(error)}`)
    }
  }

  const toggleLogDetails = async (conversationId: number) => {
    if (expandedLogId === conversationId) {
      setExpandedLogId(null)
      return
    }
    setExpandedLogId(conversationId)
    if (logDetails[conversationId]) return
    setLoadingLogId(conversationId)
    try {
      const result = await apiRequest<LogDetails>(`/api/logs/conversations/${conversationId}`)
      setLogDetails((current) => ({ ...current, [conversationId]: result }))
    } catch (error) {
      toast.error(`Could not load log details: ${messageOf(error)}`)
    } finally {
      setLoadingLogId(null)
    }
  }

  const filteredConversations = useMemo(() => {
    const query = historySearch.trim().toLowerCase()
    return query
      ? conversations.filter((item) => (item.Title || "").toLowerCase().includes(query))
      : conversations
  }, [conversations, historySearch])

  const filteredTools = useMemo(() => {
    const query = toolSearch.trim().toLowerCase()
    return Object.entries(tools).filter(([name, info]) =>
      (!query || `${name} ${info.description || ""}`.toLowerCase().includes(query)),
    )
  }, [toolSearch, tools])

  const filteredProviders = useMemo(() => {
    const query = dbSearch.providers.trim().toLowerCase()
    return providers.filter((provider) =>
      `${provider.name} ${provider.base_url}`.toLowerCase().includes(query),
    )
  }, [dbSearch.providers, providers])

  const filteredModels = useMemo(() => {
    const query = dbSearch.models.trim().toLowerCase()
    return models.filter((model) =>
      `${model.name} ${model.provider_name}`.toLowerCase().includes(query),
    )
  }, [dbSearch.models, models])

  const filteredKeys = useMemo(() => {
    const query = dbSearch.keys.trim().toLowerCase()
    return apiKeys.filter((key) =>
      `${key.unique_name} ${key.env_key} ${key.provider_name}`.toLowerCase().includes(query),
    )
  }, [apiKeys, dbSearch.keys])

  const updateForm = (key: string, value: string) => {
    setEntityForm((current) => ({ ...current, [key]: value }))
  }

  const renderEntityDialog = () => {
    if (!editingEntity) return null
    const { kind, record } = editingEntity
    const entityLabel = kind === "key" ? "API key reference" : kind

    return (
      <Dialog open onOpenChange={(open) => !open && setEditingEntity(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{record ? "Edit" : "Add"} {entityLabel}</DialogTitle>
            <DialogDescription>
              {kind === "key"
                ? "Store the environment variable name only. The secret value stays in your environment."
                : `Configure the ${entityLabel} used by the failover router.`}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={saveEntity} className="grid gap-4">
            {kind === "provider" ? (
              <>
                <Field label="Provider name" htmlFor="entity-name">
                  <Input id="entity-name" required value={entityForm.name || ""} onChange={(event) => updateForm("name", event.target.value)} />
                </Field>
                <Field label="Base URL" htmlFor="entity-url">
                  <Input id="entity-url" required type="url" value={entityForm.base_url || ""} onChange={(event) => updateForm("base_url", event.target.value)} />
                </Field>
              </>
            ) : (
              <>
                <Field label="Provider" htmlFor="entity-provider">
                  <Select value={entityForm.provider_id || ""} onValueChange={(value) => updateForm("provider_id", value)}>
                    <SelectTrigger id="entity-provider"><SelectValue placeholder="Choose a provider" /></SelectTrigger>
                    <SelectContent>
                      {providers.map((provider) => (
                        <SelectItem key={provider.id} value={String(provider.id)}>{provider.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                {kind === "model" ? (
                  <>
                    <Field label="Model name" htmlFor="entity-name">
                      <Input id="entity-name" required value={entityForm.name || ""} onChange={(event) => updateForm("name", event.target.value)} />
                    </Field>
                    <div className="grid gap-4 sm:grid-cols-3">
                      <Field label="Size (B)" htmlFor="entity-size">
                        <Input id="entity-size" type="number" step="any" value={entityForm.model_size || ""} onChange={(event) => updateForm("model_size", event.target.value)} />
                      </Field>
                      <Field label="RPM" htmlFor="entity-rpm">
                        <Input id="entity-rpm" type="number" value={entityForm.RPM || ""} onChange={(event) => updateForm("RPM", event.target.value)} />
                      </Field>
                      <Field label="TPM" htmlFor="entity-tpm">
                        <Input id="entity-tpm" type="number" value={entityForm.TPM || ""} onChange={(event) => updateForm("TPM", event.target.value)} />
                      </Field>
                    </div>
                  </>
                ) : (
                  <>
                    <Field label="Unique key name" htmlFor="entity-unique-name">
                      <Input id="entity-unique-name" required value={entityForm.unique_name || ""} onChange={(event) => updateForm("unique_name", event.target.value)} placeholder="MAIN" />
                    </Field>
                    <Field label="Environment variable name" htmlFor="entity-env-key">
                      <Input id="entity-env-key" required value={entityForm.env_key || ""} onChange={(event) => updateForm("env_key", event.target.value)} placeholder="API_KEY_GROQ_MAIN" />
                    </Field>
                  </>
                )}
              </>
            )}
            <Field label="Status" htmlFor="entity-status">
              <Select value={entityForm.status || "active"} onValueChange={(value) => updateForm("status", value)}>
                <SelectTrigger id="entity-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="cooldown">Cooldown</SelectItem>
                  <SelectItem value="disabled">Disabled</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditingEntity(null)}>Cancel</Button>
              <Button type="submit" disabled={savingEntity || providers.length === 0 && kind !== "provider"}>
                {savingEntity && <LoaderCircle className="animate-spin" />}
                {record ? "Save changes" : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    )
  }

  return (
    <TooltipProvider delayDuration={100}>
      <div className="flex h-svh min-h-0 overflow-hidden bg-background text-foreground">
        <aside className="flex w-[68px] shrink-0 flex-col items-center border-r bg-muted/30 py-3">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="secondary" size="icon-lg" aria-label="Brain Studio" className="mb-6">
                <Brain className="size-5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Brain Studio</TooltipContent>
          </Tooltip>

          <nav className="flex flex-col items-center gap-2" aria-label="Main navigation">
            {navigation.map(({ id, label, icon: Icon }) => (
              <Tooltip key={id}>
                <TooltipTrigger asChild>
                  <Button
                    variant={page === id ? "secondary" : "ghost"}
                    size="icon-lg"
                    aria-label={label}
                    aria-current={page === id ? "page" : undefined}
                    onClick={() => {
                      window.location.hash = id
                    }}
                  >
                    <Icon />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">{label}</TooltipContent>
              </Tooltip>
            ))}
          </nav>

          <div className="mt-auto flex flex-col items-center gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="flex size-9 items-center justify-center" aria-label={apiError ? "API offline" : "API connected"}>
                  <span className={`size-2.5 rounded-full ${apiError ? "bg-destructive" : "bg-emerald-500"}`} />
                </span>
              </TooltipTrigger>
              <TooltipContent side="right">{apiError ? "API offline" : "API connected"}</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon-lg" aria-label="Refresh workspace" onClick={() => void refreshAll()} disabled={refreshing}>
                  <RefreshCw className={refreshing ? "animate-spin" : ""} />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Refresh workspace</TooltipContent>
            </Tooltip>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b px-4 sm:px-6">
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold">{currentPageCopy.title}</h1>
              <p className="hidden truncate text-xs text-muted-foreground sm:block">{currentPageCopy.description}</p>
            </div>
            <div className="flex items-center gap-2">
              {stats && (
                <div className="hidden items-center gap-4 text-xs text-muted-foreground lg:flex">
                  <span><strong className="font-medium text-foreground">{stats.providers_count}</strong> providers</span>
                  <span><strong className="font-medium text-foreground">{stats.active_models}/{stats.models_count}</strong> active models</span>
                  <span><strong className="font-medium text-foreground">{stats.keys_count}</strong> keys</span>
                </div>
              )}
              {apiError && (
                <Badge variant="destructive" className="hidden items-center gap-1 sm:inline-flex">
                  <CircleAlert className="size-3" /> API unavailable
                </Badge>
              )}
              <Button
                variant="outline"
                size="icon"
                aria-label={resolvedTheme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
                title={resolvedTheme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
                onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
              >
                {resolvedTheme === "dark" ? <Sun /> : <Moon />}
              </Button>
            </div>
          </header>

          {apiError && (
            <div className="flex items-center gap-2 border-b bg-muted/40 px-4 py-2 text-sm text-muted-foreground sm:px-6">
              <CircleAlert className="size-4 shrink-0" />
              <span className="truncate">Backend unavailable: {apiError}. Start it from the repository root with <code className="rounded bg-muted px-1.5 py-0.5">python -m backend.run_server</code>.</span>
            </div>
          )}

          <main className={`min-h-0 flex-1 ${page === "logs" ? "overflow-y-auto" : "overflow-hidden"}`}>
            {page === "chat" && (
              <section className="flex h-full min-h-0 flex-col">
                <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b px-4 sm:px-6">
                  <div className="flex min-w-0 items-center gap-2">
                    <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="outline" size="icon" aria-label="Open conversation history" onClick={() => setHistoryOpen(true)}>
                            <PanelLeft />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Conversation history</TooltipContent>
                      </Tooltip>
                      <SheetContent side="left" className="flex w-[min(360px,calc(100vw-68px))] flex-col gap-0 p-0">
                        <SheetHeader className="border-b p-4 text-left">
                          <SheetTitle>Conversations</SheetTitle>
                          <SheetDescription>Choose a chat or start a new one.</SheetDescription>
                        </SheetHeader>
                        <div className="flex gap-2 border-b p-3">
                          <div className="relative min-w-0 flex-1">
                            <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
                            <Input className="pl-9" placeholder="Search chats" value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} />
                          </div>
                          <Button size="icon" aria-label="New chat" onClick={() => void createConversation()}><Plus /></Button>
                        </div>
                        <ScrollArea className="min-h-0 flex-1">
                          <div className="grid gap-1 p-2">
                            {filteredConversations.map((conversation) => (
                              <div key={conversation.ID} className={`group flex items-center gap-1 rounded-lg ${activeConversationId === conversation.ID ? "bg-muted" : "hover:bg-muted/70"}`}>
                                <button
                                  type="button"
                                  className="min-w-0 flex-1 p-3 text-left"
                                  onClick={() => void openConversation(conversation.ID)}
                                >
                                  <span className="block truncate text-sm font-medium">{conversation.Title || "New Chat"}</span>
                                  <span className="mt-1 block text-xs text-muted-foreground">{conversation.message_count} turns · {formatTime(conversation.Updated_At)}</span>
                                </button>
                                <Button variant="ghost" size="icon-sm" className="mr-2 opacity-0 group-hover:opacity-100" aria-label={`Delete ${conversation.Title || "conversation"}`} onClick={() => void deleteConversation(conversation.ID)}>
                                  <Trash2 />
                                </Button>
                              </div>
                            ))}
                            {filteredConversations.length === 0 && (
                              <p className="px-3 py-8 text-center text-sm text-muted-foreground">No conversations found.</p>
                            )}
                          </div>
                        </ScrollArea>
                      </SheetContent>
                    </Sheet>

                    <div className="min-w-0">
                      <div className="flex items-center gap-1">
                        <h2 className="truncate text-sm font-medium">{currentConversation?.Title || "New Chat"}</h2>
                        {activeConversationId !== null && (
                          <Button variant="ghost" size="icon-xs" aria-label="Rename conversation" onClick={() => {
                            setRenameTitle(currentConversation?.Title || "New Chat")
                            setRenameOpen(true)
                          }}>
                            <Pencil />
                          </Button>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">{chatMode === "agent" ? "Autonomous agent" : "Direct model"}</p>
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    <Select value={chatMode} onValueChange={setChatMode}>
                      <SelectTrigger className="h-8 w-[132px] text-xs sm:w-[160px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="agent">Autonomous agent</SelectItem>
                        <SelectItem value="direct">Direct model</SelectItem>
                      </SelectContent>
                    </Select>
                    <Button variant="outline" size="icon" aria-label="New chat" onClick={() => void createConversation()}>
                      <Plus />
                    </Button>
                    {activeConversationId !== null && (
                      <Button variant="ghost" size="icon" aria-label="Delete current conversation" onClick={() => void deleteConversation(activeConversationId)}>
                        <Trash2 />
                      </Button>
                    )}
                  </div>
                </div>

                <ScrollArea className="min-h-0 flex-1">
                  <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col gap-5 p-4 sm:p-8">
                    {messagesLoading ? (
                      <div className="grid gap-4">
                        <Skeleton className="h-20 w-3/4" />
                        <Skeleton className="ml-auto h-16 w-2/3" />
                        <Skeleton className="h-24 w-4/5" />
                      </div>
                    ) : messages.length === 0 ? (
                      <div className="flex flex-1 flex-col items-center justify-center gap-4 py-14 text-center">
                        <div className="rounded-2xl bg-muted p-4"><Brain className="size-7 text-muted-foreground" /></div>
                        <div className="space-y-1">
                          <h2 className="text-lg font-semibold">What can I help with?</h2>
                          <p className="text-sm text-muted-foreground">Ask a question or describe a task for your assistant.</p>
                        </div>
                      </div>
                    ) : (
                      messages.map((message) => (
                        <article key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                          {message.role === "user" ? (
                            <div className="max-w-[90%] min-w-0 rounded-2xl bg-muted px-4 py-3 sm:max-w-[82%]">
                              <div className="break-words text-sm leading-7">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                              </div>
                            </div>
                          ) : (
                            <AssistantChatBubble message={message} />
                          )}
                        </article>
                      ))
                    )}
                    {sending && (
                      <div className="grid gap-2 text-sm text-muted-foreground">
                        <div className="flex items-center gap-2">
                          <LoaderCircle className="size-4 animate-spin" />
                          {sendingMode === "agent" ? "Agent is working…" : "Waiting for the model…"}
                        </div>
                        {sendingMode === "agent" && (
                          <ToolActivityPanel
                            tools={liveToolActivity}
                            pending
                            error={liveActivityError}
                          />
                        )}
                      </div>
                    )}
                  </div>
                </ScrollArea>

                <form onSubmit={sendMessage} className="shrink-0 border-t p-3 sm:px-6 sm:py-4">
                  <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border bg-background p-2 shadow-xs focus-within:ring-2 focus-within:ring-ring/20">
                    <Textarea
                      aria-label="Message"
                      placeholder="Message your assistant…"
                      value={chatText}
                      onChange={(event) => setChatText(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault()
                          event.currentTarget.form?.requestSubmit()
                        }
                      }}
                      className="max-h-40 min-h-10 resize-none border-0 shadow-none focus-visible:ring-0"
                      rows={1}
                    />
                    <div className="flex shrink-0 items-center gap-1">
                      <Input
                        aria-label="Temperature"
                        type="number"
                        min="0"
                        max="1"
                        step="0.1"
                        title="Temperature"
                        value={temperature}
                        onChange={(event) => setTemperature(event.target.value)}
                        className="hidden h-8 w-[68px] text-xs sm:block"
                      />
                      <Input
                        aria-label="Maximum agent turns"
                        type="number"
                        min="1"
                        max="50"
                        title="Maximum agent turns"
                        value={maxTurns}
                        onChange={(event) => setMaxTurns(event.target.value)}
                        className="hidden h-8 w-[68px] text-xs sm:block"
                      />
                      <Button type="submit" size="icon" disabled={sending || !chatText.trim()} aria-label="Send message">
                        {sending ? <LoaderCircle className="animate-spin" /> : <Send />}
                      </Button>
                    </div>
                  </div>
                  <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-muted-foreground">Enter to send · Shift+Enter for a new line</p>
                </form>
              </section>
            )}

            {page === "mesh" && (
              <MeshPage
                temperature={Number(temperature) || 0.2}
                maxTurns={Number(maxTurns) || 20}
              />
            )}

            {page === "tools" && (
              <section className="grid h-full min-h-0 gap-4 p-4 lg:grid-cols-[minmax(240px,300px)_minmax(0,1fr)] lg:p-6">
                <Card className="flex min-h-0 flex-col overflow-hidden">
                  <CardHeader className="gap-3">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <CardTitle>Registered tools</CardTitle>
                        <CardDescription>
                          {Object.values(tools).filter((info) => info.enabled !== false).length} enabled · {Object.keys(tools).length} total
                        </CardDescription>
                      </div>
                      <Button variant="outline" size="icon" aria-label="Create tool" onClick={() => setCreateToolOpen(true)}><Plus /></Button>
                    </div>
                    <div className="relative">
                      <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
                      <Input className="pl-9" placeholder="Search tools" value={toolSearch} onChange={(event) => setToolSearch(event.target.value)} />
                    </div>
                  </CardHeader>
                  <Separator />
                  <ScrollArea className="min-h-0 flex-1">
                    <div className="grid gap-1 p-2">
                      {filteredTools.map(([name, info]) => (
                        <div
                          key={name}
                          className={`flex items-center gap-2 rounded-lg p-2 transition-colors ${selectedTool === name ? "bg-muted" : "hover:bg-muted/70"} ${info.enabled === false ? "opacity-65" : ""}`}
                        >
                          <button
                            type="button"
                            className="min-w-0 flex-1 rounded-md p-1 text-left"
                            onClick={() => selectToolByName(name)}
                          >
                            <span className="flex items-center justify-between gap-2">
                              <span className="truncate text-sm font-medium">{name}</span>
                              <Badge variant="secondary">{Object.keys(info.parameter || {}).length}</Badge>
                            </span>
                          </button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className={`h-6 w-11 shrink-0 rounded-full p-0 ${
                              info.enabled === false ? "justify-start bg-muted" : "justify-end bg-primary"
                            }`}
                            role="switch"
                            aria-label={`${info.enabled === false ? "Enable" : "Disable"} ${name} for the LLM`}
                            title={`${info.enabled === false ? "Enable" : "Disable"} ${name} for the LLM`}
                            aria-checked={info.enabled !== false}
                            disabled={updatingTool === name}
                            onClick={() => void toggleToolEnabled(name)}
                          >
                            <span className="mx-0.5 size-5 rounded-full bg-background shadow-sm" />
                          </Button>
                        </div>
                      ))}
                      {filteredTools.length === 0 && <p className="p-6 text-center text-sm text-muted-foreground">No tools found.</p>}
                    </div>
                  </ScrollArea>
                </Card>

                {selectedToolInfo ? (
                  <div className="flex min-h-0 flex-col gap-4 overflow-y-auto">
                    <Card>
                      <CardHeader>
                        <div className="flex items-start justify-between gap-4">
                          <div className="min-w-0 space-y-1">
                            <CardTitle className="break-all">{selectedTool}</CardTitle>
                            <CardDescription>{selectedToolInfo.description || "No description available."}</CardDescription>
                          </div>
                          <Badge variant={selectedToolInfo.status === "valid" ? "default" : "destructive"}>{selectedToolInfo.status || "unknown"}</Badge>
                        </div>
                      </CardHeader>
                      <CardContent className="grid gap-5">
                        <div className="flex items-center justify-between gap-3">
                          <h3 className="text-sm font-medium">Arguments</h3>
                          <Button variant="outline" size="sm" onClick={() => {
                            if (!toolJsonMode) setToolJson(JSON.stringify(Object.fromEntries(Object.entries(toolArgs).map(([key, value]) => [key, value])), null, 2))
                            else {
                              try {
                                const parsed = JSON.parse(toolJson) as Record<string, unknown>
                                setToolArgs(Object.fromEntries(Object.entries(parsed).map(([key, value]) => [key, String(value)])))
                              } catch (error) {
                                toast.error(`Invalid JSON: ${messageOf(error)}`)
                                return
                              }
                            }
                            setToolJsonMode((value) => !value)
                          }}>
                            <Code2 /> {toolJsonMode ? "Form mode" : "JSON mode"}
                          </Button>
                        </div>
                        {toolJsonMode ? (
                          <Textarea className="min-h-40 font-mono text-xs" value={toolJson} onChange={(event) => setToolJson(event.target.value)} aria-label="Tool arguments JSON" />
                        ) : Object.keys(selectedToolInfo.parameter || {}).length === 0 ? (
                          <p className="text-sm text-muted-foreground">This tool does not require arguments.</p>
                        ) : (
                          <div className="grid gap-4 sm:grid-cols-2">
                            {Object.entries(selectedToolInfo.parameter || {}).map(([key, info]) => (
                              <Field key={key} label={`${key}${info.required === false ? " (optional)" : ""}`} htmlFor={`tool-arg-${key}`}>
                                <Input
                                  id={`tool-arg-${key}`}
                                  type={["int", "integer", "float", "number"].includes((info.type || "").toLowerCase()) ? "number" : "text"}
                                  value={toolArgs[key] || ""}
                                  placeholder={info.type || "Enter a value"}
                                  onChange={(event) => setToolArgs((current) => ({ ...current, [key]: event.target.value }))}
                                />
                              </Field>
                            ))}
                          </div>
                        )}
                        <div className="flex justify-end">
                          <Button onClick={() => void executeTool()} disabled={runningTool || selectedToolInfo.status !== "valid"}>
                            {runningTool ? <LoaderCircle className="animate-spin" /> : <Play />}
                            {runningTool ? "Running…" : "Run tool"}
                          </Button>
                        </div>
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader className="flex-row items-center justify-between">
                        <div>
                          <CardTitle>Execution output</CardTitle>
                          <CardDescription>Tool results appear here.</CardDescription>
                        </div>
                        <div className="flex items-center gap-2">
                          {toolRunStatus && <StatusBadge status={toolRunStatus} />}
                          {toolDuration !== null && <span className="text-xs text-muted-foreground">{toolDuration} ms</span>}
                        </div>
                      </CardHeader>
                      <CardContent>
                        <pre className="max-h-80 min-h-20 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted p-4 font-mono text-xs leading-5">{toolOutput || "Ready to execute."}</pre>
                      </CardContent>
                    </Card>
                  </div>
                ) : (
                  <Card className="flex items-center justify-center">
                    <EmptyState icon={Wrench} title="Select a tool" description="Choose a registered tool to inspect its arguments and run it." />
                  </Card>
                )}
              </section>
            )}

            {page === "db" && (
              <section className="h-full overflow-y-auto p-4 sm:p-6">
                <Tabs defaultValue="providers" className="mx-auto max-w-7xl">
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <TabsList>
                      <TabsTrigger value="providers"><Server /> Providers</TabsTrigger>
                      <TabsTrigger value="models"><Cpu /> Models</TabsTrigger>
                      <TabsTrigger value="keys"><KeyRound /> API keys</TabsTrigger>
                    </TabsList>
                  </div>

                  <TabsContent value="providers">
                    <Card>
                      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
                        <div><CardTitle>Providers</CardTitle><CardDescription>{providers.length} configured</CardDescription></div>
                        <div className="flex w-full gap-2 sm:w-auto">
                          <div className="relative min-w-0 flex-1 sm:w-64">
                            <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
                            <Input className="pl-9" placeholder="Filter providers" value={dbSearch.providers} onChange={(event) => setDbSearch((current) => ({ ...current, providers: event.target.value }))} />
                          </div>
                          <Button onClick={() => openEntityEditor("provider")}><Plus /> Add provider</Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <Table>
                          <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Base URL</TableHead><TableHead>Status</TableHead><TableHead>Last modified</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
                          <TableBody>
                            {filteredProviders.map((provider) => (
                              <TableRow key={provider.id}>
                                <TableCell className="font-medium">{provider.name}</TableCell>
                                <TableCell className="max-w-[280px] truncate font-mono text-xs">{provider.base_url}</TableCell>
                                <TableCell><StatusBadge status={provider.status} /></TableCell>
                                <TableCell className="text-muted-foreground">{formatTime(provider.last_modify)}</TableCell>
                                <TableCell className="text-right">
                                  <div className="inline-flex items-center gap-1">
                                    <Button variant="ghost" size="icon-sm" title="Cycle status" aria-label={`Cycle status for ${provider.name}`} onClick={() => void cycleEntityStatus("provider", provider)}><RefreshCw /></Button>
                                    <Button variant="ghost" size="icon-sm" title="Edit provider" aria-label={`Edit ${provider.name}`} onClick={() => openEntityEditor("provider", provider)}><Pencil /></Button>
                                    <Button variant="ghost" size="icon-sm" title="Delete provider" aria-label={`Delete ${provider.name}`} onClick={() => void deleteEntity("provider", provider)}><Trash2 /></Button>
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                            {filteredProviders.length === 0 && <TableRow><TableCell colSpan={5} className="h-24 text-center text-muted-foreground">No providers found.</TableCell></TableRow>}
                          </TableBody>
                        </Table>
                      </CardContent>
                    </Card>
                  </TabsContent>

                  <TabsContent value="models">
                    <Card>
                      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
                        <div><CardTitle>Models</CardTitle><CardDescription>{models.length} configured</CardDescription></div>
                        <div className="flex w-full gap-2 sm:w-auto">
                          <div className="relative min-w-0 flex-1 sm:w-64">
                            <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
                            <Input className="pl-9" placeholder="Filter models" value={dbSearch.models} onChange={(event) => setDbSearch((current) => ({ ...current, models: event.target.value }))} />
                          </div>
                          <Button onClick={() => openEntityEditor("model")} disabled={providers.length === 0}><Plus /> Add model</Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <Table>
                          <TableHeader><TableRow><TableHead>Provider</TableHead><TableHead>Model</TableHead><TableHead>Size</TableHead><TableHead>RPM / TPM</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
                          <TableBody>
                            {filteredModels.map((model) => (
                              <TableRow key={model.id}>
                                <TableCell>{model.provider_name}</TableCell>
                                <TableCell className="font-medium">{model.name}</TableCell>
                                <TableCell>{model.model_size == null ? "—" : `${model.model_size}B`}</TableCell>
                                <TableCell className="text-muted-foreground">{model.RPM ?? "—"} / {model.TPM ?? "—"}</TableCell>
                                <TableCell><StatusBadge status={model.status} /></TableCell>
                                <TableCell className="text-right">
                                  <div className="inline-flex items-center gap-1">
                                    <Button variant="ghost" size="icon-sm" title="Cycle status" aria-label={`Cycle status for ${model.name}`} onClick={() => void cycleEntityStatus("model", model)}><RefreshCw /></Button>
                                    <Button variant="ghost" size="icon-sm" title="Edit model" aria-label={`Edit ${model.name}`} onClick={() => openEntityEditor("model", model)}><Pencil /></Button>
                                    <Button variant="ghost" size="icon-sm" title="Delete model" aria-label={`Delete ${model.name}`} onClick={() => void deleteEntity("model", model)}><Trash2 /></Button>
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                            {filteredModels.length === 0 && <TableRow><TableCell colSpan={6} className="h-24 text-center text-muted-foreground">No models found.</TableCell></TableRow>}
                          </TableBody>
                        </Table>
                      </CardContent>
                    </Card>
                  </TabsContent>

                  <TabsContent value="keys">
                    <Card>
                      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
                        <div><CardTitle>API key references</CardTitle><CardDescription>Secrets are read from your environment, not stored here.</CardDescription></div>
                        <div className="flex w-full gap-2 sm:w-auto">
                          <div className="relative min-w-0 flex-1 sm:w-64">
                            <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
                            <Input className="pl-9" placeholder="Filter keys" value={dbSearch.keys} onChange={(event) => setDbSearch((current) => ({ ...current, keys: event.target.value }))} />
                          </div>
                          <Button onClick={() => openEntityEditor("key")} disabled={providers.length === 0}><Plus /> Add key</Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <Table>
                          <TableHeader><TableRow><TableHead>Provider</TableHead><TableHead>Unique name</TableHead><TableHead>Environment variable</TableHead><TableHead>Configured</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
                          <TableBody>
                            {filteredKeys.map((key) => (
                              <TableRow key={key.id}>
                                <TableCell>{key.provider_name}</TableCell>
                                <TableCell className="font-medium">{key.unique_name}</TableCell>
                                <TableCell className="font-mono text-xs">{key.env_key}</TableCell>
                                <TableCell><Badge variant={key.env_configured ? "default" : "secondary"}>{key.env_configured ? <><Check /> Loaded</> : "Missing"}</Badge></TableCell>
                                <TableCell><StatusBadge status={key.status} /></TableCell>
                                <TableCell className="text-right">
                                  <div className="inline-flex items-center gap-1">
                                    <Button variant="ghost" size="icon-sm" title="Cycle status" aria-label={`Cycle status for ${key.unique_name}`} onClick={() => void cycleEntityStatus("key", key)}><RefreshCw /></Button>
                                    <Button variant="ghost" size="icon-sm" title="Edit key" aria-label={`Edit ${key.unique_name}`} onClick={() => openEntityEditor("key", key)}><Pencil /></Button>
                                    <Button variant="ghost" size="icon-sm" title="Delete key" aria-label={`Delete ${key.unique_name}`} onClick={() => void deleteEntity("key", key)}><Trash2 /></Button>
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                            {filteredKeys.length === 0 && <TableRow><TableCell colSpan={6} className="h-24 text-center text-muted-foreground">No API key references found.</TableCell></TableRow>}
                          </TableBody>
                        </Table>
                      </CardContent>
                    </Card>
                  </TabsContent>
                </Tabs>
              </section>
            )}

            {page === "logs" && (
              <section className="min-h-full p-4 sm:p-6">
                <div className="mx-auto grid max-w-5xl gap-4">
                  <div className="flex flex-wrap items-end justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold">Recent conversations</h2>
                      <p className="text-sm text-muted-foreground">Follow each interaction through LLM tasks, retry attempts, and actual tool executions.</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="flex items-center rounded-lg border p-1" aria-label="Log detail filter">
                        <Button
                          variant={logViewMode === "simple" ? "secondary" : "ghost"}
                          size="sm"
                          aria-pressed={logViewMode === "simple"}
                          onClick={() => setLogViewMode("simple")}
                        >
                          Simple
                        </Button>
                        <Button
                          variant={logViewMode === "full" ? "secondary" : "ghost"}
                          size="sm"
                          aria-pressed={logViewMode === "full"}
                          onClick={() => setLogViewMode("full")}
                        >
                          Full trace
                        </Button>
                      </div>
                      <Button variant="outline" onClick={() => void loadLogs()}><RefreshCw /> Refresh logs</Button>
                    </div>
                  </div>
                  {logConversations.map((conversation) => {
                    const details = logDetails[conversation.ID]
                    const isExpanded = expandedLogId === conversation.ID
                    return (
                      <Card key={conversation.ID}>
                        <CardHeader className="flex flex-row items-center justify-between gap-3">
                          <div className="min-w-0 space-y-1">
                            <CardTitle className="truncate text-base">{conversation.Title || "Untitled conversation"}</CardTitle>
                            <CardDescription className="flex items-center gap-1">
                              <Clock3 className="size-3" />
                              {formatTime(conversation.Created_At)} · Conversation #{conversation.ID}
                            </CardDescription>
                          </div>
                          <Button variant="outline" size="sm" onClick={() => void toggleLogDetails(conversation.ID)}>
                            {isExpanded ? "Collapse" : "Details"} <ChevronDown className={`transition-transform ${isExpanded ? "rotate-180" : ""}`} />
                          </Button>
                        </CardHeader>
                        {isExpanded && (
                          <CardContent className="grid gap-4 border-t pt-4">
                            {loadingLogId === conversation.ID ? (
                              <div className="grid gap-3"><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div>
                            ) : details?.interactives.length ? (
                              details.interactives.map((interactive) => {
                                const iterations = interactive.iterations || []
                                const apiCalls = iterations.flatMap((iteration) => iteration.api_calls)
                                const firstPayload = apiCalls.find((call) => call.Payload)?.Payload
                                const legacyPayload = !firstPayload
                                const interactionPrompt = interactive.Interaction_Prompt || apiCalls[0]?.Interaction_Prompt
                                const executionRecords = getExecutionRecords(interactive)
                                const taskRecords = executionRecords.filter(
                                  (record): record is Extract<LogExecutionRecord, { type: "task" }> => record.type === "task",
                                )
                                const toolRecords = executionRecords.flatMap((record) => record.type === "tool" ? [record.tool] : [])
                                const toolResults = getToolResults(taskRecords.map((record) => record.task))
                                const taskToolExecutions = new Map<number, LogToolExecution[]>()
                                const assignedToolIds = new Set<number>()
                                for (const { task } of taskRecords) {
                                  const requestedCallIds = new Set(
                                    getToolCalls(task.Final_Response).flatMap((call) => call.id ? [call.id] : []),
                                  )
                                  const relatedTools = toolRecords.filter((tool) =>
                                    tool.Task_Id === task.ID ||
                                    (tool.Tool_Call_Id != null && requestedCallIds.has(tool.Tool_Call_Id)),
                                  )
                                  if (relatedTools.length > 0) {
                                    taskToolExecutions.set(task.ID, relatedTools)
                                    relatedTools.forEach((tool) => assignedToolIds.add(tool.ID))
                                  }
                                }
                                const displayExecutionRecords = executionRecords.filter(
                                  (record) => record.type !== "tool" || !assignedToolIds.has(record.ID),
                                )
                                const taskCount = taskRecords.length
                                const toolCount = toolRecords.length
                                return (
                                  <details key={interactive.ID} className="group rounded-lg border bg-card">
                                    <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 p-4 sm:p-5">
                                      <div className="grid min-w-0 gap-1">
                                        <span className="flex flex-wrap items-center gap-2">
                                          <Badge variant="outline">Interaction #{interactive.ID}</Badge>
                                          <StatusBadge status={interactive.Response_Status || "Not_Final"} />
                                          <span className="text-xs text-muted-foreground">{formatTime(interactive.Created_At)}</span>
                                        </span>
                                        {interactionPrompt && <span className="truncate text-sm text-muted-foreground" title={interactionPrompt}>{interactionPrompt}</span>}
                                      </div>
                                      <span className="text-xs text-muted-foreground">
                                        {taskCount} task{taskCount === 1 ? "" : "s"} · {toolCount} tool{toolCount === 1 ? "" : "s"} · {interactive.Duration_Seconds == null ? "Duration not recorded" : `${interactive.Duration_Seconds.toFixed(2)} sec across API attempts`}
                                      </span>
                                    </summary>
                                    <div className="grid gap-4 border-t p-4 sm:p-5">
                                      {logViewMode === "simple" ? (
                                        <>
                                          <div className="grid gap-2">
                                            <p className="text-xs font-medium text-muted-foreground">
                                              {legacyPayload ? "First API payload (not recorded in this older log)" : "First API payload"}
                                            </p>
                                            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted p-3 font-mono text-xs">
                                              {formatPayload(firstPayload)}
                                            </pre>
                                            {legacyPayload && (
                                              <p className="text-xs text-muted-foreground">
                                                This older log did not save API request payloads, so they cannot be recovered.
                                              </p>
                                            )}
                                          </div>
                                          <div className="grid gap-2">
                                            <p className="text-xs font-medium text-muted-foreground">Final response</p>
                                            <div className="rounded-lg bg-muted/50 p-3 text-sm leading-6">
                                              {interactive.Actual_Response
                                                ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{interactive.Actual_Response}</ReactMarkdown>
                                                : <span className="text-muted-foreground">No final response was recorded.</span>}
                                            </div>
                                          </div>
                                        </>
                                      ) : executionRecords.length > 0 ? (
                                        <div className="grid gap-4">
                                          {displayExecutionRecords.map((record, recordIndex) => record.type === "task"
                                            ? <TaskExecutionCard
                                                key={`task-${record.ID}`}
                                                task={record.task}
                                                index={displayExecutionRecords.slice(0, recordIndex + 1).filter((entry) => entry.type === "task").length - 1}
                                                toolExecutions={taskToolExecutions.get(record.ID) || []}
                                                toolResults={toolResults}
                                              />
                                            : <ToolExecutionCard key={`tool-${record.ID}`} tool={record.tool} />)}
                                        </div>
                                      ) : (
                                        <div className="grid gap-2">
                                          <p className="text-xs font-medium text-muted-foreground">Request payload</p>
                                          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted p-3 font-mono text-xs">{formatPayload(interactive.Payload)}</pre>
                                          <p className="text-xs text-muted-foreground">No task or tool execution records were saved for this interaction.</p>
                                        </div>
                                      )}
                                    </div>
                                  </details>
                                )
                              })
                            ) : (
                              <p className="py-4 text-center text-sm text-muted-foreground">No interactions were recorded.</p>
                            )}
                          </CardContent>
                        )}
                      </Card>
                    )
                  })}
                  {logConversations.length === 0 && (
                    <Card><EmptyState icon={History} title="No logs yet" description="Run a chat or agent task to see its execution history here." /></Card>
                  )}
                </div>
              </section>
            )}
            {page === "flow" && <WorkflowPage />}
          </main>
        </div>
      </div>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename conversation</DialogTitle>
            <DialogDescription>Choose a short name so this chat is easy to find later.</DialogDescription>
          </DialogHeader>
          <form onSubmit={renameConversation} className="grid gap-4">
            <Field label="Conversation name" htmlFor="conversation-name">
              <Input id="conversation-name" autoFocus value={renameTitle} onChange={(event) => setRenameTitle(event.target.value)} />
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setRenameOpen(false)}>Cancel</Button>
              <Button type="submit">Save name</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={createToolOpen} onOpenChange={setCreateToolOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Create a Python tool</DialogTitle>
            <DialogDescription>The tool is written into the existing Tools folder and becomes available to the agent.</DialogDescription>
          </DialogHeader>
          <form onSubmit={createTool} className="grid gap-4">
            <Field label="File name" htmlFor="new-tool-file">
              <Input id="new-tool-file" value={newToolFile} onChange={(event) => setNewToolFile(event.target.value)} placeholder="example_tool.py" />
            </Field>
            <Field label="Python code" htmlFor="new-tool-code">
              <Textarea id="new-tool-code" className="min-h-64 font-mono text-xs" value={newToolCode} onChange={(event) => setNewToolCode(event.target.value)} placeholder={"def run(query: str) -> str:\n    \"\"\"Describe what this tool does.\"\"\"\n    return query"} />
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateToolOpen(false)}>Cancel</Button>
              <Button type="submit"><FilePlus2 /> Create tool</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {renderEntityDialog()}
      <Toaster position="bottom-right" />
    </TooltipProvider>
  )
}

export default App
