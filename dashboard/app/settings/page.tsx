"use client";

import React, { useEffect, useState } from "react";
import { 
  Settings as SettingsIcon, 
  Key, 
  Cpu, 
  Mic, 
  Folder, 
  CheckCircle2, 
  RefreshCw, 
  ShieldCheck,
  Calendar,
  BookOpen,
  ExternalLink,
  LogOut,
  AlertTriangle,
  Sparkles,
  Volume2,
  Bot,
  Radio,
  HardDrive,
  Trash2
} from "lucide-react";
import { 
  getStatus, 
  getDevices, 
  getStoredToken, 
  setStoredToken, 
  SystemStatus,
  getGoogleStatus,
  getGoogleAuthUrl,
  exchangeGoogleCode,
  syncGoogle,
  disconnectGoogle,
  GoogleStatus,
  getVoiceStatus,
  triggerWakeWord,
  VoiceStatus,
  purgeRetention
} from "@/lib/api";

export default function SettingsPage() {
  const [token, setToken] = useState("");
  const [savedTokenMsg, setSavedTokenMsg] = useState(false);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Google Integration states
  const [googleStatus, setGoogleStatus] = useState<GoogleStatus | null>(null);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [authCode, setAuthCode] = useState("");
  const [showCodeInput, setShowCodeInput] = useState(false);

  // Phase 5 Voice Assistant states
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
  const [wakeWordTriggerMsg, setWakeWordTriggerMsg] = useState<string | null>(null);

  // Phase 6 Retention Purge states
  const [purging, setPurging] = useState(false);
  const [purgeMsg, setPurgeMsg] = useState<string | null>(null);

  const handlePurgeRetention = async () => {
    setPurging(true);
    setPurgeMsg(null);
    try {
      const res = await purgeRetention();
      const mb = (res.freed_bytes / (1024 * 1024)).toFixed(1);
      setPurgeMsg(`Purged ${res.purged_count} raw audio file(s) (>30 days old). Freed ${mb} MB.`);
    } catch (err: any) {
      setPurgeMsg("Purge error: " + err.message);
    } finally {
      setPurging(false);
    }
  };

  const loadSettingsData = async () => {
    setLoading(true);
    setToken(getStoredToken());
    try {
      const [s, dev, g, v] = await Promise.all([
        getStatus().catch(() => null),
        getDevices().catch(() => []),
        getGoogleStatus().catch(() => null),
        getVoiceStatus().catch(() => null),
      ]);
      setStatus(s);
      setDevices(dev);
      setGoogleStatus(g);
      setVoiceStatus(v);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettingsData();
  }, []);

  const handleSaveToken = (e: React.FormEvent) => {
    e.preventDefault();
    setStoredToken(token.trim());
    setSavedTokenMsg(true);
    setTimeout(() => setSavedTokenMsg(false), 3000);
    loadSettingsData();
  };

  const handleConnectGoogle = async () => {
    setGoogleLoading(true);
    setSyncError(null);
    try {
      const { auth_url } = await getGoogleAuthUrl();
      window.open(auth_url, "_blank");
      setShowCodeInput(true);
    } catch (err: any) {
      setSyncError(err.message || "Failed to initiate Google authorization.");
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleExchangeCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authCode.trim()) return;
    setGoogleLoading(true);
    setSyncError(null);
    try {
      await exchangeGoogleCode(authCode.trim());
      setSyncMsg("Google account authenticated successfully! Refresh token saved to Windows Credential Manager.");
      setShowCodeInput(false);
      setAuthCode("");
      const g = await getGoogleStatus().catch(() => null);
      setGoogleStatus(g);
      setTimeout(() => setSyncMsg(null), 5000);
    } catch (err: any) {
      setSyncError(err.message || "Failed to exchange authorization code.");
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleSyncGoogle = async () => {
    setGoogleLoading(true);
    setSyncMsg(null);
    setSyncError(null);
    try {
      const res = await syncGoogle("all");
      const c = res.results.classroom?.new_tasks ?? 0;
      const cal = res.results.calendar?.created_events ?? 0;
      setSyncMsg(`Sync complete! Classroom: ${c} new assignments imported. Calendar: ${cal} new events created.`);
      setTimeout(() => setSyncMsg(null), 6000);
    } catch (err: any) {
      setSyncError(err.message || "Failed to sync Google Classroom & Calendar.");
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleDisconnectGoogle = async () => {
    if (!confirm("Are you sure you want to disconnect Google integration? This will remove the stored token from Windows Credential Manager.")) {
      return;
    }
    setGoogleLoading(true);
    setSyncMsg(null);
    setSyncError(null);
    try {
      await disconnectGoogle();
      setSyncMsg("Google account disconnected successfully.");
      const g = await getGoogleStatus().catch(() => null);
      setGoogleStatus(g);
      setShowCodeInput(false);
      setTimeout(() => setSyncMsg(null), 4000);
    } catch (err: any) {
      setSyncError(err.message || "Failed to disconnect Google account.");
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleTestWakeWord = async () => {
    try {
      await triggerWakeWord();
      setWakeWordTriggerMsg("Wake word triggered! Event published to WebSocket clients.");
      setTimeout(() => setWakeWordTriggerMsg(null), 3000);
    } catch (err: any) {
      alert("Failed to trigger wake word: " + err.message);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center space-x-2">
          <SettingsIcon className="w-6 h-6 text-emerald-400" />
          <span>System & Hardware Settings</span>
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Configure API authentication, view RTX 4060 GPU allocation, voice assistant, and manage integrations.
        </p>
      </div>

      <div className="space-y-6">
        {/* 1. API Token Authentication */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
              <Key className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">Local API Bearer Token</h2>
              <p className="text-xs text-slate-400">
                Generated per-installation at <code className="text-emerald-400 font-mono">data/api_token</code> to secure 127.0.0.1 loopback communication.
              </p>
            </div>
          </div>

          <form onSubmit={handleSaveToken} className="flex gap-2">
            <input
              type="password"
              placeholder="Paste Bearer token from data/api_token..."
              value={token}
              onChange={(e) => setToken(e.target.value)}
              className="flex-1 px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white placeholder-slate-500 text-xs focus:outline-none focus:border-emerald-500 font-mono"
            />
            <button
              type="submit"
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-colors shrink-0"
            >
              Save Token
            </button>
          </form>

          {savedTokenMsg && (
            <p className="text-xs text-emerald-400 flex items-center space-x-1.5 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Token saved successfully. Backend requests authorized.</span>
            </p>
          )}
        </div>

        {/* 2. Hardware Acceleration & AI Model Status */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-teal-500/10 text-teal-400 flex items-center justify-center">
              <Cpu className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">Hardware & Models</h2>
              <p className="text-xs text-slate-400">Local RTX 4060 CUDA STT and hybrid Gemini/Ollama LLM engine.</p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
              <div className="text-[11px] text-slate-400">Speech-to-Text Model:</div>
              <div className="text-sm font-bold text-white font-mono">faster-whisper large-v3-turbo</div>
              <div className="text-xs text-emerald-400">CUDA int8_float16 acceleration</div>
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
              <div className="text-[11px] text-slate-400">Intelligence Router:</div>
              <div className="text-sm font-bold text-white font-mono">
                {status?.has_cloud_llm ? "Gemini 2.5 Flash" : "Ollama 7B (Offline)"}
              </div>
              <div className="text-xs text-slate-400">Structured JSON schema output</div>
            </div>
          </div>
        </div>

        {/* 3. Obsidian Vault Linkage */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-purple-500/10 text-purple-400 flex items-center justify-center">
              <Folder className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">Obsidian Second Brain Integration</h2>
              <p className="text-xs text-slate-400">Automatic Markdown note generation with YAML frontmatter.</p>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Vault Path:</span>
              <span className="font-mono text-slate-200">C:\Users\Legion\Documents\Obsidian Vault</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Lecture Notes Folder:</span>
              <span className="font-mono text-emerald-400">13 - Lectures\&lt;Course&gt;\</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Active Plan Mirror:</span>
              <span className="font-mono text-slate-200">01 - Projects\E.V.E\Active-Plan.md</span>
            </div>
          </div>
        </div>

        {/* 4. Google Classroom & Calendar Integration */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 rounded-lg bg-sky-500/10 text-sky-400 flex items-center justify-center">
                <BookOpen className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-white">Google Classroom & Calendar Integration</h2>
                <p className="text-xs text-slate-400">
                  Read-only coursework sync & dedicated &quot;{googleStatus?.calendar_name || "E.V.E."}&quot; calendar event publishing.
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${
                googleStatus?.authenticated
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  : "bg-slate-800 text-slate-400"
              }`}>
                {googleStatus?.authenticated ? "Connected" : "Disconnected"}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 space-y-1">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider">OAuth Credentials</div>
              <div className="font-semibold text-slate-200">
                {googleStatus?.configured ? (
                  <span className="text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Configured
                  </span>
                ) : (
                  <span className="text-amber-400 flex items-center gap-1">
                    <AlertTriangle className="w-3.5 h-3.5" /> Missing client_secrets.json
                  </span>
                )}
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 space-y-1">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider">Classroom Access</div>
              <div className="font-semibold text-sky-400">Read-Only (Academic Safe)</div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 space-y-1">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider">Target Calendar</div>
              <div className="font-semibold text-purple-400 font-mono">
                {googleStatus?.calendar_name || "E.V.E."} (Isolated)
              </div>
            </div>
          </div>

          <div className="pt-2 flex flex-wrap items-center gap-3">
            {!googleStatus?.authenticated ? (
              <button
                type="button"
                onClick={handleConnectGoogle}
                disabled={googleLoading || !googleStatus?.configured}
                className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-semibold text-xs transition-colors flex items-center space-x-1.5"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>{googleLoading ? "Connecting..." : "Connect Google Account"}</span>
              </button>
            ) : (
              <>
                <button
                  type="button"
                  onClick={handleSyncGoogle}
                  disabled={googleLoading}
                  className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold text-xs transition-colors flex items-center space-x-1.5"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${googleLoading ? "animate-spin" : ""}`} />
                  <span>{googleLoading ? "Syncing..." : "Sync Now"}</span>
                </button>

                <button
                  type="button"
                  onClick={handleDisconnectGoogle}
                  disabled={googleLoading}
                  className="px-3.5 py-2 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 font-medium text-xs transition-colors flex items-center space-x-1.5"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span>Disconnect</span>
                </button>
              </>
            )}
          </div>

          {showCodeInput && (
            <form onSubmit={handleExchangeCode} className="p-4 rounded-xl bg-slate-950 border border-sky-500/30 space-y-2">
              <p className="text-xs text-slate-300 font-medium">
                Authorization prompt opened in browser. If redirected to code page, paste your authorization code below:
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Paste Google Authorization Code (4/0A...)..."
                  value={authCode}
                  onChange={(e) => setAuthCode(e.target.value)}
                  className="flex-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs text-white placeholder-slate-500 font-mono focus:outline-none focus:border-sky-500"
                />
                <button
                  type="submit"
                  disabled={googleLoading || !authCode.trim()}
                  className="px-4 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-semibold text-xs"
                >
                  Complete Link
                </button>
              </div>
            </form>
          )}

          {syncMsg && (
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{syncMsg}</span>
            </div>
          )}

          {syncError && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center space-x-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{syncError}</span>
            </div>
          )}
        </div>

        {/* 5. Phase 5: Voice Assistant & Kokoro TTS Engine */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 rounded-lg bg-purple-500/10 text-purple-400 flex items-center justify-center">
                <Bot className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-white">Voice Assistant & Kokoro TTS</h2>
                <p className="text-xs text-slate-400">
                  Wake word detection (&quot;Hey Eve&quot;), local Kokoro 24 kHz speech synthesis, and Live Copilot.
                </p>
              </div>
            </div>

            <button
              onClick={handleTestWakeWord}
              className="px-3 py-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/30 text-xs font-semibold flex items-center space-x-1.5 transition-colors"
            >
              <Radio className="w-3.5 h-3.5 text-purple-400" />
              <span>Simulate &quot;Hey Eve&quot;</span>
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 space-y-1">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider">Wake Word Engine</div>
              <div className="font-semibold text-slate-200">
                {voiceStatus?.wakeword_loaded ? (
                  <span className="text-emerald-400">ONNX Model Loaded</span>
                ) : (
                  <span className="text-sky-400">Phonetic/Utterance Matcher</span>
                )}
              </div>
              <div className="text-[10px] text-slate-500">&quot;Hey Eve&quot; / &quot;Hi Eve&quot; / Ctrl+Alt+E</div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 space-y-1">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider">Text-To-Speech</div>
              <div className="font-semibold text-slate-200">
                {voiceStatus?.tts_loaded ? (
                  <span className="text-emerald-400 font-mono">Kokoro-ONNX (24 kHz)</span>
                ) : (
                  <span className="text-amber-400 font-mono">Synthetic Tone Fallback</span>
                )}
              </div>
              <div className="text-[10px] text-slate-500">Voice: {voiceStatus?.tts_voice || "af_sarah"}</div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 space-y-1">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider">Live Copilot</div>
              <div className="font-semibold text-purple-400">
                {voiceStatus?.copilot_enabled ? "Enabled (180s Window)" : "Disabled"}
              </div>
              <div className="text-[10px] text-slate-500">Silent classroom talking points</div>
            </div>
          </div>

          {wakeWordTriggerMsg && (
            <p className="text-xs text-purple-400 flex items-center space-x-1.5 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{wakeWordTriggerMsg}</span>
            </p>
          )}
        </div>

        {/* 6. Audio Devices */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 rounded-lg bg-sky-500/10 text-sky-400 flex items-center justify-center">
                <Mic className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-white">Audio Endpoints (PyAudioWPatch)</h2>
                <p className="text-xs text-slate-400">Active capture devices on your Windows machine.</p>
              </div>
            </div>

            <button
              onClick={loadSettingsData}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
              title="Refresh Devices"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>

          {devices.length === 0 ? (
            <p className="text-xs text-slate-500">No hardware devices reported by backend yet.</p>
          ) : (
            <div className="divide-y divide-slate-800 bg-slate-950 rounded-xl border border-slate-800 overflow-hidden text-xs">
              {devices.map((d) => (
                <div key={d.id} className="p-3 flex items-center justify-between">
                  <div className="space-y-0.5">
                    <span className="font-medium text-slate-200">{d.name}</span>
                    <div className="text-[10px] text-slate-400 font-mono">
                      Type: {d.type} {d.is_default && "• Default Endpoint"}
                    </div>
                  </div>
                  <span className={`text-[10px] px-2 py-0.5 rounded font-mono ${
                    d.type === "loopback" ? "bg-emerald-500/10 text-emerald-400" : "bg-sky-500/10 text-sky-400"
                  }`}>
                    {d.type === "loopback" ? "WASAPI Loopback" : "Microphone"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 7. Storage & Audio Retention */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
                <HardDrive className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-white">Audio Retention & Storage Policy</h2>
                <p className="text-xs text-slate-400">
                  Automatic 30-day retention cleans raw WAV audio while preserving Obsidian notes, transcripts, and RAG vectors forever.
                </p>
              </div>
            </div>

            <button
              onClick={handlePurgeRetention}
              disabled={purging}
              className="flex items-center space-x-2 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-colors disabled:opacity-50"
            >
              <Trash2 className={`w-3.5 h-3.5 ${purging ? "animate-spin" : "text-amber-400"}`} />
              <span>{purging ? "Scanning & Cleaning..." : "Purge Expired Audio (>30d)"}</span>
            </button>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80 text-xs space-y-1.5">
            <div className="flex items-center justify-between text-slate-300">
              <span className="font-medium">Raw WAV Retention:</span>
              <span className="font-mono text-emerald-400">30 Days (Scheduled Daily)</span>
            </div>
            <div className="flex items-center justify-between text-slate-400 text-[11px]">
              <span>SQLite Transcripts & RAG Chunks:</span>
              <span className="text-slate-300">Permanent (Zero Loss)</span>
            </div>
            <div className="flex items-center justify-between text-slate-400 text-[11px]">
              <span>Obsidian Vault Notes:</span>
              <span className="text-slate-300">Local Markdown (Permanent)</span>
            </div>
          </div>

          {purgeMsg && (
            <p className="text-xs text-emerald-400 flex items-center space-x-1.5 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{purgeMsg}</span>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
