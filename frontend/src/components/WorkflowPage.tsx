import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  NodeResizer,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
  type Viewport,
} from "@xyflow/react"
import { useEffect, useState } from "react"
import {
  Bot,
  Brain,
  Check,
  CircleAlert,
  CircleHelp,
  Clock3,
  Database,
  Filter,
  GitBranch,
  KeyRound,
  Play,
  RefreshCw,
  Search,
  Server,
  SlidersHorizontal,
  Timer,
  type LucideIcon,
} from "lucide-react"
import "@xyflow/react/dist/style.css"
import "./WorkflowPage.css"

type StepKind = "trigger" | "process" | "condition" | "success" | "error" | "group" | "substep" | "workflow-root" | "backend-root" | "database-root" | "database-table" | "route-group" | "route"
type StepData = {
  title: string
  description: string
  icon: LucideIcon
  kind: StepKind
  category: string
  envVar?: string
  routeMethod?: string
  routeCount?: number
  columns?: DbColumn[]
  tableColor?: string
}
type DbColumn = { name: string; type: string; keys?: ("PK" | "FK" | "NN" | "UQ" | "UQ*")[] }
type FlowNode = Node<StepData, "apiStep">

function ApiStepNode({ data, id, selected }: NodeProps<FlowNode>) {
  const Icon = data.icon
  const { getNodes, setNodes } = useReactFlow<FlowNode, Edge>()

  if (data.kind === "workflow-root" || data.kind === "backend-root" || data.kind === "database-root") {
    const isBackendRoot = data.kind === "backend-root"
    const isDatabaseRoot = data.kind === "database-root"

    return (
      <article className={`workflow-boundary${isBackendRoot ? " workflow-boundary--backend" : ""}${isDatabaseRoot ? " workflow-boundary--database" : ""}`}>
        <NodeResizer
          isVisible={selected}
          minWidth={isBackendRoot ? 1680 : isDatabaseRoot ? 1600 : 1800}
          minHeight={isBackendRoot ? 1200 : isDatabaseRoot ? 1200 : 1500}
          color="#9b6bff"
          lineStyle={{ borderWidth: 2 }}
          handleStyle={{ width: 10, height: 10, borderRadius: 3 }}
        />
        <header className="workflow-boundary__header">
          <span className="api-step__icon"><Icon aria-hidden="true" /></span>
          <span>
            <strong>{data.title}</strong>
            <small>{data.description}</small>
          </span>
        </header>
        {data.kind === "workflow-root" && (
          <>
            <Handle type="target" position={Position.Left} style={{ top: "8%" }} />
            <span className="workflow-boundary__input-label">ENTRY</span>
            <Handle id="success" type="source" position={Position.Right} style={{ top: "58%" }} />
            <Handle id="no-route" type="source" position={Position.Right} style={{ top: "66%" }} />
            <Handle id="max-attempts" type="source" position={Position.Right} style={{ top: "90%" }} />
            <span className="workflow-boundary__output-label workflow-boundary__output-label--success">SUCCESS</span>
            <span className="workflow-boundary__output-label workflow-boundary__output-label--no-route">NO ROUTE</span>
            <span className="workflow-boundary__output-label workflow-boundary__output-label--max-attempts">MAX ATTEMPTS</span>
          </>
        )}
      </article>
    )
  }

  if (data.kind === "database-table") {
    const columns = data.columns ?? []

    return (
      <article className="database-table" style={{ borderColor: data.tableColor }}>
        <NodeResizer
          isVisible={selected}
          minWidth={320}
          minHeight={44 + columns.length * 26}
          color={data.tableColor}
          lineStyle={{ borderWidth: 1.5 }}
          handleStyle={{ width: 8, height: 8, borderRadius: 3 }}
        />
        <header className="database-table__header" style={{ backgroundColor: data.tableColor }}>
          <strong>{data.title}</strong>
          <code>TABLE</code>
        </header>
        <div className="database-table__columns">
          {columns.map((column) => (
            <div className="database-table__column" key={column.name}>
              <span className="database-table__name">
                {column.name}
                {column.keys?.includes("PK") && <span className="database-table__key-icon" aria-label="Primary key">⌑</span>}
                {column.keys?.includes("FK") && <span className="database-table__key-icon" aria-label="Foreign key">↗</span>}
              </span>
              <span className="database-table__type">{column.type}</span>
              <span className="database-table__badges">
                {column.keys?.filter((key) => key !== "PK" && key !== "FK").map((key) => (
                  <code
                    key={key}
                    className={`database-table__badge ${key === "UQ*" ? "database-table__badge--uq-composite" : `database-table__badge--${key.toLowerCase()}`}`}
                  >{key}</code>
                ))}
                {column.keys?.includes("PK") && <code className="database-table__badge database-table__badge--pk">PK</code>}
                {column.keys?.includes("FK") && <code className="database-table__badge database-table__badge--fk">FK</code>}
              </span>
            </div>
          ))}
        </div>
        <Handle id="in" type="target" position={Position.Left} />
        <Handle id="out" type="source" position={Position.Right} />
      </article>
    )
  }

  if (data.kind === "route-group") {
    const alignRoutes = (width: number, height: number) => {
      const routes = getNodes()
        .filter((node) => node.parentId === id && node.data.kind === "route")
        .sort((left, right) => {
          const leftIndex = Number(left.id.split("-").at(-1))
          const rightIndex = Number(right.id.split("-").at(-1))
          return leftIndex - rightIndex
        })
      const routeHeight = 64
      const topPadding = 40
      const bottomPadding = 20
      const routeGap = routes.length > 1
        ? (height - topPadding - bottomPadding - routes.length * routeHeight) / (routes.length - 1)
        : 0

      setNodes((currentNodes) => currentNodes.map((node) => {
        const index = routes.findIndex((route) => route.id === node.id)
        if (index < 0) return node

        return {
          ...node,
          position: { x: 20, y: topPadding + index * (routeHeight + routeGap) },
          style: { ...node.style, width: width - 40, height: routeHeight },
        }
      }))
    }

    return (
      <article className="api-route-group">
        <NodeResizer
          isVisible={selected}
          minWidth={300}
          minHeight={44 + (data.routeCount ?? 1) * 80}
          color="#9b6bff"
          lineStyle={{ borderWidth: 1.5 }}
          handleStyle={{ width: 8, height: 8, borderRadius: 3 }}
          onResize={(_, { width, height }) => alignRoutes(width, height)}
        />
        <strong>{data.title}</strong>
        <span>{data.description}</span>
      </article>
    )
  }

  return (
    <article className={`api-step api-step--${data.kind}`}>
      {data.kind === "route" && (
        <NodeResizer
          isVisible={selected}
          minWidth={220}
          minHeight={64}
          color="#9b6bff"
          lineStyle={{ borderWidth: 1.5 }}
          handleStyle={{ width: 8, height: 8, borderRadius: 3 }}
        />
      )}
      {data.kind !== "substep" && data.kind !== "route" && <Handle type="target" position={Position.Left} />}
      <header className="api-step__header">
        <span className="api-step__icon"><Icon aria-hidden="true" /></span>
        <span className="api-step__category">{data.category}</span>
        {data.routeMethod && <code className={`api-step__method api-step__method--${data.routeMethod.toLowerCase()}`}>{data.routeMethod}</code>}
        {data.envVar && <code className="api-step__env-tag">{data.envVar}</code>}
      </header>
      <strong className="api-step__title">{data.title}</strong>
      <p className="api-step__description">{data.description}</p>
      {data.kind === "condition" ? (
        <>
          <Handle id="yes" type="source" position={Position.Right} style={{ top: "38%" }} />
          <Handle id="no" type="source" position={Position.Right} style={{ top: "70%" }} />
        </>
      ) : data.kind !== "substep" && data.kind !== "route" ? (
        <Handle type="source" position={Position.Right} />
      ) : null}
    </article>
  )
}

