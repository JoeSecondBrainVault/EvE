"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Terminal,
  Video,
  Monitor,
  Play,
  CheckCircle2,
  AlertCircle,
  Plus,
  RefreshCw,
  ExternalLink,
  Cpu,
  Layers,
  ChevronRight,
  Sparkles,
  Command,
  FileCode,
  FolderOpen
} from "lucide-react";
import {
  getChromeProfiles,
  launchGoogleMeet,
  launchDesktopApp,
  getMCPServers,
  saveMCPServer,
  getMCPTools,
  callMCPTool,
  ChromeProfile,
  MCPServerInfo,
  MCPToolInfo,
  MCPCallResult,
  MeetLaunchResult
} from "@/lib/api";

export default function ToolsPage() {
  const [profiles, setProfiles] = useState<ChromeProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>("");
  const [meetUrl, setMeetUrl] = useState("");
  const [autoRecord, setAutoRecord] = useState(true);
  const [meetLoading, setMeetLoading] = useState(false);
  const [meetResult, setMeetResult] = useState<MeetLaunchResult | null>(null);
  const [meetError, setMeetError] = useState<string | null>(null);

  // Desktop Apps Launcher state
  const [appStatus, setAppStatus] = useState<{ [key: string]: string }>({});

  // MCP Servers & Tools state
  const [servers, setServers] = useState<MCPServerInfo[]>([]);
  const [tools, setTools] = useState<MCPToolInfo[]>([]);
  const [mcpLoading, setMcpLoading] = useState(true);

  // MCP Sandbox Runner state
  const [selectedTool, setSelectedTool] = useState<string>("");
  const [toolArgsJson, setToolArgsJson] = useState<string>("{}");
  const [executingTool, setExecutingTool] = useState(false);
  const [toolResult, setToolResult] = useState<MCPCallResult | null>(null);
  const [toolError, setToolError] = useState<string | null>(null);

  // New MCP Server form state
  const [showAddServer, setShowAddServer] = useState(false);
  const [newServerName, setNewServerName] = useState("");
  const [newServerCmd, setNewServerCmd] = useState("");
  const [newServerArgs, setNewServerArgs] = useState("");
  const [newServerDesc, setNewServerDesc] = useState("");

  const refreshAll = async () => {
    setMcpLoading(true);
    try {
      const [profData, srvData, toolData] = await Promise.all([
        getChromeProfiles().catch(() => ({ profiles: [] })),
        getMCPServers().catch(() => ({ servers: [] })),
        getMCPTools().catch(() => ({ tools: [] })),
      ]);

      setProfiles(profData.profiles);
      if (profData.profiles.length > 0 && !selectedProfile) {
        // Default to first profile with email
        const withEmail = profData.profiles.find((p) => p.email.includes("@"));
        setSelectedProfile(withEmail ? withEmail.email : profData.profiles[0].email);
      }

      setServers(srvData.servers);
      setTools(toolData.tools);
      if (toolData.tools.length > 0 && !selectedTool) {
        setSelectedTool(toolData.tools[0].name);
      }
    } finally {
      setMcpLoading(false);
    }
  };

  useEffect(() => {
    refreshAll();
  }, []);

  const handleLaunchMeet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!meetUrl.trim()) return;
    setMeetLoading(true);
    setMeetError(null);
    setMeetResult(null);

    try {
      const res = await launchGoogleMeet(meetUrl.trim(), selectedProfile || undefined, autoRecord);
      setMeetResult(res);
    } catch (err: any) {
      setMeetError(err.message || "Failed to launch Google Meet");
    } finally {
      setMeetLoading(false);
    }
  };

  const handleQuickAppLaunch = async (appName: string) => {
    setAppStatus((prev) => ({ ...prev, [appName]: "launching" }));
    try {
      const res = await launchDesktopApp(appName);
      if (res.status === "opened") {
        setAppStatus((prev) => ({ ...prev, [appName]: "opened" }));
      } else {
        setAppStatus((prev) => ({ ...prev, [appName]: res.message || "error" }));
      }
    } catch (err: any) {
      setAppStatus((prev) => ({ ...prev, [appName]: err.message || "error" }));
    }
    setTimeout(() => {
      setAppStatus((prev) => ({ ...prev, [appName]: "" }));
    }, 4000);
  };

  const handleExecuteTool = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTool) return;
    setExecutingTool(true);
    setToolError(null);
    setToolResult(null);

    let parsedArgs = {};
    try {
      parsedArgs = JSON.parse(toolArgsJson);
    } catch (err) {
      setToolError("Arguments must be valid JSON: " + String(err));
      setExecutingTool(false);
      return;
    }

    try {
      const res = await callMCPTool(selectedTool, parsedArgs);
      setToolResult(res);
    } catch (err: any) {
      setToolError(err.message || "Failed to execute tool");
    } finally {
      setExecutingTool(false);
    }
  };

  const handleSaveNewServer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newServerName.trim() || !newServerCmd.trim()) return;

    const argsList = newServerArgs
      .trim()
      .split(" ")
      .filter((a) => a.length > 0);

    const newCfg: MCPServerInfo = {
      name: newServerName.trim().toLowerCase().replace(/\s+/g, "_"),
      command: newServerCmd.trim(),
      args: argsList,
      enabled: true,
      description: newServerDesc.trim() || "User custom MCP server",
    };

    try {
      await saveMCPServer(newCfg);
      setShowAddServer(false);
      setNewServerName("");
      setNewServerCmd("");
      setNewServerArgs("");
      setNewServerDesc("");
      await refreshAll();
    } catch (err: any) {
      alert("Error adding server: " + err.message);
    }
  };

  const activeToolObj = tools.find((t) => t.name === selectedTool);

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 select-none">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-3xl font-bold tracking-tight text-white">System Tools & MCP Hub</h1>
            <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-mono border border-emerald-500/20">
              Desktop Native
            </span>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            Automate Google Meet, control computer applications, and orchestrate Model Context Protocol (MCP) tools.
          </p>
        </div>

        <button
          onClick={refreshAll}
          disabled={mcpLoading}
          className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium transition-colors flex items-center space-x-2 border border-slate-700 w-fit"
        >
          <RefreshCw className={`w-4 h-4 ${mcpLoading ? "animate-spin text-emerald-400" : ""}`} />
          <span>Refresh All Tools</span>
        </button>
      </div>

      {/* Grid: Google Meet & Desktop Apps */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Google Meet Controller */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <div className="w-9 h-9 rounded-xl bg-rose-500/10 text-rose-400 flex items-center justify-center">
                <Video className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-white">Google Meet Quick Join & Auto-Record</h2>
                <p className="text-xs text-slate-400">Launch Chrome under your selected account and record class audio.</p>
              </div>
            </div>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
              {profiles.length} Profiles Found
            </span>
          </div>

          {meetResult && (
            <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs space-y-1.5 text-emerald-300">
              <div className="font-semibold flex items-center space-x-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Google Meet Launched Successfully</span>
              </div>
              <p className="text-slate-300">
                Connected profile: <strong className="text-white">{meetResult.email}</strong> ({meetResult.profile_directory})
              </p>
              {meetResult.recording && (
                <div className="flex items-center justify-between pt-1 border-t border-emerald-500/20">
                  <span className="text-rose-300 flex items-center space-x-1">
                    <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
                    <span>WASAPI loopback recording active (Session #{meetResult.session_id})</span>
                  </span>
                  <Link href="/live" className="text-emerald-400 hover:text-emerald-300 font-semibold underline">
                    View Live Captions
                  </Link>
                </div>
              )}
            </div>
          )}

          {meetError && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{meetError}</span>
            </div>
          )}

          <form onSubmit={handleLaunchMeet} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                Google Account / Email
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {profiles.map((p) => {
                  const isSelected = selectedProfile === p.email;
                  return (
                    <button
                      type="button"
                      key={p.directory}
                      onClick={() => setSelectedProfile(p.email)}
                      className={`text-left p-2.5 rounded-lg border transition-all text-xs ${
                        isSelected
                          ? "bg-rose-500/10 border-rose-500 text-white shadow-sm"
                          : "bg-slate-950 border-slate-800 text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
                      }`}
                    >
                      <div className="font-semibold truncate">{p.name || p.directory}</div>
                      <div className="text-[11px] text-slate-400 font-mono truncate">{p.email}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                Google Meet Link or Code
              </label>
              <input
                type="text"
                required
                placeholder="e.g. meet.google.com/abc-defg-hij or abc-defg-hij"
                value={meetUrl}
                onChange={(e) => setMeetUrl(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-lg bg-slate-950 border border-slate-800 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-rose-500 transition-colors font-mono"
              />
            </div>

            <div className="flex items-center space-x-2 pt-1">
              <input
                type="checkbox"
                id="autoRecord"
                checked={autoRecord}
                onChange={(e) => setAutoRecord(e.target.checked)}
                className="rounded border-slate-700 bg-slate-950 text-rose-500 focus:ring-0"
              />
              <label htmlFor="autoRecord" className="text-xs text-slate-300 cursor-pointer">
                Automatically start lecture audio recording & live transcription on join
              </label>
            </div>

            <button
              type="submit"
              disabled={meetLoading || !meetUrl.trim()}
              className="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 disabled:opacity-50 text-white font-semibold text-sm transition-all flex items-center justify-center space-x-2 shadow-lg shadow-rose-600/20"
            >
              <Video className="w-4 h-4 fill-current" />
              <span>{meetLoading ? "Launching Chrome..." : "Join Google Meet with Selected Account"}</span>
            </button>
          </form>
        </div>

        {/* Desktop Computer Control */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm space-y-5">
          <div className="flex items-center space-x-2.5">
            <div className="w-9 h-9 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center">
              <Monitor className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Desktop Application Launcher</h2>
              <p className="text-xs text-slate-400">Directly control installed PC applications via allowlisted shell dispatcher.</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 pt-2">
            {[
              { id: "obsidian", name: "Obsidian Vault", desc: "Joe's Second Brain", icon: FolderOpen, color: "text-purple-400" },
              { id: "code", name: "VS Code", desc: "Code Editor", icon: FileCode, color: "text-blue-400" },
              { id: "chrome", name: "Google Chrome", desc: "Web Browser", icon: ExternalLink, color: "text-emerald-400" },
              { id: "terminal", name: "Windows Terminal", desc: "PowerShell / CLI", icon: Terminal, color: "text-slate-300" },
              { id: "calculator", name: "Calculator", desc: "System Math", icon: Command, color: "text-amber-400" },
              { id: "explorer", name: "File Explorer", desc: "Local Files", icon: FolderOpen, color: "text-sky-400" },
            ].map((app) => {
              const Icon = app.icon;
              const status = appStatus[app.id];
              return (
                <button
                  key={app.id}
                  onClick={() => handleQuickAppLaunch(app.id)}
                  className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80 hover:border-purple-500/40 hover:bg-slate-800/40 transition-all text-left flex flex-col justify-between group"
                >
                  <div className="flex items-center justify-between w-full">
                    <Icon className={`w-5 h-5 ${app.color} group-hover:scale-110 transition-transform`} />
                    <span className="text-[10px] font-mono text-slate-500 group-hover:text-purple-400">
                      {status === "launching" ? "Launching..." : status === "opened" ? "✓ Opened" : "Launch"}
                    </span>
                  </div>
                  <div className="mt-3">
                    <div className="text-xs font-semibold text-slate-200 group-hover:text-white transition-colors">
                      {app.name}
                    </div>
                    <div className="text-[11px] text-slate-500 truncate">{app.desc}</div>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="p-3.5 rounded-xl bg-purple-950/20 border border-purple-800/30 text-xs text-purple-300 space-y-1">
            <span className="font-semibold flex items-center space-x-1.5">
              <Sparkles className="w-3.5 h-3.5 text-purple-400" />
              <span>Voice & Copilot Integration</span>
            </span>
            <p className="text-slate-300 text-[11px] leading-relaxed">
              You can also open any of these by saying aloud: <strong className="text-white">"Eve, open Obsidian"</strong> or{" "}
              <strong className="text-white">"Eve, open VS Code"</strong>.
            </p>
          </div>
        </div>
      </div>

      {/* Model Context Protocol (MCP) Section */}
      <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
              <Terminal className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white flex items-center space-x-2">
                <span>Model Context Protocol (MCP) Tools</span>
                <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-mono">
                  JSON-RPC 2.0
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Connect external agents, database drivers, and cloud services directly to E.V.E.
              </p>
            </div>
          </div>

          <button
            onClick={() => setShowAddServer(true)}
            className="px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs transition-colors flex items-center space-x-1.5 shadow-lg shadow-emerald-600/20 w-fit"
          >
            <Plus className="w-4 h-4" />
            <span>Add Custom MCP Server</span>
          </button>
        </div>

        {/* Server Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {servers.map((srv) => (
            <div
              key={srv.name}
              className="p-4 rounded-xl bg-slate-950 border border-slate-800/80 space-y-3 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between">
                  <div className="font-bold text-sm text-white flex items-center space-x-2">
                    <span>{srv.name}</span>
                  </div>
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded flex items-center space-x-1 ${
                      srv.connected
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${srv.connected ? "bg-emerald-400 animate-pulse" : "bg-slate-500"}`} />
                    <span>{srv.connected ? "Connected" : "Inactive"}</span>
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-1">{srv.description}</p>
                <div className="mt-2 text-[11px] font-mono text-slate-500 bg-slate-900 px-2.5 py-1.5 rounded truncate">
                  {srv.command} {srv.args.join(" ")}
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-xs">
                <span className="text-slate-400">
                  Discovered Tools: <strong className="text-white">{srv.tools?.length || 0}</strong>
                </span>
                <span className={`text-[11px] font-medium ${srv.enabled ? "text-emerald-400" : "text-slate-500"}`}>
                  {srv.enabled ? "Enabled" : "Disabled"}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Interactive MCP Tool Execution Sandbox */}
        <div className="pt-4 border-t border-slate-800 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center space-x-2">
                <Cpu className="w-4 h-4 text-emerald-400" />
                <span>MCP Tool Execution Sandbox</span>
              </h3>
              <p className="text-xs text-slate-400">Select any connected MCP tool and test its live response.</p>
            </div>
            <span className="text-xs text-slate-500 font-mono">
              Total registered tools: {tools.length}
            </span>
          </div>

          <form onSubmit={handleExecuteTool} className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">
                  Select Tool
                </label>
                <select
                  value={selectedTool}
                  onChange={(e) => {
                    setSelectedTool(e.target.value);
                    const t = tools.find((x) => x.name === e.target.value);
                    if (t?.input_schema?.properties) {
                      const sample: Record<string, any> = {};
                      for (const [k, v] of Object.entries(t.input_schema.properties)) {
                        sample[k] = (v as any).default || "";
                      }
                      setToolArgsJson(JSON.stringify(sample, null, 2));
                    } else {
                      setToolArgsJson("{}");
                    }
                  }}
                  className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white text-xs font-mono focus:outline-none focus:border-emerald-500"
                >
                  {tools.map((t) => (
                    <option key={t.name} value={t.name}>
                      {t.name} ({t.server_name})
                    </option>
                  ))}
                </select>
              </div>

              {activeToolObj && (
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-400">
                  <div className="font-semibold text-slate-200">{activeToolObj.name}</div>
                  <div className="mt-0.5">{activeToolObj.description || "No description provided."}</div>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">
                  Arguments (JSON)
                </label>
                <textarea
                  rows={4}
                  value={toolArgsJson}
                  onChange={(e) => setToolArgsJson(e.target.value)}
                  className="w-full p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-emerald-400 font-mono focus:outline-none focus:border-emerald-500"
                />
              </div>

              <button
                type="submit"
                disabled={executingTool || !selectedTool}
                className="w-full py-2 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold text-xs transition-colors flex items-center justify-center space-x-1.5 shadow-md shadow-emerald-600/20"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>{executingTool ? "Executing..." : "Execute MCP Tool via E.V.E."}</span>
              </button>
            </div>

            {/* Output Sandbox Terminal */}
            <div className="rounded-xl bg-slate-950 border border-slate-800 p-4 font-mono text-xs flex flex-col justify-between">
              <div>
                <div className="text-slate-500 text-[11px] mb-2 border-b border-slate-800 pb-1 flex items-center justify-between">
                  <span>OUTPUT TERMINAL</span>
                  {toolResult && (
                    <span className={toolResult.is_error ? "text-rose-400" : "text-emerald-400"}>
                      {toolResult.is_error ? "Status: Error" : "Status: OK"}
                    </span>
                  )}
                </div>

                {toolError && <div className="text-rose-400 whitespace-pre-wrap">{toolError}</div>}

                {toolResult ? (
                  <pre className="text-slate-200 overflow-x-auto max-h-60 text-[11px] leading-relaxed">
                    {JSON.stringify(toolResult.content, null, 2)}
                  </pre>
                ) : !toolError ? (
                  <div className="text-slate-600 italic py-8 text-center">
                    Select a tool and click execute to inspect structured MCP results.
                  </div>
                ) : null}
              </div>
            </div>
          </form>
        </div>
      </div>

      {/* Add Custom MCP Server Modal */}
      {showAddServer && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-white">Add Custom MCP Server</h3>
            <p className="text-xs text-slate-400">
              Register a local or remote stdio-based MCP process (Python, Node, Go, or Rust).
            </p>

            <form onSubmit={handleSaveNewServer} className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-300 mb-1">Server Identifier Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. filesystem or sqlite_db"
                  value={newServerName}
                  onChange={(e) => setNewServerName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-300 mb-1">Executable Command</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. npx or python"
                  value={newServerCmd}
                  onChange={(e) => setNewServerCmd(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-300 mb-1">Arguments (Space-separated)</label>
                <input
                  type="text"
                  placeholder="e.g. -y @modelcontextprotocol/server-filesystem C:\data"
                  value={newServerArgs}
                  onChange={(e) => setNewServerArgs(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-emerald-500 font-mono text-[11px]"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-300 mb-1">Description (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. Local filesystem MCP driver"
                  value={newServerDesc}
                  onChange={(e) => setNewServerDesc(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="flex justify-end space-x-2 pt-3">
                <button
                  type="button"
                  onClick={() => setShowAddServer(false)}
                  className="px-3 py-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold shadow-md shadow-emerald-600/20"
                >
                  Save & Connect
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
