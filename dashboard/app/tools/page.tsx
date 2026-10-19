"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  BookOpen,
  Calendar,
  CheckCircle2,
  ExternalLink,
  FileText,
  FolderOpen,
  HardDrive,
  KeyRound,
  Loader2,
  LogOut,
  RefreshCw,
  Terminal,
  Upload,
  Video,
  Wrench,
  X,
} from "lucide-react";
import {
  ChromeProfile,
  GoogleAppId,
  GoogleAppsStatus,
  MCPServerInfo,
  MCPToolInfo,
  MeetLaunchResult,
  callMCPTool,
  connectGoogleApp,
  disconnectGoogle,
  getChromeProfiles,
  getGoogleApps,
  getMCPServers,
  launchDesktopApp,
  launchGoogleMeet,
  runGoogleAppAction,
  saveGoogleClientSecret,
  saveMCPServer,
} from "@/lib/api";

interface ClassroomApp {
  id: GoogleAppId;
  name: string;
  description: string;
  permission: string;
  actionLabel: string;
  icon: React.ComponentType<{ className?: string }>;
  tint: string;
}

const GOOGLE_APPS: ClassroomApp[] = [
  {
    id: "classroom",
    name: "Google Classroom",
    description: "Import your classes and assignment deadlines into E.V.E. Tasks.",
    permission: "View your classes and your own coursework (read-only, never submits).",
    actionLabel: "Sync assignments",
    icon: BookOpen,
    tint: "bg-emerald-500/15 text-emerald-400",
  },
  {
    id: "meet",
    name: "Google Meet",
    description: "Join class calls with auto-recording, or create a new Meet link.",
    permission: "Create Google Meet meeting links on your behalf.",
    actionLabel: "Create Meet link",
    icon: Video,
    tint: "bg-teal-500/15 text-teal-400",
  },
  {
    id: "docs",
    name: "Google Docs",
    description: "Find your lecture notes, essays, and reviewers from Google Docs.",
    permission: "Read your Google Docs (read-only).",
    actionLabel: "Show recent docs",
    icon: FileText,
    tint: "bg-blue-500/15 text-blue-400",
  },
  {
    id: "drive",
    name: "Google Drive",
    description: "Access class handouts, slides, and modules shared to your Drive.",
    permission: "Read your Google Drive files (read-only).",
    actionLabel: "Show recent files",
    icon: HardDrive,
    tint: "bg-amber-500/15 text-amber-400",
  },
  {
    id: "calendar",
    name: "Google Calendar",
    description: "Put assignment deadlines on a dedicated \"E.V.E.\" calendar.",
    permission: "Create an E.V.E. calendar and manage only the events on it.",
    actionLabel: "Push deadlines",
    icon: Calendar,
    tint: "bg-rose-500/15 text-rose-400",
  },
];

type ActionResult = { app: GoogleAppId; data: Record<string, any> } | null;