const nodeTypes: NodeTypes = { apiStep: ApiStepNode }

const workflowSteps: FlowNode[] = [
  {
    id: "entry",
    type: "apiStep",
    position: { x: 360, y: 0 },
    data: { title: "api_caller", description: "Seed defaults and logging schema; create or reuse conversation context.", icon: Play, kind: "trigger", category: "ENTRY POINT" },
  },
  {
    id: "context",
    type: "apiStep",
    position: { x: 360, y: 160 },
    data: { title: "Initialize request", description: "Create interaction and iteration IDs, set logging context, and read MAX_ITERATIONS.", icon: Database, kind: "process", category: "REQUEST SETUP" },
  },
  {
    id: "find-best",
    type: "apiStep",
    position: { x: 360, y: 320 },
    style: { width: 340, height: 270 },
    data: { title: "find_best_api", description: "Prepare routing state, then select the best active provider/model/key combination.", icon: Search, kind: "group", category: "ROUTE SELECTION" },
  },
  {
    id: "reactivate",
    type: "apiStep",
    parentId: "find-best",
    extent: "parent",
    position: { x: 26, y: 104 },
    style: { width: 288, height: 66 },
    data: { title: "reactivate_expired_cooldowns", description: "Restore expired provider, model, and API-key cooldowns.", icon: RefreshCw, kind: "substep", category: "PREPARE ROUTER" },
  },
  {
    id: "refresh-keys",
    type: "apiStep",
    parentId: "find-best",
    extent: "parent",
    position: { x: 26, y: 184 },
    style: { width: 288, height: 66 },
    data: { title: "update_api_keys", description: "Refresh key state from environment variables.", icon: KeyRound, kind: "substep", category: "PREPARE ROUTER" },
  },
  {
    id: "api-found",
    type: "apiStep",
    position: { x: 360, y: 640 },
    data: { title: "Route available?", description: "Was an active provider, model, and API key combination found?", icon: CircleHelp, kind: "condition", category: "CHECK" },
  },
  {
    id: "waiting-policy",
    type: "apiStep",
    position: { x: -360, y: 800 },
    data: { title: "WAITING_TYPE?", description: "waiting_node reads this setting when no active route is available.", icon: GitBranch, kind: "condition", category: "WAIT POLICY", envVar: "WAITING_TYPE" },
  },
  {
    id: "waiting",
    type: "apiStep",
    position: { x: 0, y: 980 },
    data: { title: "waiting_node", description: "In run_anyhow mode, wait for the earliest cooldown; return fail if none is available.", icon: Clock3, kind: "process", category: "RUN_ANYHOW" },
  },
  {
    id: "retry-wait",
    type: "apiStep",
    position: { x: 0, y: 1140 },
    data: { title: "Retry or fail?", description: "waiting_node returns retry after the cooldown wait, or fail when no cooldown exists.", icon: Timer, kind: "condition", category: "WAIT RESULT" },
  },
  {
    id: "no-route",
    type: "apiStep",
    position: { x: 0, y: 1380 },
    data: { title: "Return route error", description: "Record the interaction as not final and return the no-active-route error.", icon: CircleAlert, kind: "error", category: "FAILURE" },
  },
  {
    id: "provider-call",
    type: "apiStep",
    position: { x: 720, y: 980 },
    data: { title: "call_openai_compatible", description: "Prepare messages and tools, POST to the provider, then parse text or tool calls.", icon: Bot, kind: "process", category: "PROVIDER REQUEST" },
  },
  {
    id: "call-success",
    type: "apiStep",
    position: { x: 720, y: 1160 },
    data: { title: "Provider succeeded?", description: "Did the HTTP request return a valid response?", icon: CircleHelp, kind: "condition", category: "CHECK" },
  },
  {
    id: "return-success",
    type: "apiStep",
    position: { x: 400, y: 1380 },
    data: { title: "Finalize and return", description: "Mark the interaction final when owned, then return the response and chosen route.", icon: Check, kind: "success", category: "SUCCESS" },
  },
  {
    id: "parse-response",
    type: "apiStep",
    position: { x: 1072, y: 1482 },
    style: { width: 270, height: 132 },
    data: { title: "parse_api_response", description: "Parse the provider error into an action or UNKNOWN.", icon: SlidersHorizontal, kind: "process", category: "STATIC PARSER" },
  },
  {
    id: "use-laya",
    type: "apiStep",
    position: { x: 1390, y: 1482 },
    style: { width: 250, height: 132 },
    data: { title: "Use Laya?", description: "Only when PARSER_MODE=laya and the parser returned UNKNOWN.", icon: CircleHelp, kind: "condition", category: "CHECK", envVar: "PARSER_MODE" },
  },
  {
    id: "laya-decision",
    type: "apiStep",
    position: { x: 1390, y: 1680 },
    style: { width: 250, height: 132 },
    data: { title: "decide_with_laya", description: "Choose a recovery action. If Laya is unavailable, errors, or returns an invalid action, fall back to the static parser.", icon: Brain, kind: "process", category: "LAYA" },
  },
  {
    id: "update-db",
    type: "apiStep",
    position: { x: 2100, y: 1640 },
    data: { title: "update_api_database", description: "Apply the recovery action: disable or cool down the provider, model, or key.", icon: Database, kind: "process", category: "RECOVERY" },
  },
  {
    id: "exclude",
    type: "apiStep",
    position: { x: 2100, y: 1820 },
    data: { title: "Exclude failed route", description: "Exclude the key, model, or provider indicated by the recovery action; UNKNOWN leaves exclusions unchanged.", icon: Filter, kind: "process", category: "FAILOVER" },
  },
  {
    id: "attempts-left",
    type: "apiStep",
    position: { x: 2100, y: 2000 },
    data: { title: "Max iterations reached?", description: "The loop allows up to MAX_ITERATIONS provider attempts.", icon: CircleHelp, kind: "condition", category: "LOOP CHECK", envVar: "MAX_ITERATIONS" },
  },
  {
    id: "max-failure",
    type: "apiStep",
    position: { x: 2460, y: 2180 },
    data: { title: "Return max-attempts error", description: "Record the interaction as not final and report that all API attempts failed.", icon: CircleAlert, kind: "error", category: "FAILURE" },
  },
]

