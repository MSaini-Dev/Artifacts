export type SystemStats = {
  providers_count: number
  models_count: number
  active_models: number
  keys_count: number
  tools_count: number
  conversations_count: number
}

export type Conversation = {
  ID: number
  Title: string | null
  Created_At: string
  Updated_At: string
  message_count: number
}

export type ChatMessage = {
  id: string
  role: "user" | "assistant"
  content: string
  created_at?: string
  status?: string
  interactive_id?: number
  tool_activity?: LogToolExecution[]
  chosen?: {
    provider?: string
    model?: string
    key_name?: string
  }
  duration_ms?: number
  mode?: string
}

export type Provider = {
  id: number
  name: string
  base_url: string
  status: string
  rate_limit: string | null
  last_modify: string
}

export type Model = {
  id: number
  provider_id: number
  provider_name: string
  name: string
  status: string
  model_size: number | null
  RPM: number | null
  RPD: number | null
  TPM: number | null
  TPD: number | null
  disabled_reason: string | null
}

export type ApiKey = {
  id: number
  provider_id: number
  provider_name: string
  unique_name: string
  env_key: string
  status: string
  env_configured: boolean
  disabled_reason: string | null
}

export type ToolInfo = {
  parameter?: Record<string, { required?: boolean; type?: string; default?: unknown }>
  description?: string
  enabled?: boolean
  module?: string
  status?: string
  error?: string | null
  assigned_agents?: { id: string; name: string }[]
}

export type ToolSource = {
  tool_name: string
  file_name: string
  source: string
  editable: boolean
  related_tools: string[]
}

export type AgentProfile = {
  id: string
  name: string
  description: string
  system_prompt: string
  tool_names: string[]
  profile_photo: string | null
  is_built_in: boolean
  created_at?: string
  updated_at?: string
}

export type AgentTool = {
  name: string
  description: string
  enabled: boolean
  status: string
}

export type LogConversation = {
  ID: number
  Title: string | null
  Created_At: string
}

export type LogIteration = {
  ID: number
  api_calls: LogApiCall[]
}

export type LogApiCall = {
  API_Call_Id: number
  Conversation_Id: number
  Interaction_Id: number
  Iteration_Id: number
  URL: string | null
  Model: string | null
  API_Name: string | null
  Payload: string | null
  Response: string | null
  Request_Status: "Failed" | "Success"
  Final_Response: number | null
  Timestamp: string
  Duration: number | null
  Is_Complete?: number
  Task_Started_At?: string | null
  Task_Duration_Seconds?: number | null
  Task_Is_Complete?: number
  Recovery_Mode: string | null
  Recovery_Request: string | null
  Recovery_Action: string | null
  Wait_Duration_Seconds: number | null
  Interaction_Prompt: string | null
  Legacy_Record: number
}

export type LogTask = {
  ID: number
  Name: string
  Model: string | null
  Timestamp: string
  Duration_Seconds: number | null
  Status: "Running" | "Success" | "Failed"
  Request: string | null
  Final_Response: string | null
  api_calls: LogApiCall[]
}

export type LogToolExecution = {
  ID: number
  Conversation_Id: number
  Interaction_Id: number
  Task_Id: number | null
  Tool_Call_Id: string | null
  Name: string
  Parameters: string | null
  Response: string | null
  Error: string | null
  Status: "Running" | "Success" | "Failed"
  Timestamp: string
  Duration: number | null
}

export type LogExecutionRecord =
  | { type: "task"; Timestamp: string; ID: number; task: LogTask }
  | { type: "tool"; Timestamp: string; ID: number; tool: LogToolExecution }

export type LogInteractive = {
  ID: number
  Created_At: string
  Response_Status: string
  Duration_Seconds: number | null
  Payload: string | null
  Interaction_Prompt: string | null
  Actual_Response: string | null
  iterations: LogIteration[]
  tasks?: LogTask[]
  execution_records?: LogExecutionRecord[]
}

export type LogDetails = {
  conversation: LogConversation
  interactives: LogInteractive[]
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  })

  if (!response.ok) {
    const body = await response.text()
    let message = body || `${response.status} ${response.statusText}`
    try {
      const parsed = JSON.parse(body) as { detail?: string; error?: string }
      message = parsed.detail || parsed.error || message
    } catch {
      // Keep the response body as the error when it isn't JSON.
    }
    throw new Error(message)
  }

  return response.json() as Promise<T>
}

export function jsonBody(value: unknown): string {
  return JSON.stringify(value)
}
