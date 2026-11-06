import { useMemo, useRef, useState, type FormEvent } from "react"
import { Bot, ImagePlus, Pencil, Plus, Search, Trash2, Users, X } from "lucide-react"
import { toast } from "sonner"
import { apiRequest, jsonBody, type AgentProfile, type AgentTool } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
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
import { Textarea } from "@/components/ui/textarea"

type AgentDraft = {
  name: string
  description: string
  system_prompt: string
  tool_names: string[]
  profile_photo: string | null
}

const emptyDraft: AgentDraft = {
  name: "",
  description: "",
  system_prompt: "",
  tool_names: [],
  profile_photo: null,
}

export default function AgentsPage({
  profiles,
  tools,
  onProfilesChange,
}: {
  profiles: AgentProfile[]
  tools: AgentTool[]
  onProfilesChange: (profiles: AgentProfile[]) => void
}) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [detailsProfile, setDetailsProfile] = useState<AgentProfile | null>(null)
  const [editing, setEditing] = useState<AgentProfile | null>(null)
  const [draft, setDraft] = useState<AgentDraft>(emptyDraft)
  const [saving, setSaving] = useState(false)
  const [updatingToolName, setUpdatingToolName] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [detailsToolSearch, setDetailsToolSearch] = useState("")
  const photoInput = useRef<HTMLInputElement>(null)

  const filteredProfiles = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return profiles
    return profiles.filter((profile) =>
      `${profile.name} ${profile.description} ${profile.tool_names.join(" ")}`
        .toLowerCase()
        .includes(query),
    )
  }, [profiles, search])

  function openCreate() {
    setEditing(null)
    setDraft(emptyDraft)
    setDialogOpen(true)
  }

  function openEdit(profile: AgentProfile) {
    setEditing(profile)
    setDraft({
      name: profile.name,
      description: profile.description,
      system_prompt: profile.system_prompt,
      tool_names: profile.tool_names.includes("*") ? tools.map((tool) => tool.name) : profile.tool_names,
      profile_photo: profile.profile_photo,
    })
    setDialogOpen(true)
  }

  async function choosePhoto(file?: File) {
    if (!file) return
    if (!["image/png", "image/jpeg", "image/webp", "image/gif"].includes(file.type)) {
      toast.error("Choose a PNG, JPEG, WebP, or GIF image.")
      return
    }
    if (file.size > 2 * 1024 * 1024) {
      toast.error("Profile photos must be 2 MB or smaller.")
      return
    }

    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setDraft((current) => ({ ...current, profile_photo: reader.result as string }))
      } else {
        toast.error("Could not read the selected image.")
      }
    }
    reader.onerror = () => toast.error("Could not read the selected image.")
    reader.readAsDataURL(file)
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    const payload = {
      ...draft,
      name: draft.name.trim(),
      description: draft.description.trim(),
      tool_names: draft.tool_names,
    }
    try {
      const saved = await apiRequest<AgentProfile>(
        editing ? `/api/agents/${encodeURIComponent(editing.id)}` : "/api/agents",
        {
          method: editing ? "PUT" : "POST",
          body: jsonBody(payload),
        },
      )
      const next = editing
        ? profiles.map((profile) => profile.id === saved.id ? saved : profile)
        : [...profiles, saved].sort((left, right) => left.name.localeCompare(right.name))
      onProfilesChange(next)
      setDialogOpen(false)
      toast.success(editing ? "Agent profile updated." : "Agent profile created.")
    } catch (error) {
      toast.error(`Could not save agent: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setSaving(false)
    }
  }

  async function deleteProfile(profile: AgentProfile) {
    if (!window.confirm(`Delete the "${profile.name}" agent profile?`)) return
    try {
      await apiRequest<{ success: boolean }>(`/api/agents/${encodeURIComponent(profile.id)}`, {
        method: "DELETE",
      })
      onProfilesChange(profiles.filter((item) => item.id !== profile.id))
      toast.success("Agent profile deleted.")
    } catch (error) {
      toast.error(`Could not delete agent: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  function toggleTool(toolName: string) {
    setDraft((current) => ({
      ...current,
      tool_names: current.tool_names.includes(toolName)
        ? current.tool_names.filter((name) => name !== toolName)
        : [...current.tool_names, toolName],
    }))
  }

  async function toggleProfileTool(profile: AgentProfile, toolName: string) {
    if (updatingToolName) return
    const assigned = profile.tool_names.includes("*") || profile.tool_names.includes(toolName)
    const nextToolNames = assigned
      ? (profile.tool_names.includes("*") ? tools.map((tool) => tool.name) : profile.tool_names)
        .filter((name) => name !== toolName)
      : [...profile.tool_names, toolName]

    setUpdatingToolName(toolName)
    try {
      const saved = await apiRequest<AgentProfile>(`/api/agents/${encodeURIComponent(profile.id)}`, {
        method: "PUT",
        body: jsonBody({
          name: profile.name,
          description: profile.description,
          system_prompt: profile.system_prompt,
          tool_names: nextToolNames,
          profile_photo: profile.profile_photo,
        }),
      })
      onProfilesChange(profiles.map((item) => item.id === saved.id ? saved : item))
      setDetailsProfile(saved)
      toast.success(`${toolName} ${assigned ? "removed from" : "added to"} ${profile.name}`)
    } catch (error) {
      toast.error(`Could not update ${profile.name}: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setUpdatingToolName(null)
    }
  }

  const detailsTools = detailsProfile
    ? tools
      .filter((tool) => `${tool.name} ${tool.description}`.toLowerCase().includes(detailsToolSearch.trim().toLowerCase()))
      .sort((left, right) => {
        const leftAssigned = detailsProfile.tool_names.includes("*") || detailsProfile.tool_names.includes(left.name)
        const rightAssigned = detailsProfile.tool_names.includes("*") || detailsProfile.tool_names.includes(right.name)
        if (leftAssigned !== rightAssigned) return leftAssigned ? -1 : 1
        return left.name.localeCompare(right.name)
      })
    : []

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Agent profiles</h2>
          <p className="text-sm text-muted-foreground">
            Manage the profile, system prompt, and tool access used by autonomous chat.
          </p>
        </div>
        <Button onClick={openCreate}><Plus /> Add agent</Button>
      </div>

      <Input
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search agents"
        aria-label="Search agents"
        className="max-w-sm"
      />

      {filteredProfiles.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <Users className="size-8 text-muted-foreground" />
            <p className="font-medium">No agents found</p>
            <p className="text-sm text-muted-foreground">Add an agent profile or adjust your search.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,28rem),28rem))] gap-4">
          {filteredProfiles.map((profile) => {
            const assignedTools = profile.tool_names.includes("*")
              ? tools.map((tool) => tool.name)
              : profile.tool_names
            return (
              <Card key={profile.id} className="min-w-0 max-w-md overflow-hidden">
                <div className="relative mx-4 aspect-[16/11] overflow-hidden rounded-lg bg-muted">
                  {profile.profile_photo ? (
                    <img src={profile.profile_photo} alt={`${profile.name} profile`} className="size-full object-cover" />
                  ) : (
                    <div className="flex size-full items-center justify-center">
                      <Bot className="size-12 text-muted-foreground" />
                    </div>
                  )}
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="absolute right-3 bottom-3 shadow-sm"
                    aria-label={`${profile.profile_photo ? "Change" : "Add"} ${profile.name} photo`}
                    onClick={() => openEdit(profile)}
                  >
                    <ImagePlus /> {profile.profile_photo ? "Change photo" : "Add photo"}
                  </Button>
                </div>
                <CardContent className="grid gap-4 p-4">
                  <div className="min-w-0">
                    <CardTitle className="truncate text-base">{profile.name}</CardTitle>
                    <CardDescription className="mt-1 line-clamp-2 min-h-10">
                      {profile.description || "No description provided."}
                    </CardDescription>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-t pt-3">
                    <div className="text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{assignedTools.length}</span> tools assigned
                    </div>
                    <Button variant="outline" size="sm" onClick={() => setDetailsProfile(profile)}>
                      Details
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      <Dialog open={detailsProfile !== null} onOpenChange={(open) => !open && setDetailsProfile(null)}>
        {detailsProfile && (
          <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
            <DialogHeader>
              <DialogTitle>{detailsProfile.name}</DialogTitle>
              <DialogDescription>{detailsProfile.description || "No description provided."}</DialogDescription>
            </DialogHeader>
            <div className="grid gap-5">
              <div className="grid gap-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium">Assigned tools</h3>
                  <Badge variant="secondary">{detailsProfile.tool_names.includes("*") ? tools.length : detailsProfile.tool_names.length}</Badge>
                </div>
                <div className="relative">
                  <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
                  <Input
                    className="pl-9"
                    placeholder="Search tools"
                    aria-label="Search tools"
                    value={detailsToolSearch}
                    onChange={(event) => setDetailsToolSearch(event.target.value)}
                  />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {detailsTools.length > 0
                    ? detailsTools.map((tool) => {
                      const assigned = detailsProfile.tool_names.includes("*")
                        || detailsProfile.tool_names.includes(tool.name)
                      return (
                        <Button
                          key={tool.name}
                          type="button"
                          size="sm"
                          variant={assigned ? "secondary" : "outline"}
                          className={`rounded-full ${
                            assigned
                              ? "border-white bg-white text-black hover:bg-white/90 hover:text-black"
                              : "border-white bg-black text-white hover:bg-white/10 hover:text-white"
                          }`}
                          aria-pressed={assigned}
                          aria-label={`${assigned ? "Remove" : "Add"} ${tool.name} ${assigned ? "from" : "to"} ${detailsProfile.name}`}
                          disabled={updatingToolName !== null}
                          onClick={() => void toggleProfileTool(detailsProfile, tool.name)}
                        >
                          <span>{tool.name}</span>
                          <span aria-hidden="true" className={`-mr-1 ml-1.5 flex size-5 items-center justify-center border-l ${assigned ? "border-black/20" : "border-white/30"}`}>
                            {assigned ? <X className="size-3.5" /> : <Plus className="size-3.5" />}
                          </span>
                        </Button>
                      )
                    })
                    : <span className="text-sm text-muted-foreground">{tools.length ? "No tools match your search." : "No tools available."}</span>}
                </div>
              </div>
              <div className="grid gap-2">
                <h3 className="text-sm font-medium">System prompt</h3>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-xs text-muted-foreground">
                  {detailsProfile.system_prompt}
                </pre>
              </div>
            </div>
            <DialogFooter>
              {!detailsProfile.is_built_in && (
                <Button variant="destructive" onClick={() => {
                  const profile = detailsProfile
                  setDetailsProfile(null)
                  void deleteProfile(profile)
                }}>
                  <Trash2 /> Delete
                </Button>
              )}
              <Button variant="outline" onClick={() => {
                const profile = detailsProfile
                setDetailsProfile(null)
                openEdit(profile)
              }}>
                <Pencil /> Edit
              </Button>
            </DialogFooter>
          </DialogContent>
        )}
      </Dialog>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editing ? "Edit agent profile" : "Create agent profile"}</DialogTitle>
            <DialogDescription>
              This profile is available in autonomous chat and controls its system prompt and tools.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={(event) => void saveProfile(event)} className="grid gap-5">
            <div className="flex items-center gap-4">
              <div className="flex size-16 items-center justify-center overflow-hidden rounded-full border bg-muted">
                {draft.profile_photo
                  ? <img src={draft.profile_photo} alt="Selected agent profile" className="size-full object-cover" />
                  : <Bot className="size-7 text-muted-foreground" />}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" onClick={() => photoInput.current?.click()}>
                  <ImagePlus /> Choose photo
                </Button>
                {draft.profile_photo && (
                  <Button type="button" variant="ghost" onClick={() => setDraft((current) => ({ ...current, profile_photo: null }))}>
                    <X /> Remove photo
                  </Button>
                )}
              </div>
              <input
                ref={photoInput}
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                className="hidden"
                onChange={(event) => {
                  void choosePhoto(event.target.files?.[0])
                  event.target.value = ""
                }}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="agent-name">Name</Label>
              <Input id="agent-name" required maxLength={80} value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="agent-description">Description</Label>
              <Textarea id="agent-description" maxLength={2000} value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="agent-system-prompt">System prompt</Label>
              <Textarea id="agent-system-prompt" required className="min-h-36 font-mono text-xs" value={draft.system_prompt} onChange={(event) => setDraft((current) => ({ ...current, system_prompt: event.target.value }))} />
            </div>
            <div className="grid gap-2">
              <div>
                <Label>Available tools</Label>
                <p className="text-xs text-muted-foreground">Only selected tools are exposed to this agent in chat.</p>
              </div>
              <ScrollArea className="h-52 rounded-md border">
                <div className="grid gap-1 p-2 sm:grid-cols-2">
                  {tools.map((tool) => (
                    <label key={tool.name} className="flex min-w-0 items-start gap-2 rounded-md p-2 text-sm hover:bg-muted/60">
                      <input
                        type="checkbox"
                        checked={draft.tool_names.includes(tool.name)}
                        onChange={() => toggleTool(tool.name)}
                        className="mt-1 accent-primary"
                      />
                      <span className="min-w-0">
                        <span className="block truncate font-medium">{tool.name}</span>
                        <span className="line-clamp-2 text-xs text-muted-foreground">{tool.description}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </ScrollArea>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={saving || !draft.name.trim() || !draft.system_prompt.trim()}>
                {saving ? "Saving…" : editing ? "Save changes" : "Create agent"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  )
}
