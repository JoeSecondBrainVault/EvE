/**
 * Strongly-typed API client for E.V.E. FastAPI backend (http://127.0.0.1:8765).
 */

export const API_BASE = "http://127.0.0.1:8765";

export interface Session {
  id: number;
  session_id?: number;
  title: string;
  course: string | null;
  status: "recording" | "idle" | "processing" | "processed" | "error" | "stopped" | "failed";
  started_at: string;
  ended_at: string | null;
}

export interface Segment {
  id: number;
  source: "them" | "me";
  t0: float;
  t1: float;
  text: string;
  language?: string | null;
}

export type float = number;

export interface Note {
  id: number;
  session_id: number;
  vault_path: string;
  title: string;
  summary: string;
  key_takeaways: string[];
  glossary: { term: string; definition: string }[];
  created_at: string;
}

export interface Task {
  id: number;
  session_id: number | null;
  title: string;
  due_date: string | null;
  status: "inbox" | "todo" | "doing" | "done";
  priority: "low" | "medium" | "high";
  course_name: string | null;
  evidence: string | null;
  confidence: number;
  created_at: string;
  external_id?: string | null;
  calendar_event_id?: string | null;
}

export interface Flashcard {
  id: number;
  session_id: number;
  front: string;
  back: string;
  topic?: string | null;
}

export interface QuizItem {
  id: number;
  session_id: number;
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
}

export interface Citation {
  chunk_id: number;
  session_id: number;
  course_name: string | null;
  session_title: string | null;
  t0: number;
  t1: number;
  timestamp_label: string;
  snippet: string;
}

export interface RAGAnswer {
  answer: string;
  citations: Citation[];
}

export interface ChunkSearchResult {
  chunk_id: number;
  session_id: number;
  course_name: string | null;
  session_title: string | null;
  t0: number;
  t1: number;
  text: string;
  score: number;
}

export interface Stats {
  total_sessions: number;
  total_segments: number;
  total_tasks: number;
  pending_tasks: number;
  total_flashcards: number;
  total_quizzes: number;
  total_hours_recorded: number;
}

export interface SystemStatus {
  version: string;
  model: string;
  device: string | null;
  active_session_id: number | null;
  live_clients: number;
  has_cloud_llm: boolean;
  vault_path?: string;
}

export function getStoredToken(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = localStorage.getItem("eve_api_token") || "";
    const urlParams = new URLSearchParams(window.location.search);
    const urlToken = urlParams.get("token");
    if (urlToken && urlToken.trim()) {
      const cleanToken = urlToken.trim();
      // Protect existing valid tokens from malicious link overwrites (S4)
      if (!existing) {
        localStorage.setItem("eve_api_token", cleanToken);
      }
      // Immediately strip the ?token= query parameter from URL bar to prevent leakage in history/logs (S3)
      const url = new URL(window.location.href);
      url.searchParams.delete("token");
      window.history.replaceState({}, document.title, url.pathname + (url.search ? url.search : "") + url.hash);
      return existing || cleanToken;
    }
  } catch {
    // ignore
  }
  return localStorage.getItem("eve_api_token") || "";
}

export function setStoredToken(token: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem("eve_api_token", token);
  }
}

export function clearStoredToken(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem("eve_api_token");
  }
}

export async function ensureToken(): Promise<string> {
  return getStoredToken();
}