export default function ToolsPage() {
  const [status, setStatus] = useState<GoogleAppsStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [waitingFor, setWaitingFor] = useState<GoogleAppId | null>(null);
  const [authUrl, setAuthUrl] = useState<string>("");
  const [browserOpened, setBrowserOpened] = useState<boolean>(true);
  const [connectError, setConnectError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [busyAction, setBusyAction] = useState<GoogleAppId | null>(null);
  const [actionResult, setActionResult] = useState<ActionResult>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // MCP Servers and Tool execution state
  const [mcpServers, setMcpServers] = useState<MCPServerInfo[]>([]);
  const [mcpLoading, setMcpLoading] = useState(false);
  const [callingTool, setCallingTool] = useState<string | null>(null);
  const [toolResult, setToolResult] = useState<{ tool: string; result: string; isError: boolean } | null>(null);

  const [secretText, setSecretText] = useState("");
  const [secretSaving, setSecretSaving] = useState(false);
  const [secretMsg, setSecretMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const [showMeet, setShowMeet] = useState(false);
  const [meetUrl, setMeetUrl] = useState("");
  const [autoRecord, setAutoRecord] = useState(true);
  const [meetConsent, setMeetConsent] = useState(true);
  const [profiles, setProfiles] = useState<ChromeProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState("");
  const [meetLoading, setMeetLoading] = useState(false);
  const [meetResult, setMeetResult] = useState<MeetLaunchResult | null>(null);
  const [meetError, setMeetError] = useState<string | null>(null);

  const [obsidianState, setObsidianState] = useState<string>("");

  const refresh = useCallback(async () => {
    try {
      const s = await getGoogleApps();
      setStatus(s);
      setStatusError(null);
      getMCPServers().then((res) => setMcpServers(res.servers || [])).catch(() => {});
      return s;
    } catch (err: any) {
      setStatusError(err.message || "Could not reach E.V.E. backend");
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    getChromeProfiles()
      .then((d) => setProfiles(d.profiles || []))
      .catch(() => {});
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [refresh]);

  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
    setWaitingFor(null);
  };

  const handleConnect = async (app: GoogleAppId) => {
    setConnectError(null);
    setActionResult(null);
    try {
      const res = await connectGoogleApp(app);
      setAuthUrl(res.auth_url);
      const wasOpened = res.opened === "true";
      setBrowserOpened(wasOpened);
      if (!wasOpened) {
        window.open(res.auth_url, "_blank", "noopener");
      }
      setWaitingFor(app);
      const started = Date.now();
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        const s = await refresh();
        if (s?.apps?.[app]?.connected) {
          stopPolling();
        } else if (Date.now() - started > 5 * 60 * 1000) {
          stopPolling();
          setConnectError("Timed out waiting for Google permission. Click Connect to try again.");
        }
      }, 2000);
    } catch (err: any) {
      setConnectError(err.message || "Could not start Google sign-in");
    }
  };

  const handleAction = async (app: GoogleAppId) => {
    setBusyAction(app);
    setActionError(null);
    setActionResult(null);
    try {
      const data = await runGoogleAppAction(app);
      if (data.status === "error") setActionError(data.message || "Google returned an error");
      else setActionResult({ app, data });
    } catch (err: any) {
      setActionError(err.message || "Action failed");
    } finally {
      setBusyAction(null);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Disconnect your Google account from E.V.E.? This revokes all Google app permissions.")) return;
    await disconnectGoogle().catch(() => {});
    setActionResult(null);
    await refresh();
  };

  const handleSecretFile = async (file: File | undefined) => {
    if (!file) return;
    setSecretText(await file.text());
  };

  const handleSaveSecret = async () => {
    setSecretSaving(true);
    setSecretMsg(null);
    try {
      const res = await saveGoogleClientSecret(secretText.trim());
      setSecretMsg({ ok: true, text: res.message });
      setSecretText("");
      await refresh();
    } catch (err: any) {
      setSecretMsg({ ok: false, text: err.message || "Could not save" });
    } finally {
      setSecretSaving(false);
    }
  };

  const handleLaunchMeet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!meetUrl.trim()) return;
    setMeetLoading(true);
    setMeetError(null);
    setMeetResult(null);
    try {
      setMeetResult(await launchGoogleMeet(meetUrl.trim(), selectedProfile || undefined, autoRecord, meetConsent));
    } catch (err: any) {
      setMeetError(err.message || "Failed to launch Google Meet");
    } finally {
      setMeetLoading(false);
    }
  };

  const handleToggleServer = async (server: MCPServerInfo) => {
    setMcpLoading(true);
    setActionError(null);
    try {
      const updated = { ...server, enabled: !server.enabled };
      const res = await saveMCPServer(updated);
      if (res.status === "error") {
        setActionError(`Failed to connect to MCP server '${server.name}'. Verify interpreter and stdio script.`);
      }
      const s = await getMCPServers();
      setMcpServers(s.servers || []);
    } catch (err: any) {
      setActionError(err.message || "Failed to update MCP server");
    } finally {
      setMcpLoading(false);
    }
  };

  const handleCallTool = async (toolName: string) => {
    setCallingTool(toolName);
    setToolResult(null);
    try {
      const res = await callMCPTool(toolName);
      const text = res.content.map((c: any) => c.text).join("\n");
      setToolResult({ tool: toolName, result: text, isError: res.is_error });
    } catch (err: any) {
      setToolResult({ tool: toolName, result: err.message || "Failed to call MCP tool", isError: true });
    } finally {
      setCallingTool(null);
    }
  };

  const handleObsidian = async () => {
    setObsidianState("Opening...");
    try {
      const res = await launchDesktopApp("obsidian");
      setObsidianState(res.status === "opened" ? "Opened" : res.message || "Could not open");
    } catch (err: any) {
      setObsidianState(err.message || "Could not open");
    }
    setTimeout(() => setObsidianState(""), 3500);
  };

  const configured = !!status?.configured;

  return (
    <div className="p-6 md:p-8 max-w-5xl mx-auto space-y-6 text-slate-200">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Classroom Apps</h1>
          <p className="text-sm text-slate-400 mt-1">
            Connect the school apps you use. Each one asks Google for permission when you click Connect.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {status?.authenticated && (
            <span className="text-xs px-3 py-1.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
              Signed in as {status.email || "Google account"}
            </span>
          )}
          <button
            onClick={refresh}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700"
            title="Refresh connection status"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {statusError && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{statusError}</span>
        </div>
      )}

      {/* One-time Google setup (only when no OAuth client is configured) */}
      {status && !configured && (
        <div className="p-5 rounded-2xl bg-slate-900 border border-amber-500/30 space-y-4">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-500/15 text-amber-400 flex items-center justify-center shrink-0">
              <KeyRound className="w-5 h-5" />
            </div>
            <div>
              <h2 className="font-semibold text-white">One-time setup: link E.V.E. to Google</h2>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                Google only shows its sign-in and permission screen to registered apps. Create a free OAuth
                client once, then every app below connects with a normal Google login.
              </p>
            </div>
          </div>
          <ol className="text-xs text-slate-300 space-y-1.5 list-decimal list-inside leading-relaxed">
            <li>
              Open{" "}
              <a
                href="https://console.cloud.google.com/apis/credentials"
                target="_blank"
                rel="noreferrer"
                className="text-sky-400 underline"
              >
                Google Cloud Console → Credentials
              </a>{" "}
              (create a project if asked).
            </li>
            <li>
              Enable the APIs: Google Classroom, Drive, Docs, Calendar, Meet REST (APIs &amp; Services → Library).
            </li>
            <li>OAuth consent screen → External → add your school Gmail as a Test user.</li>
            <li>
              Create credentials → OAuth client ID → Application type <strong>Desktop app</strong> → Download JSON.
            </li>
            <li>Load that JSON file below.</li>
          </ol>
          <div className="flex flex-col sm:flex-row gap-2">
            <label className="px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium cursor-pointer flex items-center gap-2 w-fit">
              <Upload className="w-3.5 h-3.5" />
              <span>Choose client_secret.json</span>
              <input
                type="file"
                accept="application/json,.json"
                className="hidden"
                onChange={(e) => handleSecretFile(e.target.files?.[0])}
              />
            </label>
            <button
              onClick={handleSaveSecret}
              disabled={secretSaving || secretText.trim().length < 20}
              className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-xs font-semibold"
            >
              {secretSaving ? "Saving..." : secretText ? "Save & enable Google apps" : "Save"}
            </button>
          </div>
          {secretText && !secretMsg && <p className="text-[11px] text-slate-500">File loaded. Click Save.</p>}
          {secretMsg && (
            <p className={`text-xs ${secretMsg.ok ? "text-emerald-400" : "text-rose-400"}`}>{secretMsg.text}</p>
          )}
        </div>
      )}

      {waitingFor && (
        <div className="p-3.5 rounded-xl bg-sky-500/10 border border-sky-500/30 text-sky-200 text-sm flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin shrink-0" />
            <span>
              {browserOpened ? (
                <>Google sign-in opened in your browser. </>
              ) : (
                <>
                  Browser did not open automatically.{" "}
                  {authUrl && (
                    <a
                      href={authUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline font-bold text-sky-300 hover:text-white"
                    >
                      Click here to sign in
                    </a>
                  )}
                  .{" "}
                </>
              )}
              Choose your account and click <strong>Allow</strong> for{" "}
              {GOOGLE_APPS.find((a) => a.id === waitingFor)?.name}.
            </span>
          </div>
          <button onClick={stopPolling} className="text-sky-300 hover:text-white shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {connectError && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{connectError}</span>
        </div>
      )}

      {/* App cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {GOOGLE_APPS.map((app) => {
          const Icon = app.icon;
          const connected = !!status?.apps?.[app.id]?.connected;
          const isWaiting = waitingFor === app.id;
          return (
            <div key={app.id} className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex flex-col gap-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${app.tint}`}>
                    <Icon className="w-5 h-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="font-semibold text-white">{app.name}</div>
                    <p className="text-xs text-slate-400 mt-0.5">{app.description}</p>
                  </div>
                </div>
                {connected ? (
                  <span className="shrink-0 text-xs text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Connected
                  </span>
                ) : (
                  <button
                    onClick={() => handleConnect(app.id)}
                    disabled={!configured || isWaiting}
                    title={configured ? "Sign in with Google and grant permission" : "Finish the one-time setup first"}
                    className="shrink-0 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-white text-slate-900 hover:bg-slate-200 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {isWaiting ? "Waiting..." : "Connect"}
                  </button>
                )}
              </div>

              <p className="text-[11px] text-slate-500">
                <span className="text-slate-400">Permission:</span> {app.permission}
              </p>

              <div className="flex flex-wrap gap-2 pt-1 border-t border-slate-800">
                {app.id === "meet" && (
                  <button
                    onClick={() => {
                      setMeetResult(null);
                      setMeetError(null);
                      setShowMeet(true);
                    }}
                    className="mt-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-teal-600 hover:bg-teal-500 text-white flex items-center gap-1.5"
                  >
                    <Video className="w-3.5 h-3.5" /> Join class &amp; record
                  </button>
                )}
                <button
                  onClick={() => handleAction(app.id)}
                  disabled={!connected || busyAction === app.id}
                  className="mt-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 border border-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {busyAction === app.id ? "Working..." : app.actionLabel}
                </button>
              </div>

              {actionResult?.app === app.id && <ActionResultView app={app.id} data={actionResult.data} />}
              {actionError && busyAction === null && actionResult === null && app.id === lastActionApp(actionError, app.id) && null}
            </div>
          );
        })}

        {/* Obsidian: local notes vault, no Google login needed */}
        <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex flex-col gap-3">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-purple-500/15 text-purple-400 flex items-center justify-center shrink-0">
                <FolderOpen className="w-5 h-5" />
              </div>
              <div>
                <div className="font-semibold text-white">Obsidian Notes</div>
                <p className="text-xs text-slate-400 mt-0.5">
                  Where E.V.E. saves your lecture notes, flashcards, and quizzes.
                </p>
              </div>
            </div>
            <span className="shrink-0 text-xs text-emerald-400 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" /> On this PC
            </span>
          </div>
          <p className="text-[11px] text-slate-500">
            <span className="text-slate-400">Permission:</span> Local folder on your computer, no account needed.
          </p>
          <div className="pt-1 border-t border-slate-800">
            <button
              onClick={handleObsidian}
              className="mt-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 border border-slate-700"
            >
              {obsidianState || "Open vault"}
            </button>
          </div>
        </div>
      </div>

      {actionError && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Workspace MCP Servers & Tools Hub */}
      <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-teal-500/15 text-teal-400 flex items-center justify-center shrink-0">
              <Terminal className="w-5 h-5" />
            </div>
            <div>
              <div className="font-semibold text-white text-base">Model Context Protocol (MCP) Hub</div>
              <p className="text-xs text-slate-400 mt-0.5">
                Standardized stdio JSON-RPC 2.0 tool servers providing classroom data to E.V.E.
              </p>
            </div>
          </div>
          <button
            onClick={refresh}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 flex items-center gap-1.5 w-fit"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${mcpLoading ? "animate-spin" : ""}`} />
            <span>Refresh MCP</span>
          </button>
        </div>

        {/* Server list */}
        <div className="space-y-3">
          {mcpServers.length === 0 ? (
            <p className="text-xs text-slate-500 py-2">No MCP servers registered yet.</p>
          ) : (
            mcpServers.map((server) => (
              <div
                key={server.name}
                className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="font-mono font-semibold text-white text-sm">{server.name}</span>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-mono ${
                        server.connected
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          : server.enabled
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                          : "bg-slate-800 text-slate-400"
                      }`}
                    >
                      {server.connected ? "Connected" : server.enabled ? "Enabled (Connecting)" : "Disabled"}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">{server.description}</p>
                  <p className="text-[11px] text-slate-500 font-mono">
                    Command: {server.command} {server.args?.join(" ")}
                  </p>
                </div>

                <div className="flex items-center space-x-3 shrink-0">
                  <button
                    onClick={() => handleToggleServer(server)}
                    disabled={mcpLoading}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                      server.enabled
                        ? "bg-rose-500/10 text-rose-300 hover:bg-rose-500/20 border border-rose-500/30"
                        : "bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 border border-emerald-500/30"
                    }`}
                  >
                    {server.enabled ? "Disable Server" : "Enable Server"}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Discovered MCP Tools */}
        {mcpServers.some((s) => s.tools && s.tools.length > 0) && (
          <div className="pt-2 space-y-3">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Discovered MCP Tools:
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {mcpServers.flatMap((s) => s.tools || []).map((t) => (
                <div
                  key={t.name}
                  className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex flex-col justify-between gap-3"
                >
                  <div>
                    <span className="font-mono text-xs font-semibold text-teal-400">{t.name}</span>
                    <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">{t.description}</p>
                  </div>
                  <button
                    onClick={() => handleCallTool(t.name)}
                    disabled={callingTool === t.name}
                    className="w-full py-1.5 px-3 rounded-lg bg-teal-600/20 hover:bg-teal-600/30 text-teal-300 text-xs font-medium border border-teal-500/30 flex items-center justify-center gap-1.5"
                  >
                    {callingTool === t.name ? (
                      <>
                        <Loader2 className="w-3 h-3 animate-spin" />
                        <span>Calling...</span>
                      </>
                    ) : (
                      <>
                        <Wrench className="w-3 h-3" />
                        <span>Test Call</span>
                      </>
                    )}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tool Call Output View */}
        {toolResult && (
          <div
            className={`p-4 rounded-xl border text-xs font-mono space-y-2 ${
              toolResult.isError
                ? "bg-rose-500/10 border-rose-500/30 text-rose-300"
                : "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
            }`}
          >
            <div className="flex items-center justify-between font-bold">
              <span>Result: {toolResult.tool}</span>
              <button onClick={() => setToolResult(null)} className="text-slate-400 hover:text-white">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <pre className="whitespace-pre-wrap text-[11px] max-h-48 overflow-y-auto bg-slate-950/70 p-3 rounded-lg border border-slate-800/80">
              {toolResult.result}
            </pre>
          </div>
        )}
      </div>

      {status?.authenticated && (
        <div className="flex justify-end">
          <button
            onClick={handleDisconnect}
            className="px-3 py-2 rounded-lg text-xs text-rose-300 hover:bg-rose-500/10 border border-rose-500/20 flex items-center gap-1.5"
          >
            <LogOut className="w-3.5 h-3.5" /> Disconnect Google account
          </button>
        </div>
      )}

      {/* Google Meet join dialog */}
      {showMeet && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-white">Join class on Google Meet</h3>
              <button onClick={() => setShowMeet(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            {meetResult && (
              <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 space-y-1">
                <div className="font-semibold">Google Meet opened in Chrome.</div>
                {meetResult.recording && (
                  <Link href="/live" className="underline text-emerald-400">
                    Recording session #{meetResult.session_id} - view live captions
                  </Link>
                )}
                {meetResult.recording_error && <div className="text-rose-300">{meetResult.recording_error}</div>}
              </div>
            )}
            {meetError && <div className="p-3 rounded-xl bg-rose-500/10 text-rose-300 text-xs">{meetError}</div>}

            <form onSubmit={handleLaunchMeet} className="space-y-3">
              <input
                type="text"
                required
                placeholder="meet.google.com/abc-defg-hij or abc-defg-hij"
                value={meetUrl}
                onChange={(e) => setMeetUrl(e.target.value)}
                className="w-full px-3 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm font-mono focus:outline-none focus:border-teal-500"
              />
              {profiles.length > 1 && (
                <select
                  value={selectedProfile}
                  onChange={(e) => setSelectedProfile(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300"
                >
                  <option value="">Chrome: default profile</option>
                  {profiles.map((p) => (
                    <option key={p.directory} value={p.email}>
                      Chrome: {p.name || p.directory}
                    </option>
                  ))}
                </select>
              )}
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input type="checkbox" checked={autoRecord} onChange={(e) => setAutoRecord(e.target.checked)} />
                Record and transcribe the lecture when I join
              </label>
              {autoRecord && (
                <label className="flex items-center gap-2 text-xs text-slate-400 pl-2">
                  <input type="checkbox" checked={meetConsent} onChange={(e) => setMeetConsent(e.target.checked)} />
                  I confirm all participants are informed and consent to recording
                </label>
              )}
              <button
                type="submit"
                disabled={meetLoading || !meetUrl.trim() || (autoRecord && !meetConsent)}
                className="w-full py-2.5 rounded-xl bg-teal-600 hover:bg-teal-500 disabled:opacity-40 text-white text-sm font-semibold"
              >
                {meetLoading ? "Opening Chrome..." : "Join Meet"}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

// Keeps JSX above simple; errors are rendered once below the grid.
function lastActionApp(_err: string, _app: GoogleAppId): null {
  return null;
}

function ActionResultView({ app, data }: { app: GoogleAppId; data: Record<string, any> }) {
  if (app === "classroom") {
    return (
      <div className="text-xs text-emerald-300 bg-emerald-500/5 rounded-lg p-2.5">
        Scanned {data.courses_scanned} classes · {data.new_tasks} new assignments · {data.updated_tasks} updated.{" "}
        <Link href="/assignments" className="underline">
          View assignments
        </Link>
      </div>
    );
  }
  if (app === "calendar") {
    return (
      <div className="text-xs text-emerald-300 bg-emerald-500/5 rounded-lg p-2.5">
        Added {data.events_created} deadline(s) to your E.V.E. calendar.
      </div>
    );
  }
  if (app === "meet") {
    return (
      <div className="text-xs text-emerald-300 bg-emerald-500/5 rounded-lg p-2.5 flex items-center justify-between gap-2">
        <span className="font-mono truncate">{data.meeting_uri}</span>
        {data.meeting_uri && (
          <a href={data.meeting_uri} target="_blank" rel="noreferrer" className="flex items-center gap-1 underline shrink-0">
            Open <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
    );
  }
  const files: Array<{ id: string; name: string; webViewLink?: string; modifiedTime?: string }> = data.files || [];
  if (files.length === 0) {
    return <div className="text-xs text-slate-400 bg-slate-950 rounded-lg p-2.5">No files found.</div>;
  }
  return (
    <ul className="text-xs bg-slate-950 rounded-lg p-2 space-y-1 max-h-48 overflow-y-auto">
      {files.map((f) => (
        <li key={f.id} className="flex items-center justify-between gap-2">
          <span className="truncate text-slate-200">{f.name}</span>
          {f.webViewLink && (
            <a href={f.webViewLink} target="_blank" rel="noreferrer" className="text-sky-400 shrink-0">
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </li>
      ))}
    </ul>
  );
}