const backendRouteGroups = [
  {
    id: "providers",
    title: "Providers",
    routes: [
      ["GET", "/api/providers", "list_providers"],
      ["POST", "/api/providers", "add_provider"],
      ["PUT", "/api/providers/{provider_id}", "update_provider"],
      ["DELETE", "/api/providers/{provider_id}", "delete_provider"],
    ],
  },
  {
    id: "models",
    title: "Models",
    routes: [
      ["GET", "/api/models", "list_models"],
      ["POST", "/api/models", "add_model"],
      ["PUT", "/api/models/{model_id}", "update_model"],
      ["DELETE", "/api/models/{model_id}", "delete_model"],
    ],
  },
  {
    id: "api-keys",
    title: "API Keys",
    routes: [
      ["GET", "/api/api-keys", "list_api_keys"],
      ["POST", "/api/api-keys", "add_api_key"],
      ["PUT", "/api/api-keys/{key_id}", "update_api_key"],
      ["DELETE", "/api/api-keys/{key_id}", "delete_api_key"],
    ],
  },
  {
    id: "tools",
    title: "Tools",
    routes: [
      ["GET", "/api/tools", "list_tools"],
      ["POST", "/api/tools/execute", "execute_tool_manually"],
      ["POST", "/api/tools/create", "create_new_tool"],
    ],
  },
  {
    id: "conversations",
    title: "Conversations",
    routes: [
      ["GET", "/api/conversations", "list_conversations"],
      ["POST", "/api/conversations", "create_new_conversation"],
      ["GET", "/api/conversations/{conv_id}/messages", "get_conversation_messages"],
      ["PATCH", "/api/conversations/{conv_id}", "rename_conversation"],
      ["DELETE", "/api/conversations/{conv_id}", "delete_conversation"],
    ],
  },
  {
    id: "mesh",
    title: "Mesh",
    routes: [
      ["GET", "/api/mesh/snapshot", "get_mesh_snapshot"],
      ["POST", "/api/mesh/send", "send_mesh_message"],
      ["POST", "/api/mesh/connect", "connect_mesh_peer"],
      ["POST", "/api/mesh/name", "set_mesh_name"],
      ["POST", "/api/mesh/agent", "call_peer_agent"],
    ],
  },
  {
    id: "chat",
    title: "Chat",
    routes: [["POST", "/api/chat", "handle_chat_message"]],
  },
  {
    id: "logs",
    title: "Logs",
    routes: [
      ["GET", "/api/logs/conversations", "get_conversations"],
      ["GET", "/api/logs/conversations/{conv_id}", "get_conversation_details"],
    ],
  },
  {
    id: "system",
    title: "System",
    routes: [
      ["GET", "/api/stats", "get_system_stats"],
      ["GET", "/", "serve_index"],
    ],
  },
] as const