export async function fetchAPI<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  let token = getStoredToken();
  if (!token && typeof window !== "undefined") {
    token = await ensureToken();
  }
  const headers = new Headers(options.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let detail = `Error ${res.status}: ${res.statusText}`;
    try {
      const err = await res.json();
      if (err.detail) detail = err.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

// --- Endpoints ---

export async function getStatus(): Promise<SystemStatus> {
  return fetchAPI<SystemStatus>("/api/status");
}

export async function getStats(): Promise<Stats> {
  return fetchAPI<Stats>("/api/stats");
}

export async function getDevices(): Promise<Array<{ id: number; name: string; type: string; is_default: boolean }>> {
  return fetchAPI("/api/devices");
}

export async function startSession(title: string, course?: string): Promise<Session> {
  return fetchAPI<Session>("/api/sessions/start", {
    method: "POST",
    body: JSON.stringify({
      title,
      course: course || null,
      consent_confirmed: true,
    }),
  });
}

export async function stopSession(): Promise<Session & { session_id?: number }> {
  return fetchAPI<Session & { session_id?: number }>("/api/sessions/stop", {
    method: "POST",
  });
}

export async function getSessions(): Promise<Session[]> {
  return fetchAPI<Session[]>("/api/sessions");
}

export async function getSession(id: number): Promise<Session & { segments: Segment[] }> {
  return fetchAPI<Session & { segments: Segment[] }>(`/api/sessions/${id}`);
}

export async function processSession(id: number): Promise<{
  session_id: number;
  vault_path: string;
  tasks_count: number;
  flashcards_count: number;
  quiz_count: number;
}> {
  return fetchAPI(`/api/sessions/${id}/process`, { method: "POST" });
}

export async function getSessionNote(id: number): Promise<Note> {
  return fetchAPI<Note>(`/api/sessions/${id}/note`);
}

export async function getSessionFlashcards(id: number): Promise<Flashcard[]> {
  return fetchAPI<Flashcard[]>(`/api/sessions/${id}/flashcards`);
}

export async function getSessionQuiz(id: number): Promise<QuizItem[]> {
  return fetchAPI<QuizItem[]>(`/api/sessions/${id}/quiz`);
}

export async function getTasks(status?: string, course?: string): Promise<Task[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (course) params.set("course", course);
  const q = params.toString() ? `?${params.toString()}` : "";
  return fetchAPI<Task[]>(`/api/tasks${q}`);
}

export async function updateTaskStatus(id: number, status: "inbox" | "todo" | "doing" | "done"): Promise<Task> {
  return fetchAPI<Task>(`/api/tasks/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export async function chatRAG(query: string, course?: string, top_k: number = 4): Promise<RAGAnswer> {
  return fetchAPI<RAGAnswer>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ query, course: course || null, top_k }),
  });
}

export async function searchRAG(query: string, course?: string, top_k: number = 5): Promise<ChunkSearchResult[]> {
  const params = new URLSearchParams({ q: query });
  if (course) params.set("course", course);
  params.set("top_k", top_k.toString());
  return fetchAPI<ChunkSearchResult[]>(`/api/chat/search?${params.toString()}`);
}

export function getAudioUrl(sessionId: number, source: "them" | "me" = "them"): string {
  const token = getStoredToken();
  return `${API_BASE}/api/sessions/${sessionId}/audio/${source}?token=${token}`;
}

export function getLiveWebSocketUrl(): string {
  return `ws://127.0.0.1:8765/ws/live`;
}

// --- Phase 4: Google Classroom & Calendar Integration ---

export interface GoogleStatus {
  configured: boolean;
  authenticated: boolean;
  calendar_name: string;
}

export interface GoogleSyncResult {
  status: string;
  results: {
    classroom?: {
      synced_courses: number;
      new_tasks: number;
      total_coursework: number;
    };
    calendar?: {
      created_events: number;
      checked_tasks: number;
    };
  };
}

export async function getGoogleStatus(): Promise<GoogleStatus> {
  return fetchAPI<GoogleStatus>("/api/integrations/google/status");
}

export async function getGoogleAuthUrl(redirectUri?: string): Promise<{ auth_url: string }> {
  const params = new URLSearchParams();
  if (redirectUri) params.set("redirect_uri", redirectUri);
  const q = params.toString() ? `?${params.toString()}` : "";
  return fetchAPI<{ auth_url: string }>(`/api/integrations/google/auth-url${q}`);
}

export async function exchangeGoogleCode(
  code: string,
  redirectUri: string = "http://127.0.0.1:8765/api/integrations/google/callback"
): Promise<{ status: string; message: string }> {
  return fetchAPI<{ status: string; message: string }>("/api/integrations/google/exchange", {
    method: "POST",
    body: JSON.stringify({ code, redirect_uri: redirectUri }),
  });
}

export async function syncGoogle(
  target: "all" | "classroom" | "calendar" = "all"
): Promise<GoogleSyncResult> {
  const params = new URLSearchParams({ target });
  return fetchAPI<GoogleSyncResult>(`/api/integrations/google/sync?${params.toString()}`, {
    method: "POST",
  });
}

export async function disconnectGoogle(): Promise<{ status: string; message: string }> {
  return fetchAPI<{ status: string; message: string }>("/api/integrations/google/disconnect", {
    method: "POST",
  });
}

export type GoogleAppId = "classroom" | "calendar" | "docs" | "drive" | "meet" | "gmail";

export interface GoogleAppsStatus {
  configured: boolean;
  authenticated: boolean;
  email: string | null;
  apps: Record<GoogleAppId, { connected: boolean; scopes: string[] }>;
}

export async function getGoogleApps(): Promise<GoogleAppsStatus> {
  return fetchAPI<GoogleAppsStatus>("/api/integrations/google/apps");
}

export async function connectGoogleApp(app: GoogleAppId): Promise<{ auth_url: string; opened: string }> {
  return fetchAPI<{ auth_url: string; opened: string }>("/api/integrations/google/connect", {
    method: "POST",
    body: JSON.stringify({ app }),
  });
}

export async function runGoogleAppAction(app: GoogleAppId): Promise<Record<string, any>> {
  return fetchAPI<Record<string, any>>(`/api/integrations/google/apps/${app}/action`, { method: "POST" });
}

export async function saveGoogleClientSecret(content: string): Promise<{ status: string; message: string }> {
  return fetchAPI<{ status: string; message: string }>("/api/integrations/google/client-secret", {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

// --- Phase 5: Voice Assistant & Live Copilot ---

export interface VoiceStatus {
  wakeword_enabled: boolean;
  wakeword_loaded: boolean;
  tts_enabled: boolean;
  tts_loaded: boolean;
  tts_voice: string;
  tts_speed: number;
  copilot_enabled: boolean;
}

export interface VoiceInteractResult {
  tool: string;
  arguments: Record<string, any>;
  response_text: string;
  tool_output: Record<string, any>;
  audio_base64: string | null;
}

export interface CopilotSuggestion {
  topic: string;
  talking_points: string[];
  context_summary: string;
}

export async function getVoiceStatus(): Promise<VoiceStatus> {
  return fetchAPI<VoiceStatus>("/api/voice/status");
}

export async function interactVoice(
  input: string,
  synthesize_audio: boolean = true
): Promise<VoiceInteractResult> {
  return fetchAPI<VoiceInteractResult>("/api/voice/interact", {
    method: "POST",
    body: JSON.stringify({ input, synthesize_audio }),
  });
}

export async function triggerWakeWord(): Promise<{ status: string; message: string }> {
  return fetchAPI<{ status: string; message: string }>("/api/voice/wakeword/trigger", {
    method: "POST",
  });
}

export async function getCopilotRecent(): Promise<{
  suggestion: CopilotSuggestion | null;
  window_text: string;
}> {
  return fetchAPI<{ suggestion: CopilotSuggestion | null; window_text: string }>(
    "/api/copilot/recent"
  );
}

export async function suggestCopilot(hint?: string): Promise<{
  status: string;
  suggestion: CopilotSuggestion | null;
}> {
  return fetchAPI<{ status: string; suggestion: CopilotSuggestion | null }>(
    "/api/copilot/suggest",
    {
      method: "POST",
      body: JSON.stringify({ hint: hint || null }),
    }
  );
}

// --- Phase 6: Assignment Helper & Hardening ---

export interface RubricItem {
  criterion: string;
  expectation: string;
}

export interface OutlineSection {
  section_title: string;
  recommended_content: string[];
  lecture_connection?: string | null;
}

export interface LectureCitationRef {
  topic: string;
  citation_label: string;
  relevance: string;
}

export interface AssignmentAnalysis {
  title: string;
  course_name?: string | null;
  summary: string;
  deliverables: string[];
  rubric_criteria: RubricItem[];
  outline_sections: OutlineSection[];
  suggested_citations: LectureCitationRef[];
  draft_overview: string;
  academic_integrity_notice: string;
}

export async function analyzeAssignment(
  prompt: string,
  course?: string
): Promise<AssignmentAnalysis> {
  return fetchAPI<AssignmentAnalysis>("/api/assignments/analyze", {
    method: "POST",
    body: JSON.stringify({ prompt, course: course || null }),
  });
}

export async function uploadAssignment(
  file: File,
  course?: string
): Promise<AssignmentAnalysis> {
  const formData = new FormData();
  formData.append("file", file);
  if (course) {
    formData.append("course", course);
  }
  return fetchAPI<AssignmentAnalysis>("/api/assignments/upload", {
    method: "POST",
    body: formData,
  });
}

export async function purgeRetention(): Promise<{
  status: string;
  purged_count: number;
  freed_bytes: number;
  retention_days: number;
}> {
  return fetchAPI<{
    status: string;
    purged_count: number;
    freed_bytes: number;
    retention_days: number;
  }>("/api/retention/purge", {
    method: "POST",
  });
}

// --- Desktop Computer Control, Meet Automation & MCP Tools ---

export interface ChromeProfile {
  directory: string;
  name: string;
  email: string;
  avatar_icon?: string;
}

export interface MeetLaunchResult {
  status: string;
  meet_url: string;
  email: string;
  profile_directory: string;
  recording?: boolean;
  session_id?: number;
  recording_error?: string;
}

export interface MCPServerInfo {
  name: string;
  command: string;
  args: string[];
  enabled: boolean;
  description: string;
  connected?: boolean;
  tools?: MCPToolInfo[];
}

export interface MCPToolInfo {
  server_name: string;
  name: string;
  description: string;
  input_schema: Record<string, any>;
}

export interface MCPCallResult {
  tool_name: string;
  content: Array<{ type: string; text?: string; [key: string]: any }>;
  is_error: boolean;
}

export async function getChromeProfiles(): Promise<{ profiles: ChromeProfile[] }> {
  return fetchAPI<{ profiles: ChromeProfile[] }>("/api/integrations/chrome/profiles");
}

export async function launchGoogleMeet(
  meet_url_or_code: string,
  email_or_profile?: string,
  auto_record: boolean = true,
  consent_confirmed: boolean = false
): Promise<MeetLaunchResult> {
  return fetchAPI<MeetLaunchResult>("/api/integrations/meet/launch", {
    method: "POST",
    body: JSON.stringify({
      meet_url_or_code,
      email_or_profile: email_or_profile || null,
      auto_record,
      consent_confirmed,
    }),
  });
}

export async function launchDesktopApp(appName: string): Promise<{ status: string; app?: string; message?: string }> {
  return fetchAPI<{ status: string; app?: string; message?: string }>("/api/integrations/apps/launch", {
    method: "POST",
    body: JSON.stringify({ app_name: appName }),
  });
}

export async function getMCPServers(): Promise<{ servers: MCPServerInfo[] }> {
  return fetchAPI<{ servers: MCPServerInfo[] }>("/api/mcp/servers");
}

export async function saveMCPServer(server: MCPServerInfo): Promise<{ status: string }> {
  return fetchAPI<{ status: string }>("/api/mcp/servers", {
    method: "POST",
    body: JSON.stringify(server),
  });
}

export async function getMCPTools(): Promise<{ tools: MCPToolInfo[] }> {
  return fetchAPI<{ tools: MCPToolInfo[] }>("/api/mcp/tools");
}

export async function callMCPTool(
  tool_name: string,
  args: Record<string, any> = {}
): Promise<MCPCallResult> {
  return fetchAPI<MCPCallResult>("/api/mcp/call", {
    method: "POST",
    body: JSON.stringify({ tool_name, arguments: args }),
  });
}

// --- System API Keys Management ---

export interface APIKeyStatus {
  configured: boolean;
  masked?: string | null;
  model: string;
}

export interface SystemAPIKeys {
  gemini: APIKeyStatus;
  groq: APIKeyStatus;
  active_provider: "groq" | "gemini" | "ollama";
  has_cloud: boolean;
}

export async function getAPIKeys(): Promise<SystemAPIKeys> {
  return fetchAPI<SystemAPIKeys>("/api/settings/keys");
}

export async function updateAPIKeys(keys: {
  groq_api_key?: string;
  gemini_api_key?: string;
}): Promise<{
  status: string;
  message: string;
  groq_configured: boolean;
  gemini_configured: boolean;
}> {
  return fetchAPI("/api/settings/keys", {
    method: "POST",
    body: JSON.stringify(keys),
  });
}




