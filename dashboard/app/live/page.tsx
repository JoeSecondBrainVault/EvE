"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { 
  Square, 
  Radio, 
  User, 
  Volume2, 
  Clock, 
  Sparkles, 
  AlertCircle, 
  ArrowLeft,
  Bookmark,
  Bot,
  Mic,
  ChevronRight,
  ChevronDown,
  RefreshCw,
  Send,
  HelpCircle,
  Copy,
  Check
} from "lucide-react";
import { 
  getLiveWebSocketUrl, 
  getStoredToken, 
  ensureToken,
  getStatus, 
  stopSession, 
  processSession, 
  SystemStatus,
  getCopilotRecent,
  suggestCopilot,
  interactVoice,
  triggerWakeWord,
  CopilotSuggestion,
  VoiceInteractResult
} from "@/lib/api";

interface LiveSegment {
  source: "them" | "me";
  text: string;
  t0: number;
  t1: number;
}

export default function LiveCaptionsPage() {
  const router = useRouter();
  const [segments, setSegments] = useState<LiveSegment[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [speakerFilter, setSpeakerFilter] = useState<"all" | "them" | "me">("all");
  const [bookmarks, setBookmarks] = useState<number[]>([]);

  // Phase 5: Live Copilot states
  const [copilotOpen, setCopilotOpen] = useState(true);
  const [copilotSuggestion, setCopilotSuggestion] = useState<CopilotSuggestion | null>(null);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  // Phase 5: Voice Assistant command bar states
  const [voiceInput, setVoiceInput] = useState("");
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [voiceReply, setVoiceReply] = useState<VoiceInteractResult | null>(null);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Poll system status & initial copilot suggestion
  useEffect(() => {
    getStatus().then(setStatus).catch(() => {});
    getCopilotRecent().then((res) => {
      if (res.suggestion) setCopilotSuggestion(res.suggestion);
    }).catch(() => {});
    try {
      const saved = localStorage.getItem("eve_live_bookmarks");
      if (saved) setBookmarks(JSON.parse(saved));
    } catch {}
  }, []);

  // Timer
  useEffect(() => {
    if (!status?.active_session_id) return;
    const interval = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [status?.active_session_id]);

  // WebSocket Connection
  useEffect(() => {
    const wsUrl = getLiveWebSocketUrl();
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = async () => {
      setWsConnected(true);
      const token = await ensureToken();
      ws.send(JSON.stringify({ type: "auth", token }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "segment") {
          setSegments((prev) => [...prev, {
            source: data.source,
            text: data.text,
            t0: data.t0,
            t1: data.t1,
          }]);
        } else if (data.type === "copilot_suggestion") {
          // Automatic real-time Live Copilot trigger
          if (data.data) {
            setCopilotSuggestion(data.data);
          }
        }
      } catch (err) {
        console.error("Failed to parse live WebSocket message:", err);
      }
    };

    ws.onclose = () => setWsConnected(false);
    ws.onerror = () => setWsConnected(false);

    return () => ws.close();
  }, []);

  // Auto-scroll
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [segments]);

  const handleStop = async () => {
    if (!confirm("Stop recording this session? Post-processing will automatically extract notes, tasks, and flashcards.")) return;
    setStopping(true);
    try {
      localStorage.removeItem("eve_live_bookmarks");
    } catch {}
    try {
      const res = await stopSession();
      const sid = res.id ?? res.session_id;
      if (sid) {
        await processSession(sid);
        router.push(`/lectures/${sid}`);
      } else {
        router.push("/lectures");
      }
    } catch (err: any) {
      alert("Error stopping session: " + err.message);
      setStopping(false);
    }
  };

  const handleManualCopilotHint = async () => {
    setCopilotLoading(true);
    try {
      const res = await suggestCopilot();
      if (res.suggestion) {
        setCopilotSuggestion(res.suggestion);
        setCopilotOpen(true);
      }
    } catch (err: any) {
      console.error("Failed to get copilot hint:", err);
    } finally {
      setCopilotLoading(false);
    }
  };

  const handleSendVoiceCommand = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!voiceInput.trim()) return;
    setVoiceLoading(true);
    try {
      const res = await interactVoice(voiceInput.trim(), true);
      setVoiceReply(res);
      setVoiceInput("");
      // If audio base64 is present, play it through web audio
      if (res.audio_base64) {
        try {
          const snd = new Audio(`data:audio/wav;base64,${res.audio_base64}`);
          snd.play();
        } catch {
          // ignore web audio autoplay errors
        }
      }
    } catch (err: any) {
      alert("Voice command error: " + err.message);
    } finally {
      setVoiceLoading(false);
    }
  };

  const copyPoint = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(idx);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const formatTimer = (total: number) => {
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const filteredSegments = segments.filter((s) => {
    if (speakerFilter === "all") return true;
    return s.source === speakerFilter;
  });

  const addBookmark = () => {
    setBookmarks((prev) => {
      const updated = [...prev, elapsedSeconds];
      try {
        localStorage.setItem("eve_live_bookmarks", JSON.stringify(updated));
      } catch {}
      return updated;
    });
  };

  return (
    <div className="flex flex-col h-full bg-slate-950">
      {/* Top Bar */}
      <header className="px-6 py-4 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between shrink-0">
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <span className={`w-3 h-3 rounded-full ${wsConnected ? "bg-rose-500 animate-pulse" : "bg-slate-600"}`} />
            <h1 className="text-base font-bold text-white flex items-center space-x-2">
              <span>Live Lecture Captions</span>
            </h1>
          </div>

          <div className="hidden sm:flex items-center space-x-1.5 px-3 py-1 rounded-full bg-slate-800 text-slate-300 text-xs font-mono">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>{formatTimer(elapsedSeconds)}</span>
          </div>

          <span className={`text-[11px] px-2 py-0.5 rounded font-medium ${
            wsConnected ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
          }`}>
            {wsConnected ? "WS Live Stream" : "Disconnected"}
          </span>
        </div>

        <div className="flex items-center space-x-3">
          {/* Speaker Filter */}
          <div className="flex bg-slate-800 rounded-lg p-0.5 text-xs">
            <button
              onClick={() => setSpeakerFilter("all")}
              className={`px-2.5 py-1 rounded-md transition-colors ${speakerFilter === "all" ? "bg-slate-700 text-white font-medium" : "text-slate-400 hover:text-white"}`}
            >
              All
            </button>
            <button
              onClick={() => setSpeakerFilter("them")}
              className={`px-2.5 py-1 rounded-md transition-colors ${speakerFilter === "them" ? "bg-slate-700 text-emerald-400 font-medium" : "text-slate-400 hover:text-white"}`}
            >
              Instructor
            </button>
            <button
              onClick={() => setSpeakerFilter("me")}
              className={`px-2.5 py-1 rounded-md transition-colors ${speakerFilter === "me" ? "bg-slate-700 text-sky-400 font-medium" : "text-slate-400 hover:text-white"}`}
            >
              You
            </button>
          </div>

          <button
            onClick={addBookmark}
            title="Add timestamp bookmark"
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
          >
            <Bookmark className="w-4 h-4" />
          </button>

          {/* Quick Copilot Trigger Button */}
          <button
            onClick={handleManualCopilotHint}
            disabled={copilotLoading}
            className="px-3 py-2 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/30 text-xs font-semibold flex items-center space-x-1.5 transition-colors"
            title="Ask Copilot for talking points on what the professor just asked"
          >
            <Sparkles className={`w-3.5 h-3.5 ${copilotLoading ? "animate-spin text-purple-400" : "text-purple-400"}`} />
            <span>{copilotLoading ? "Analyzing..." : "Copilot Talking Points"}</span>
          </button>

          {status?.active_session_id && (
            <button
              onClick={handleStop}
              disabled={stopping}
              className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold uppercase tracking-wider flex items-center space-x-2 shadow-lg shadow-rose-600/20 transition-colors"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
              <span>{stopping ? "Processing..." : "Stop & Analyze"}</span>
            </button>
          )}
        </div>
      </header>

      {/* Main Body: Left Captions + Right Copilot Panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* Captions Scroll Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4 max-w-4xl mx-auto w-full">
          {filteredSegments.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <div className="w-12 h-12 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-500 mb-3">
                <Radio className="w-6 h-6 animate-pulse" />
              </div>
              <p className="text-sm font-medium text-slate-300">Listening for speech...</p>
              <p className="text-xs text-slate-500 mt-1 max-w-sm">
                Capturing PC system audio (Zoom, Google Meet, Teams, YouTube) and microphone in real time.
              </p>
            </div>
          ) : (
            filteredSegments.map((seg, idx) => {
              const isSpeaker = seg.source === "them";
              return (
                <div
                  key={idx}
                  className={`p-4 rounded-2xl border transition-all ${
                    isSpeaker
                      ? "bg-slate-900/90 border-slate-800 text-slate-200"
                      : "bg-sky-950/20 border-sky-800/40 text-sky-100 ml-8"
                  }`}
                >
                  <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1.5 font-mono">
                    <div className="flex items-center space-x-1.5 font-sans font-semibold">
                      {isSpeaker ? (
                        <>
                          <Volume2 className="w-3.5 h-3.5 text-emerald-400" />
                          <span className="text-emerald-400">Instructor / System Audio</span>
                        </>
                      ) : (
                        <>
                          <User className="w-3.5 h-3.5 text-sky-400" />
                          <span className="text-sky-400">You (Microphone)</span>
                        </>
                      )}
                    </div>
                    <span>{Math.floor(seg.t0 / 60)}:{(Math.floor(seg.t0) % 60).toString().padStart(2, "0")}</span>
                  </div>
                  <p className="text-sm leading-relaxed">{seg.text}</p>
                </div>
              );
            })
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Phase 5: Live Copilot Side Panel */}
        <aside className="w-80 lg:w-96 border-l border-slate-800 bg-slate-900/70 flex flex-col shrink-0">
          <div className="p-4 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Bot className="w-4 h-4 text-purple-400" />
              <h2 className="text-xs font-bold text-white uppercase tracking-wider">Live Copilot</h2>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 font-mono">
                Silent
              </span>
            </div>
            <button
              onClick={() => setCopilotOpen(!copilotOpen)}
              className="text-slate-400 hover:text-white"
              aria-label={copilotOpen ? "Collapse Live Copilot" : "Expand Live Copilot"}
              title={copilotOpen ? "Collapse Live Copilot" : "Expand Live Copilot"}
            >
              {copilotOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>
          </div>

          {copilotOpen && (
            <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
              {copilotSuggestion ? (
                <div className="space-y-3">
                  <div className="p-3 rounded-xl bg-purple-950/20 border border-purple-500/20 space-y-1">
                    <span className="text-[10px] uppercase font-bold text-purple-400 tracking-wider">
                      Active Topic / Question
                    </span>
                    <h3 className="font-semibold text-white text-xs leading-snug">
                      {copilotSuggestion.topic}
                    </h3>
                    <p className="text-[11px] text-slate-400 italic">
                      &quot;{copilotSuggestion.context_summary}&quot;
                    </p>
                  </div>

                  <div className="space-y-2">
                    <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                      Concise Talking Points
                    </span>
                    {copilotSuggestion.talking_points.map((pt, i) => (
                      <div
                        key={i}
                        className="p-3 rounded-xl bg-slate-950 border border-slate-800 hover:border-slate-700 transition-colors flex items-start justify-between gap-2 group"
                      >
                        <p className="text-slate-200 text-xs leading-relaxed">{pt}</p>
                        <button
                          onClick={() => copyPoint(pt, i)}
                          title="Copy point"
                          className="shrink-0 p-1 text-slate-500 hover:text-slate-300 transition-colors"
                        >
                          {copiedIndex === i ? (
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-center py-12 text-slate-500 space-y-2">
                  <Sparkles className="w-6 h-6 mx-auto text-slate-600" />
                  <p className="font-medium text-slate-400">Silent Classroom Copilot</p>
                  <p className="text-[11px] text-slate-500 max-w-xs mx-auto">
                    When the professor asks a question, E.V.E. automatically suggests bulleted talking points drawn from your past lectures.
                  </p>
                </div>
              )}

              {/* Voice Command feedback if any */}
              {voiceReply && (
                <div className="p-3.5 rounded-xl bg-sky-950/20 border border-sky-800/40 space-y-2 text-xs">
                  <div className="flex items-center space-x-1.5 text-sky-400 font-semibold text-[11px]">
                    <Mic className="w-3 h-3" />
                    <span>E.V.E. Assistant Response</span>
                  </div>
                  <p className="text-slate-200">{voiceReply.response_text}</p>

                  {/* Interactive Account Clarification Chips */}
                  {voiceReply.tool_output?.status === "clarification_needed" && voiceReply.tool_output?.available_emails && (
                    <div className="pt-2 border-t border-sky-900/40 space-y-1.5">
                      <div className="text-[11px] text-slate-400 font-medium">Click an account to join with:</div>
                      <div className="flex flex-wrap gap-1.5">
                        {voiceReply.tool_output.available_emails.map((email: string) => (
                          <button
                            key={email}
                            type="button"
                            onClick={async () => {
                              const meetCode = voiceReply.tool_output?.meet_url || "";
                              setVoiceLoading(true);
                              try {
                                const rep = await interactVoice(`join google meet ${meetCode} with ${email}`);
                                setVoiceReply(rep);
                              } catch (err: any) {
                                alert("Failed to join: " + err.message);
                              } finally {
                                setVoiceLoading(false);
                              }
                            }}
                            className="px-2.5 py-1 rounded-lg bg-sky-900/60 hover:bg-sky-800 text-sky-200 border border-sky-700/60 font-mono text-[11px] transition-colors"
                          >
                            {email}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Phase 5 Voice Command Input Bar */}
          <form
            onSubmit={handleSendVoiceCommand}
            className="p-3 border-t border-slate-800 bg-slate-900/90 flex gap-2"
          >
            <input
              type="text"
              placeholder="Ask Eve (e.g. 'what is due Friday?')..."
              value={voiceInput}
              onChange={(e) => setVoiceInput(e.target.value)}
              className="flex-1 px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
            />
            <button
              type="submit"
              disabled={voiceLoading || !voiceInput.trim()}
              className="p-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white transition-colors"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </form>
        </aside>
      </div>

      {/* Bookmarks bar */}
      {bookmarks.length > 0 && (
        <div className="px-6 py-2 border-t border-slate-800/80 bg-slate-900/40 flex items-center space-x-2 text-xs text-slate-400 shrink-0">
          <Bookmark className="w-3.5 h-3.5 text-amber-400" />
          <span>Bookmarked moments:</span>
          {bookmarks.map((b, i) => (
            <span key={i} className="px-1.5 py-0.5 rounded bg-slate-800 text-amber-300 font-mono">
              {formatTimer(b)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