const databaseTables: {
  id: string
  name: string
  color: string
  position: { x: number; y: number }
  width: number
  columns: DbColumn[]
}[] = [
  {
    id: "providers",
    name: "providers",
    color: "#e54ca1",
    position: { x: 40, y: 100 },
    width: 420,
    columns: [
      { name: "id", type: "INTEGER", keys: ["PK"] },
      { name: "name", type: "TEXT", keys: ["NN", "UQ"] },
      { name: "base_url", type: "TEXT", keys: ["NN"] },
      { name: "status", type: "TEXT", keys: ["NN"] },
      { name: "rate_limit", type: "TEXT" },
      { name: "created_at", type: "TEXT", keys: ["NN"] },
      { name: "last_modify", type: "TEXT", keys: ["NN"] },
    ],
  },
  {
    id: "models",
    name: "models",
    color: "#08b5c8",
    position: { x: 500, y: 100 },
    width: 440,
    columns: [
      { name: "id", type: "INTEGER", keys: ["PK"] },
      { name: "provider_id", type: "INTEGER", keys: ["FK", "NN", "UQ*"] },
      { name: "name", type: "TEXT", keys: ["NN", "UQ*"] },
      { name: "status", type: "TEXT", keys: ["NN"] },
      { name: "preference", type: "TEXT" },
      { name: "model_size", type: "TEXT" },
      { name: "RPM", type: "INTEGER" },
      { name: "RPD", type: "INTEGER" },
      { name: "TPM", type: "INTEGER" },
      { name: "TPD", type: "INTEGER" },
      { name: "disabled_reason", type: "TEXT" },
      { name: "rate_limit", type: "TEXT" },
      { name: "created_at", type: "TEXT", keys: ["NN"] },
      { name: "last_modify", type: "TEXT", keys: ["NN"] },
    ],
  },
  {
    id: "api_keys",
    name: "api_keys",
    color: "#a246e8",
    position: { x: 1000, y: 100 },
    width: 440,
    columns: [
      { name: "id", type: "INTEGER", keys: ["PK"] },
      { name: "provider_id", type: "INTEGER", keys: ["FK", "NN", "UQ*"] },
      { name: "unique_name", type: "TEXT", keys: ["NN", "UQ*"] },
      { name: "env_key", type: "TEXT", keys: ["NN", "UQ"] },
      { name: "status", type: "TEXT", keys: ["NN"] },
      { name: "rate_limit", type: "TEXT" },
      { name: "disabled_reason", type: "TEXT" },
      { name: "created_at", type: "TEXT", keys: ["NN"] },
      { name: "last_modify", type: "TEXT", keys: ["NN"] },
    ],
  },
  {
    id: "conversation",
    name: "Conversation",
    color: "#18b49c",
    position: { x: 40, y: 700 },
    width: 420,
    columns: [
      { name: "ID", type: "INTEGER", keys: ["PK"] },
      { name: "Title", type: "VARCHAR(255)" },
      { name: "Created_At", type: "TIMESTAMP" },
      { name: "Updated_At", type: "TIMESTAMP" },
      { name: "Next_Interaction_Id", type: "INTEGER", keys: ["NN"] },
    ],
  },
  {
    id: "api-call-log",
    name: "API_Call_Log",
    color: "#397bea",
    position: { x: 500, y: 700 },
    width: 560,
    columns: [
      { name: "API_Call_Id", type: "INTEGER", keys: ["PK"] },
      { name: "Conversation_Id", type: "INTEGER", keys: ["FK", "NN"] },
      { name: "Interaction_Id", type: "INTEGER", keys: ["NN"] },
      { name: "Iteration_Id", type: "INTEGER", keys: ["NN"] },
      { name: "URL", type: "TEXT" },
      { name: "Model", type: "TEXT" },
      { name: "API_Name", type: "TEXT" },
      { name: "Payload", type: "TEXT" },
      { name: "Response", type: "TEXT" },
      { name: "Request_Status", type: "TEXT", keys: ["NN"] },
      { name: "Final_Response", type: "INTEGER" },
      { name: "Timestamp", type: "TEXT", keys: ["NN"] },
      { name: "Duration", type: "REAL" },
      { name: "Is_Complete", type: "INTEGER", keys: ["NN"] },
      { name: "Task_Started_At", type: "TEXT" },
      { name: "Task_Duration_Seconds", type: "REAL" },
      { name: "Task_Is_Complete", type: "INTEGER", keys: ["NN"] },
      { name: "Recovery_Mode", type: "TEXT" },
      { name: "Recovery_Request", type: "TEXT" },
      { name: "Recovery_Action", type: "TEXT" },
      { name: "Wait_Duration_Seconds", type: "REAL" },
      { name: "Interaction_Prompt", type: "TEXT" },
      { name: "Legacy_Record", type: "INTEGER", keys: ["NN"] },
    ],
  },
  {
    id: "tool-execution",
    name: "Tool_Execution",
    color: "#e9973e",
    position: { x: 1120, y: 700 },
    width: 500,
    columns: [
      { name: "ID", type: "INTEGER", keys: ["PK"] },
      { name: "Conversation_Id", type: "INTEGER", keys: ["FK", "NN"] },
      { name: "Interaction_Id", type: "INTEGER", keys: ["NN"] },
      { name: "Task_Id", type: "INTEGER" },
      { name: "Tool_Call_Id", type: "TEXT" },
      { name: "Name", type: "TEXT", keys: ["NN"] },
      { name: "Parameters", type: "TEXT" },
      { name: "Response", type: "TEXT" },
      { name: "Error", type: "TEXT" },
      { name: "Status", type: "TEXT", keys: ["NN"] },
      { name: "Timestamp", type: "TEXT", keys: ["NN"] },
      { name: "Duration", type: "REAL" },
    ],
  },
]

