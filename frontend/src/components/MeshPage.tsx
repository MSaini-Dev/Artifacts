import { useCallback, useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from "react"
import {
  Bot,
  CircleAlert,
  LoaderCircle,
  MessageSquare,
  Network,
  Plus,
  Send,
  UserRound,
} from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { toast } from "sonner"
import { apiRequest, jsonBody } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"

type MeshGraphNode = {
  addr?: string
  neighbors?: string[]
  last_seen?: number
  name?: string
}

type MeshStatus = {
  self_id: string
  self_addr: string
  self_name: string
  graph: Record<string, MeshGraphNode>
}

type MeshEnvelope = {
  from?: string
  to?: string
  msg: string
  ts?: number
  path?: string[]
}

type MeshSnapshot = {
  mesh_api_url: string
  status: MeshStatus
  inbox: MeshEnvelope[]
  sent: MeshEnvelope[]
}

type LocalAgentMessage = {
  id: string
  peerId: string
  role: "user" | "assistant"
  content: string
  createdAt: number
}

type Props = {
  temperature: number
  maxTurns: number
}

const graphWidth = 640
const graphHeight = 520

function nodeName(id: string, graph: Record<string, MeshGraphNode>, selfId: string): string {
  if (id === selfId) return graph[id]?.name || "This laptop"
  return graph[id]?.name || id.slice(0, 8)
}

function makeNodePositions(ids: string[], selfId: string): Record<string, [number, number]> {
  const positions: Record<string, [number, number]> = { [selfId]: [graphWidth / 2, graphHeight / 2] }
  const peers = ids.filter((id) => id !== selfId)
  const radius = Math.max(90, Math.min(graphWidth, graphHeight) * 0.34)
  peers.forEach((id, index) => {
    const angle = (2 * Math.PI * index) / Math.max(1, peers.length) - Math.PI / 2
    positions[id] = [
      graphWidth / 2 + radius * Math.cos(angle),
      graphHeight / 2 + radius * Math.sin(angle),
    ]
  })
  return positions
}

function formatMeshError(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function MeshPage({ temperature, maxTurns }: Props) {
  const [snapshot, setSnapshot] = useState<MeshSnapshot | null>(null)
  const [meshError, setMeshError] = useState("")
  const [selectedPeer, setSelectedPeer] = useState("")
  const [messageMode, setMessageMode] = useState<"human" | "agent">("human")
  const [text, setText] = useState("")
  const [sending, setSending] = useState(false)
  const [peerUrl, setPeerUrl] = useState("")
  const [connecting, setConnecting] = useState(false)
  const [nameDraft, setNameDraft] = useState<string | null>(null)
  const [savingName, setSavingName] = useState(false)
  const [agentConversationIds, setAgentConversationIds] = useState<Record<string, number>>(() => {
    try {
      const saved = localStorage.getItem("mesh-agent-conversations")
      return saved ? JSON.parse(saved) as Record<string, number> : {}
    } catch {
      return {}
    }
  })
  const [agentMessages, setAgentMessages] = useState<LocalAgentMessage[]>([])

  const refreshSnapshot = useCallback(async () => {
    try {
      const result = await apiRequest<MeshSnapshot>("/api/mesh/snapshot")
      setSnapshot(result)
      setMeshError("")
    } catch (error) {
      setMeshError(formatMeshError(error))
    }
  }, [])

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => void refreshSnapshot(), 0)
    const timer = window.setInterval(() => void refreshSnapshot(), 2000)
    return () => {
      window.clearTimeout(initialRefresh)
      window.clearInterval(timer)
    }
  }, [refreshSnapshot])

  const status = snapshot?.status
  const graph = useMemo(() => status?.graph ?? {}, [status?.graph])
  const selfId = status?.self_id ?? ""
  const nodeIds = useMemo(() => Object.keys(graph), [graph])
  const peers = useMemo(() => nodeIds.filter((id) => id !== selfId), [nodeIds, selfId])
  const reachable = useMemo(() => {
    const seen = new Set<string>(selfId ? [selfId] : [])
    const queue = selfId ? [selfId] : []
    while (queue.length) {
      const current = queue.shift()!
      for (const neighbor of graph[current]?.neighbors || []) {
        if (!seen.has(neighbor) && graph[neighbor]) {
          seen.add(neighbor)
          queue.push(neighbor)
        }
      }
    }
    return seen
  }, [graph, selfId])

  const activePeer = selectedPeer && graph[selectedPeer] ? selectedPeer : peers[0] || ""
  const positions = makeNodePositions(nodeIds, selfId)
  const isReachable = Boolean(activePeer && reachable.has(activePeer))
  const peerMessages = useMemo(() => {
    if (!snapshot || !activePeer) return []
    const received = snapshot.inbox
      .filter((message) => message.from === activePeer)
      .map((message, index) => ({
        id: `received-${message.ts ?? index}-${index}`,
        mine: false,
        content: message.msg,
        createdAt: message.ts ?? 0,
        kind: "human" as const,
      }))
    const sent = snapshot.sent
      .filter((message) => message.to === activePeer)
      .map((message, index) => ({
        id: `sent-${message.ts ?? index}-${index}`,
        mine: true,
        content: message.msg,
        createdAt: message.ts ?? 0,
        kind: "human" as const,
      }))
    const agent = agentMessages
      .filter((message) => message.peerId === activePeer)
      .map((message) => ({
        id: message.id,
        mine: message.role === "user",
        content: message.content,
        createdAt: message.createdAt,
        kind: "agent" as const,
      }))
    return [...received, ...sent, ...agent].sort((a, b) => a.createdAt - b.createdAt)
  }, [activePeer, agentMessages, snapshot])

  const send = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const message = text.trim()
    if (!message || !activePeer || !isReachable || sending) return

    setSending(true)
    setText("")
    try {
      if (messageMode === "human") {
        await apiRequest("/api/mesh/send", {
          method: "POST",
          body: jsonBody({ dest: activePeer, msg: message }),
        })
        await refreshSnapshot()
      } else {
        const requestId = `agent-user-${Date.now()}`
        setAgentMessages((current) => [
          ...current,
          { id: requestId, peerId: activePeer, role: "user", content: message, createdAt: Date.now() / 1000 },
        ])
        const result = await apiRequest<{
          success: boolean
          response: string | null
          error?: string
          duration_ms?: number
          conversation_id?: number
        }>("/api/mesh/agent", {
          method: "POST",
          body: jsonBody({
            peer_id: activePeer,
            message,
            temperature,
            max_turns: maxTurns,
            conversation_id: agentConversationIds[activePeer] ?? null,
          }),
        })
        if (!result.success) throw new Error(result.error || "Remote agent request failed")
        if (result.conversation_id) {
          const next = { ...agentConversationIds, [activePeer]: result.conversation_id }
          setAgentConversationIds(next)
          localStorage.setItem("mesh-agent-conversations", JSON.stringify(next))
        }
        setAgentMessages((current) => [
          ...current,
          {
            id: `agent-reply-${Date.now()}`,
            peerId: activePeer,
            role: "assistant",
            content: result.response || "",
            createdAt: Date.now() / 1000,
          },
        ])
      }
    } catch (error) {
      setText(message)
      toast.error(messageMode === "human"
        ? `Could not send Mesh message: ${formatMeshError(error)}`
        : `Could not call the peer agent: ${formatMeshError(error)}`)
    } finally {
      setSending(false)
    }
  }

  const connectPeer = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!peerUrl.trim() || connecting) return
    setConnecting(true)
    try {
      await apiRequest("/api/mesh/connect", {
        method: "POST",
        body: jsonBody({ url: peerUrl.trim() }),
      })
      setPeerUrl("")
      toast.success("Connecting to Mesh peer")
      window.setTimeout(() => void refreshSnapshot(), 1000)
    } catch (error) {
      toast.error(`Could not connect to peer: ${formatMeshError(error)}`)
    } finally {
      setConnecting(false)
    }
  }

  const saveName = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const name = (nameDraft ?? status?.self_name ?? "").trim()
    if (!name || savingName) return
    setSavingName(true)
    try {
      await apiRequest("/api/mesh/name", {
        method: "POST",
        body: jsonBody({ name }),
      })
      await refreshSnapshot()
    } catch (error) {
      toast.error(`Could not save Mesh name: ${formatMeshError(error)}`)
    } finally {
      setSavingName(false)
    }
  }

  const onMessageKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  return (
    <section className="mesh-layout" aria-label="Mesh workspace">
      <div className="mesh-workspace">
        <div className="mesh-workspace__toolbar">
          <form className="mesh-name-form" onSubmit={saveName}>
            <label htmlFor="mesh-node-name">This node</label>
            <Input
              id="mesh-node-name"
              aria-label="This node name"
              maxLength={32}
              value={nameDraft ?? status?.self_name ?? ""}
              onChange={(event) => setNameDraft(event.target.value)}
              placeholder="Laptop name"
              disabled={!status}
            />
            <Button type="submit" variant="outline" size="sm" disabled={!status || savingName || !(nameDraft ?? status?.self_name ?? "").trim()}>
              {savingName ? <LoaderCircle className="animate-spin" /> : "Save"}
            </Button>
          </form>
          <Badge variant={meshError ? "destructive" : "secondary"}>
            <span className={`mesh-status-dot${meshError ? " is-offline" : ""}`} />
            {meshError ? "Node offline" : `${peers.length} peer${peers.length === 1 ? "" : "s"}`}
          </Badge>
        </div>

        <div className="mesh-network-canvas">
          {status ? (
            <>
              {peers.length === 0 && (
                <div className="mesh-network-empty">
                  <Network />
                  <strong>Waiting for other nodes to join</strong>
                  <span>Connect this Mesh node to another laptop on your network.</span>
                </div>
              )}
              <svg
                className="mesh-network-graph"
                viewBox={`0 0 ${graphWidth} ${graphHeight}`}
                role="group"
                aria-label="Mesh peers"
              >
                {Object.entries(graph).flatMap(([id, info]) =>
                  (info.neighbors || []).flatMap((neighbor) => {
                    if (id >= neighbor || !positions[id] || !positions[neighbor]) return []
                    const [x1, y1] = positions[id]
                    const [x2, y2] = positions[neighbor]
                    return [<line key={`${id}-${neighbor}`} className="mesh-network-edge" x1={x1} y1={y1} x2={x2} y2={y2} />]
                  }),
                )}
                {nodeIds.map((id) => {
                  const [x, y] = positions[id]
                  const isSelf = id === selfId
                  const online = reachable.has(id)
                  return (
                    <g
                      key={id}
                      className={`mesh-network-node${isSelf ? " is-self" : ""}${online ? "" : " is-offline"}${activePeer === id ? " is-selected" : ""}`}
                      transform={`translate(${x} ${y})`}
                      role="button"
                      tabIndex={isSelf ? -1 : 0}
                      aria-label={`${nodeName(id, graph, selfId)}${online ? ", reachable" : ", offline"}`}
                      aria-pressed={activePeer === id}
                      onClick={() => !isSelf && setSelectedPeer(id)}
                      onKeyDown={(event) => {
                        if (!isSelf && (event.key === "Enter" || event.key === " ")) {
                          event.preventDefault()
                          setSelectedPeer(id)
                        }
                      }}
                    >
                      <circle className="mesh-network-node__circle" r="32" />
                      <text className="mesh-network-node__name" y="-2">{nodeName(id, graph, selfId).slice(0, 12)}</text>
                      <text className="mesh-network-node__id" y="13">{isSelf ? "this laptop" : id.slice(0, 8)}</text>
                      {!online && <circle className="mesh-network-node__offline" cx="23" cy="-23" r="5" />}
                    </g>
                  )
                })}
              </svg>
            </>
          ) : (
            <div className="mesh-setup">
              <div className="mesh-network-empty mesh-network-empty--setup">
                <CircleAlert />
                <strong>Mesh node is not connected</strong>
                <span>{meshError || "Waiting for the local Mesh node."}</span>
                <code>python mesh\server.py --port 8765</code>
                <small>REST API: {snapshot?.mesh_api_url || "http://127.0.0.1:8766"}</small>
              </div>
            </div>
          )}
        </div>

        <form className="mesh-connect-form" onSubmit={connectPeer}>
          <Input
            aria-label="Peer WebSocket address"
            placeholder="ws://peer-laptop-ip:8765"
            value={peerUrl}
            onChange={(event) => setPeerUrl(event.target.value)}
          />
          <Button type="submit" variant="outline" size="icon" aria-label="Connect to Mesh peer" disabled={!peerUrl.trim() || connecting}>
            {connecting ? <LoaderCircle className="animate-spin" /> : <Plus />}
          </Button>
        </form>
        <p className="mesh-workspace__hint">
          {status ? `This node: ${status.self_addr} · Mesh REST: ${snapshot?.mesh_api_url}` : "Start the Mesh node, then connect to a peer"}
        </p>
      </div>

      <section className="mesh-chat" aria-label="Peer conversation">
        <header className="mesh-chat__header">
          <div className="mesh-chat__avatar">{messageMode === "human" ? <UserRound /> : <Bot />}</div>
          <div className="min-w-0">
            <h2 className="mesh-chat__title">{activePeer ? nodeName(activePeer, graph, selfId) : "Select a peer"}</h2>
            <p className="mesh-chat__subtitle">
              {activePeer ? `${isReachable ? "Reachable" : "Offline"} · ${activePeer}` : "Choose another node from the graph"}
            </p>
          </div>
          {activePeer && (
            <Badge variant={isReachable ? "secondary" : "outline"} className="mesh-chat__status">
              <span className={isReachable ? "" : "is-offline"} />
              {isReachable ? "Online" : "Offline"}
            </Badge>
          )}
        </header>

        <div className="mesh-chat__mode" role="group" aria-label="Conversation type">
          <Button
            type="button"
            variant={messageMode === "human" ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={messageMode === "human"}
            onClick={() => setMessageMode("human")}
          >
            <MessageSquare /> Message
          </Button>
          <Button
            type="button"
            variant={messageMode === "agent" ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={messageMode === "agent"}
            onClick={() => setMessageMode("agent")}
          >
            <Bot /> Ask agent
          </Button>
        </div>

        <div className="mesh-chat__messages" aria-live="polite">
          {!activePeer ? (
            <div className="mesh-chat__empty">
              <div className="mesh-chat__empty-icon"><Network /></div>
              <h3>Select a Mesh peer</h3>
              <p>Choose a node in the network to message its owner or call its agent.</p>
            </div>
          ) : peerMessages.length === 0 ? (
            <div className="mesh-chat__empty">
              <div className="mesh-chat__empty-icon">{messageMode === "human" ? <MessageSquare /> : <Bot />}</div>
              <h3>{messageMode === "human" ? "Start a conversation" : "Ask this laptop's agent"}</h3>
              <p>{messageMode === "human" ? "Messages are delivered through the Mesh network." : "Your prompt is sent to the selected peer's Brain agent."}</p>
            </div>
          ) : (
            peerMessages.map((message) => (
              <article
                key={message.id}
                className={`mesh-message ${message.mine ? "mesh-message--user" : "mesh-message--assistant"}${message.kind === "agent" ? " mesh-message--agent" : ""}`}
              >
                <div className="mesh-message__bubble">
                  {message.kind === "agent" && !message.mine
                    ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                    : message.content}
                </div>
                <div className="mesh-message__meta">
                  <span>{message.kind === "agent" ? (message.mine ? "Sent to agent" : "Agent response") : message.mine ? "You" : nodeName(activePeer, graph, selfId)}</span>
                  {message.createdAt > 0 && (
                    <time>{new Date(message.createdAt * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
                  )}
                </div>
              </article>
            ))
          )}
          {sending && (
            <div className="mesh-chat__typing">
              <LoaderCircle className="size-4 animate-spin" />
              {messageMode === "human" ? "Sending through Mesh…" : "Remote agent is working…"}
            </div>
          )}
        </div>

        <form onSubmit={send} className="mesh-chat__composer">
          <Textarea
            aria-label="Mesh message"
            placeholder={
              !activePeer ? "Select a peer first…" :
                !isReachable ? "This peer is not reachable" :
                  messageMode === "human" ? `Message ${nodeName(activePeer, graph, selfId)}…` : "Ask the peer agent…"
            }
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onMessageKeyDown}
            className="mesh-chat__input"
            rows={1}
            disabled={!activePeer || !isReachable || sending}
          />
          <Button type="submit" size="icon" disabled={!text.trim() || !activePeer || !isReachable || sending} aria-label={messageMode === "human" ? "Send mesh message" : "Call peer agent"}>
            {sending ? <LoaderCircle className="animate-spin" /> : <Send />}
          </Button>
        </form>
        <p className="mesh-chat__hint">Enter to send · Shift+Enter for a new line · Agent calls require a shared token</p>
      </section>
    </section>
  )
}

export default MeshPage