const gridSize = 20
const snapPosition = (position: { x: number; y: number }) => ({
  x: Math.round(position.x / gridSize) * gridSize,
  y: Math.round(position.y / gridSize) * gridSize,
})
const canvasOffset = { x: 500, y: 200 }
const initialNodes: FlowNode[] = [
  {
    id: "workflow-root",
    type: "apiStep",
    position: { x: -canvasOffset.x, y: -canvasOffset.y },
    style: { width: 3300, height: 2800 },
    zIndex: -1,
    data: {
      title: "api_caller",
      description: "Complete API caller workflow",
      icon: GitBranch,
      kind: "workflow-root",
      category: "WORKFLOW",
    },
  },
  ...workflowSteps.map((node): FlowNode => ({
    ...node,
    parentId: node.parentId ?? "workflow-root",
    extent: "parent",
    position: node.parentId
      ? snapPosition(node.position)
      : snapPosition({
          x: node.position.x + canvasOffset.x,
          y: node.position.y + canvasOffset.y,
        }),
  })),
  {
    id: "backend-server",
    type: "apiStep",
    position: { x: 3400, y: 0 },
    style: { width: 1720, height: 1200 },
    zIndex: -1,
    data: {
      title: "Backend Server",
      description: "FastAPI route handlers from backend/server.py",
      icon: Server,
      kind: "backend-root",
      category: "HTTP ROUTES",
    },
  },
  ...backendRouteGroups.flatMap((group, groupIndex): FlowNode[] => {
    const column = groupIndex % 3
    const row = Math.floor(groupIndex / 3)
    const groupHeight = 44 + group.routes.length * 80
    const precedingRowsHeight = Array.from({ length: row }, (_, precedingRow) => {
      const groupsInRow = backendRouteGroups.slice(precedingRow * 3, precedingRow * 3 + 3)
      return Math.max(...groupsInRow.map((item) => 44 + item.routes.length * 80))
    }).reduce((total, height) => total + height + gridSize, 0)
    const groupId = `backend-route-group-${group.id}`

    return [
      {
        id: groupId,
        type: "apiStep",
        parentId: "backend-server",
        extent: "parent",
        position: { x: 20 + column * 560, y: 80 + precedingRowsHeight },
        style: { width: 540, height: groupHeight },
        data: {
          title: group.title,
          description: `${group.routes.length} routes`,
          icon: Server,
          kind: "route-group",
          category: "ROUTE CATEGORY",
          routeCount: group.routes.length,
        },
      },
      ...group.routes.map(([method, path, handler], routeIndex): FlowNode => ({
        id: `backend-route-${group.id}-${routeIndex}`,
        type: "apiStep",
        parentId: groupId,
        extent: "parent",
        position: {
          x: 20,
          y: 40 + routeIndex * 80,
        },
        style: { width: 500, height: 64 },
        draggable: false,
        data: {
          title: path,
          description: handler,
          icon: Server,
          kind: "route",
          category: "ENDPOINT",
          routeMethod: method,
        },
      })),
    ]
  }),
  {
    id: "database-root",
    type: "apiStep",
    position: { x: 5300, y: 0 },
    style: { width: 1800, height: 1500 },
    zIndex: -1,
    data: {
      title: "Database",
      description: "SQLite · API_Store.db · UQ* = composite unique",
      icon: Database,
      kind: "database-root",
      category: "DATABASE SCHEMA",
    },
  },
  ...databaseTables.map((table): FlowNode => ({
    id: `db-table-${table.id}`,
    type: "apiStep",
    parentId: "database-root",
    extent: "parent",
    position: table.position,
    style: { width: table.width, height: 44 + table.columns.length * 26 },
    data: {
      title: table.name,
      description: `${table.columns.length} columns`,
      icon: Database,
      kind: "database-table",
      category: "TABLE",
      columns: table.columns,
      tableColor: table.color,
    },
  })),
]

const layoutStorageKey = "brain-studio-api-caller-layout"
const decisionChildIds = [
  "parse-response",
  "use-laya",
  "laya-decision",
]
type SavedLayout = {
  version: number
  positions: Record<string, { x: number; y: number }>
  sizes: Record<string, { width: number; height: number }>
  viewport: Viewport
}

function loadSavedLayout(): SavedLayout | null {
  try {
    const saved = localStorage.getItem(layoutStorageKey)
    if (!saved) return null

    const parsed: unknown = JSON.parse(saved)
    if (typeof parsed !== "object" || parsed === null) return null

    const layout = parsed as Partial<SavedLayout>
    const viewport = layout.viewport
    if (
      typeof viewport !== "object" ||
      viewport === null ||
      !Number.isFinite(viewport.x) ||
      !Number.isFinite(viewport.y) ||
      !Number.isFinite(viewport.zoom) ||
      viewport.zoom <= 0
    ) {
      return null
    }

    const positions: SavedLayout["positions"] = {}
    const sizes: SavedLayout["sizes"] = {}
    if (typeof layout.positions === "object" && layout.positions !== null) {
      for (const [id, position] of Object.entries(layout.positions)) {
        if (
          typeof position === "object" &&
          position !== null &&
          Number.isFinite(position.x) &&
          Number.isFinite(position.y) &&
          (initialNodes.some((node) => node.id === id) || id === "decide")
        ) {
          positions[id] = { x: position.x, y: position.y }
        }
      }
    }

    if (typeof layout.sizes === "object" && layout.sizes !== null) {
      for (const [id, size] of Object.entries(layout.sizes)) {
        if (
          typeof size === "object" &&
          size !== null &&
          Number.isFinite(size.width) &&
          Number.isFinite(size.height) &&
          initialNodes.some((node) => node.id === id)
        ) {
          sizes[id] = { width: size.width, height: size.height }
        }
      }
    }

    const version = layout.version ?? 1
    if (version < 2) {
      positions["workflow-root"] ??= { x: -canvasOffset.x, y: -canvasOffset.y }
      for (const node of workflowSteps) {
        if (node.parentId || decisionChildIds.includes(node.id)) continue
        const position = positions[node.id]
        if (position) {
          positions[node.id] = {
            x: position.x + canvasOffset.x,
            y: position.y + canvasOffset.y,
          }
        }
      }
      if (positions.decide) {
        positions.decide = {
          x: positions.decide.x + canvasOffset.x,
          y: positions.decide.y + canvasOffset.y,
        }
      }
    }

    if (version < 3) {
      const decisionPosition = positions.decide ?? { x: 1040 + canvasOffset.x, y: 1380 + canvasOffset.y }
      for (const id of decisionChildIds) {
        const position = positions[id]
        if (position) {
          positions[id] = { x: position.x + decisionPosition.x, y: position.y + decisionPosition.y }
        }
      }
      delete positions.decide
    }

    const groupPosition = positions["find-best"] ?? initialNodes.find((node) => node.id === "find-best")?.position
    const nextStepPosition = positions["api-found"]
    if (groupPosition && nextStepPosition && nextStepPosition.y < groupPosition.y + 320) {
      positions["api-found"] = { ...nextStepPosition, y: groupPosition.y + 320 }
    }

    for (const node of initialNodes) {
      const position = positions[node.id]
      if (position) positions[node.id] = snapPosition(position)
    }

    return { version: 5, positions, sizes, viewport }
  } catch (error) {
    console.error("Could not restore the API caller graph layout.", error)
    return null
  }
}

const edgeStyle = { stroke: "var(--muted-foreground)", strokeWidth: 1.6 }
const initialEdges: Edge[] = [
  { id: "entry-context", source: "entry", target: "context" },
  { id: "context-find", source: "context", target: "find-best" },
  { id: "find-check", source: "find-best", target: "api-found" },
  { id: "no-wait-policy", source: "api-found", sourceHandle: "no", target: "waiting-policy", label: "No active route", type: "smoothstep" },
  { id: "normal-fail", source: "waiting-policy", sourceHandle: "yes", target: "no-route", label: "normal → fail", type: "smoothstep" },
  { id: "anyhow-wait", source: "waiting-policy", sourceHandle: "no", target: "waiting", label: "run_anyhow", type: "smoothstep" },
  { id: "wait-check", source: "waiting", target: "retry-wait" },
  { id: "wait-retry", source: "retry-wait", sourceHandle: "yes", target: "find-best", label: "Wait, clear exclusions, retry", type: "smoothstep" },
  { id: "wait-fail", source: "retry-wait", sourceHandle: "no", target: "no-route", label: "No cooldown → fail", type: "smoothstep" },
  { id: "found-call", source: "api-found", sourceHandle: "yes", target: "provider-call", label: "Route found", type: "smoothstep" },
  { id: "call-check", source: "provider-call", target: "call-success" },
  { id: "success-return", source: "call-success", sourceHandle: "yes", target: "return-success", label: "Success", type: "smoothstep" },
  { id: "call-decide", source: "call-success", sourceHandle: "no", target: "parse-response", label: "Failed", type: "smoothstep" },
  { id: "parse-check-laya", source: "parse-response", target: "use-laya" },
  { id: "parser-known", source: "use-laya", sourceHandle: "no", target: "update-db", label: "Use parser action", type: "smoothstep" },
  { id: "parser-unknown", source: "use-laya", sourceHandle: "yes", target: "laya-decision", label: "Laya mode + UNKNOWN", type: "smoothstep" },
  { id: "laya-update-recovery", source: "laya-decision", target: "update-db", label: "Laya action or parser fallback", type: "smoothstep" },
  { id: "update-exclude", source: "update-db", target: "exclude" },
  { id: "exclude-attempts", source: "exclude", target: "attempts-left" },
  { id: "attempts-loop", source: "attempts-left", sourceHandle: "no", target: "find-best", label: "Continue", type: "smoothstep" },
  { id: "attempts-fail", source: "attempts-left", sourceHandle: "yes", target: "max-failure", label: "Stop", type: "smoothstep" },
  { id: "db-providers-models", source: "db-table-providers", sourceHandle: "out", target: "db-table-models", targetHandle: "in", label: "1 : N", type: "smoothstep" },
  { id: "db-providers-keys", source: "db-table-providers", sourceHandle: "out", target: "db-table-api_keys", targetHandle: "in", label: "1 : N", type: "smoothstep" },
  { id: "db-conversation-api-log", source: "db-table-conversation", sourceHandle: "out", target: "db-table-api-call-log", targetHandle: "in", label: "1 : N", type: "smoothstep" },
  { id: "db-conversation-tool-execution", source: "db-table-conversation", sourceHandle: "out", target: "db-table-tool-execution", targetHandle: "in", label: "1 : N", type: "smoothstep" },
].map((edge) => ({
  ...edge,
  markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
  style: edgeStyle,
  labelStyle: { fill: "var(--muted-foreground)", fontSize: 10 },
  labelBgStyle: { fill: "var(--background)", fillOpacity: 0.9 },
}))

function WorkflowPage() {
  const [savedLayout] = useState(loadSavedLayout)
  const [nodes, , onNodesChange] = useNodesState(
    initialNodes.map((node): FlowNode => {
      const savedSize = savedLayout?.sizes[node.id]
      const parentWidth = node.parentId
        ? savedLayout?.sizes[node.parentId]?.width ?? 540
        : undefined

      return {
        ...node,
        style: {
          ...node.style,
          ...(savedSize ?? {}),
          ...(node.data.kind === "route" && !savedSize && parentWidth
            ? { width: parentWidth - 40, height: 64 }
            : {}),
        },
        position: node.data.kind === "route"
          ? node.position
          : savedLayout?.positions[node.id] ?? node.position,
      }
    }),
  )
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)
  const [viewport, setViewport] = useState<Viewport>(
    savedLayout?.viewport ?? { x: 0, y: 0, zoom: 1 },
  )

  useEffect(() => {
    try {
      const positions = Object.fromEntries(
        nodes.map((node) => [node.id, { x: node.position.x, y: node.position.y }]),
      )
      const sizes = Object.fromEntries(
        nodes.flatMap((node) => {
          const width = node.width ?? node.measured?.width ?? node.style?.width
          const height = node.height ?? node.measured?.height ?? node.style?.height
          return (node.id === "workflow-root" ||
            node.id === "backend-server" ||
            node.id === "database-root" ||
            node.data.kind === "route-group" ||
            node.data.kind === "database-table" ||
            node.data.kind === "route") &&
            typeof width === "number" &&
            typeof height === "number"
            ? [[node.id, { width, height }]]
            : []
        }),
      )
      localStorage.setItem(layoutStorageKey, JSON.stringify({ version: 5, positions, sizes, viewport }))
    } catch (error) {
      console.error("Could not save the API caller graph layout.", error)
    }
  }, [nodes, viewport])

  return (
    <section className="flow-page" aria-label="API caller workflow diagram">
      <ReactFlow<FlowNode, Edge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onMoveEnd={(_, nextViewport) => setViewport(nextViewport)}
        className="api-flow"
        defaultViewport={viewport}
        minZoom={0.15}
        maxZoom={1.8}
        panOnDrag
        zoomOnScroll
        snapToGrid
        snapGrid={[gridSize, gridSize]}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: "smoothstep" }}
      >
        <Background variant={BackgroundVariant.Dots} gap={gridSize} size={1} />
        <Controls position="bottom-left" showInteractive={false} />
        <MiniMap
          position="bottom-right"
          pannable
          zoomable
          nodeColor={(node) => {
            const kind = (node.data as StepData).kind
            return kind === "trigger" ? "#8b5cf6" : kind === "condition" ? "#f59e0b" : kind === "success" ? "#22a06b" : kind === "error" ? "#ef6461" : "#64748b"
          }}
        />
      </ReactFlow>
    </section>
  )
}

export default WorkflowPage
