"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { 
  Play, 
  Square, 
  Clock, 
  BookOpen, 
  CheckCircle2, 
  AlertCircle, 
  ArrowRight, 
  Layers, 
  FileText,
  Calendar,
  Sparkles,
  Video,
  ExternalLink,
  FolderOpen,
  FileCode,
  Terminal,
  Command
} from "lucide-react";
import { 
  getStats, 
  getSessions, 
  getTasks, 
  startSession, 
  stopSession, 
  updateTaskStatus, 
  getChromeProfiles,
  launchGoogleMeet,
  launchDesktopApp,
  getStoredToken,
  ensureToken,
  ChromeProfile,
  Stats, 
  Session, 
  Task 
} from "@/lib/api";

export default function OverviewPage() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasToken, setHasToken] = useState(true);

  // Launcher tab mode: "meet" or "manual"
  const [launcherMode, setLauncherMode] = useState<"meet" | "manual">("meet");

  // Google Meet launcher state
  const [profiles, setProfiles] = useState<ChromeProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>("");
  const [meetUrl, setMeetUrl] = useState("");
  const [meetLoading, setMeetLoading] = useState(false);
  const [meetError, setMeetError] = useState<string | null>(null);

  // Desktop apps launcher status
  const [appStatus, setAppStatus] = useState<Record<string, string>>({});

  // New session form state (manual)
  const [title, setTitle] = useState("");
  const [course, setCourse] = useState("");
  const [consent, setConsent] = useState(true);
  const [starting, setStarting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadData = async () => {
    let token = getStoredToken();
    if (!token) {
      token = await ensureToken();
    }
    if (!token) {
      setHasToken(false);
      setLoading(false);
      return;
    }
    setHasToken(true);
    try {
      const [sData, sessData, tData, profData] = await Promise.all([
        getStats().catch(() => null),
        getSessions().catch(() => []),
        getTasks().catch(() => []),
        getChromeProfiles().catch(() => ({ profiles: [] })),
      ]);
      if (sData) setStats(sData);
      setSessions(sessData.slice(0, 5));
      setTasks(tData.filter(t => t.status === "inbox" || t.status === "todo").slice(0, 6));
      setProfiles(profData.profiles);
      if (profData.profiles.length > 0 && !selectedProfile) {
        const withEmail = profData.profiles.find(p => p.email.includes("@"));
        setSelectedProfile(withEmail ? withEmail.email : profData.profiles[0].email);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleLaunchMeet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!meetUrl.trim()) return;
    setMeetLoading(true);
    setMeetError(null);
    try {
      await launchGoogleMeet(meetUrl.trim(), selectedProfile || undefined, true);
      router.push("/live");
    } catch (err: any) {
      setMeetError(err.message || "Failed to launch Google Meet");
      setMeetLoading(false);
    }
  };

  const handleQuickApp = async (appId: string) => {
    setAppStatus(prev => ({ ...prev, [appId]: "launching" }));
    try {
      const res = await launchDesktopApp(appId);
      if (res.status === "opened") {
        setAppStatus(prev => ({ ...prev, [appId]: "opened" }));
      } else {
        setAppStatus(prev => ({ ...prev, [appId]: "error" }));
      }
    } catch {
      setAppStatus(prev => ({ ...prev, [appId]: "error" }));
    }
    setTimeout(() => {
      setAppStatus(prev => ({ ...prev, [appId]: "" }));
    }, 3000);
  };

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setStarting(true);
    setActionError(null);
    try {
      await startSession(title.trim(), course.trim() || undefined);
      router.push("/live");
    } catch (err: any) {
      setActionError(err.message || "Failed to start session");
    } finally {
      setStarting(false);
    }
  };


  const activeSession = sessions.find(s => s.status === "recording");

  const handleCompleteTask = async (taskId: number) => {
    try {
      await updateTaskStatus(taskId, "done");
      setTasks(prev => prev.filter(t => t.id !== taskId));
    } catch (err: any) {
      alert("Failed to update task: " + err.message);
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Missing Token Setup Banner */}
      {!hasToken && (
        <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <AlertCircle className="w-5 h-5 text-amber-400 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-amber-200">API Bearer Token Required</p>
              <p className="text-xs text-amber-400/80">
                Connect your local E.V.E. backend by copying the token from <code className="bg-slate-900 px-1.5 py-0.5 rounded text-slate-300 font-mono">data/api_token</code> into Settings.
              </p>
            </div>
          </div>
          <Link
            href="/settings"
            className="px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-semibold transition-colors shrink-0 text-center"
          >
            Configure Token
          </Link>
        </div>
      )}

      {/* Header Greeting */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white flex items-center space-x-2">
            <span>Welcome to E.V.E.</span>
            <Sparkles className="w-5 h-5 text-emerald-400" />
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Personal Study & Work Assistant • Local AI Transcriptions & Obsidian Vault Sync
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <Link
            href="/live"
            className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm transition-colors flex items-center space-x-2 shadow-lg shadow-emerald-600/20"
          >
            <Play className="w-4 h-4 fill-current" />
            <span>Open Live Captions</span>
          </Link>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 flex items-center space-x-4">
          <div className="w-12 h-12 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
            <BookOpen className="w-6 h-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{stats?.total_sessions ?? 0}</div>
            <div className="text-xs text-slate-400 font-medium">Recorded Lectures</div>
          </div>
        </div>

        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 flex items-center space-x-4">
          <div className="w-12 h-12 rounded-lg bg-teal-500/10 text-teal-400 flex items-center justify-center">
            <Clock className="w-6 h-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{stats?.total_hours_recorded ?? 0}h</div>
            <div className="text-xs text-slate-400 font-medium">Hours Transcribed</div>
          </div>
        </div>

        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 flex items-center space-x-4">
          <div className="w-12 h-12 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
            <AlertCircle className="w-6 h-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{stats?.pending_tasks ?? 0}</div>
            <div className="text-xs text-slate-400 font-medium">Pending Deadlines</div>
          </div>
        </div>

        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 flex items-center space-x-4">
          <div className="w-12 h-12 rounded-lg bg-purple-500/10 text-purple-400 flex items-center justify-center">
            <Layers className="w-6 h-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{stats?.total_flashcards ?? 0}</div>
            <div className="text-xs text-slate-400 font-medium">Flashcards Created</div>
          </div>
        </div>
      </div>

      {/* Main Grid: Launcher + Tasks */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left 2 Cols: Session Launcher or Active Banner */}
        <div className="lg:col-span-2 space-y-6">
          {activeSession ? (
            <div className="p-6 rounded-2xl bg-gradient-to-br from-rose-950/40 via-slate-900 to-slate-900 border border-rose-500/30 shadow-xl">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <span className="w-3.5 h-3.5 rounded-full bg-rose-500 animate-pulse" />
                  <span className="text-sm font-semibold uppercase tracking-wider text-rose-400">Session in Progress</span>
                </div>
                <Link
                  href="/live"
                  className="px-3.5 py-1.5 rounded-lg bg-rose-500 text-white font-semibold text-xs hover:bg-rose-600 transition-colors"
                >
                  View Captions
                </Link>
              </div>

              <div className="mt-4">
                <h3 className="text-xl font-bold text-white">{activeSession.title}</h3>
                {activeSession.course && (
                  <span className="inline-block mt-1 text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 font-medium">
                    {activeSession.course}
                  </span>
                )}
                <p className="text-xs text-slate-400 mt-2">
                  Recording both PC audio (WASAPI loopback) and microphone with continuous Whisper STT.
                </p>
              </div>
            </div>
          ) : (
            <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm space-y-5">
              {/* Launcher Header & Tabs */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
                <div>
                  <h2 className="text-base font-bold text-white flex items-center space-x-2">
                    <span>Launch Study Session</span>
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Record PC audio & mic locally with local Whisper transcription.
                  </p>
                </div>

                <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
                  <button
                    type="button"
                    onClick={() => setLauncherMode("meet")}
                    className={`px-3 py-1.5 rounded-lg font-medium transition-colors flex items-center space-x-1.5 ${
                      launcherMode === "meet"
                        ? "bg-rose-500 text-white shadow-sm"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    <Video className="w-3.5 h-3.5" />
                    <span>Google Meet</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setLauncherMode("manual")}
                    className={`px-3 py-1.5 rounded-lg font-medium transition-colors flex items-center space-x-1.5 ${
                      launcherMode === "manual"
                        ? "bg-emerald-600 text-white shadow-sm"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Manual Rec</span>
                  </button>
                </div>
              </div>

              {launcherMode === "meet" ? (
                /* Google Meet Quick Join Form */
                <form onSubmit={handleLaunchMeet} className="space-y-4">
                  {meetError && (
                    <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-center space-x-2">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      <span>{meetError}</span>
                    </div>
                  )}

                  {profiles.length > 1 && (
                    <div>
                      <label className="block text-xs font-semibold text-slate-400 mb-1.5">
                        Chrome Profile (Optional)
                      </label>
                      <select
                        value={selectedProfile}
                        onChange={(e) => setSelectedProfile(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-300 text-xs focus:outline-none focus:border-rose-500"
                      >
                        <option value="">Default Chrome Account</option>
                        {profiles.map((p) => (
                          <option key={p.directory} value={p.email}>
                            {p.name || p.directory} ({p.email})
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                      Google Meet URL or Code
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

                  <button
                    type="submit"
                    disabled={meetLoading || !meetUrl.trim()}
                    className="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 disabled:opacity-50 text-white font-semibold text-sm transition-all flex items-center justify-center space-x-2 shadow-lg shadow-rose-600/20"
                  >
                    <Video className="w-4 h-4 fill-current" />
                    <span>{meetLoading ? "Launching Chrome..." : "Join Meet & Auto-Record Lecture"}</span>
                  </button>
                </form>
              ) : (
                /* Manual Recording Form */
                <form onSubmit={handleStart} className="space-y-4">
                  {actionError && (
                    <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
                      {actionError}
                    </div>
                  )}

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                      Lecture Title
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Subnetting & CIDR Notation"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full px-3.5 py-2.5 rounded-lg bg-slate-950 border border-slate-800 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-emerald-500 transition-colors"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                      Course / Subject (Optional)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. IT 222 Networking"
                      value={course}
                      onChange={(e) => setCourse(e.target.value)}
                      className="w-full px-3.5 py-2.5 rounded-lg bg-slate-950 border border-slate-800 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-emerald-500 transition-colors"
                    />
                  </div>

                  <div className="flex items-center space-x-2 pt-1">
                    <input
                      type="checkbox"
                      id="consent"
                      checked={consent}
                      onChange={(e) => setConsent(e.target.checked)}
                      className="rounded border-slate-700 bg-slate-950 text-emerald-500 focus:ring-0"
                    />
                    <label htmlFor="consent" className="text-xs text-slate-400 cursor-pointer">
                      I confirm that meeting / lecture participants are informed of this recording.
                    </label>
                  </div>

                  <button
                    type="submit"
                    disabled={starting || !consent}
                    className="w-full py-2.5 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold text-sm transition-colors flex items-center justify-center space-x-2 shadow-lg shadow-emerald-600/20"
                  >
                    <Play className="w-4 h-4 fill-current" />
                    <span>{starting ? "Starting..." : "Start Lecture Recording"}</span>
                  </button>
                </form>
              )}
            </div>
          )}

          {/* Desktop Computer Quick Launch Card */}
          <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-bold text-white flex items-center space-x-2">
                  <span>Desktop Control</span>
                </h2>
                <p className="text-xs text-slate-400">Tactile desktop application launcher</p>
              </div>
              <Link href="/tools" className="text-xs text-emerald-400 hover:text-emerald-300 font-medium">
                MCP Tools Hub &rarr;
              </Link>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {[
                { id: "obsidian", name: "Obsidian", desc: "Second Brain", icon: FolderOpen, color: "text-purple-400" },
                { id: "code", name: "VS Code", desc: "Editor", icon: FileCode, color: "text-blue-400" },
                { id: "chrome", name: "Chrome", desc: "Browser", icon: ExternalLink, color: "text-emerald-400" },
                { id: "terminal", name: "Terminal", desc: "CLI", icon: Terminal, color: "text-slate-300" },
                { id: "calculator", name: "Calculator", desc: "Math", icon: Command, color: "text-amber-400" },
                { id: "explorer", name: "Explorer", desc: "Files", icon: FolderOpen, color: "text-sky-400" },
              ].map((app) => {
                const Icon = app.icon;
                const status = appStatus[app.id];
                return (
                  <button
                    key={app.id}
                    onClick={() => handleQuickApp(app.id)}
                    className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 hover:border-slate-700 hover:bg-slate-800/40 transition-all text-left group"
                  >
                    <div className="flex items-center justify-between">
                      <Icon className={`w-4 h-4 ${app.color} group-hover:scale-110 transition-transform`} />
                      <span className="text-[10px] font-mono text-slate-500">
                        {status === "launching" ? "..." : status === "opened" ? "✓" : ""}
                      </span>
                    </div>
                    <div className="mt-2">
                      <div className="text-xs font-semibold text-slate-200 group-hover:text-white transition-colors">
                        {app.name}
                      </div>
                      <div className="text-[10px] text-slate-500">{app.desc}</div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>


          {/* Recent Lectures */}
          <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold text-white">Recent Lectures</h2>
              <Link href="/lectures" className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center space-x-1 font-medium">
                <span>View all</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {sessions.length === 0 ? (
              <p className="text-xs text-slate-500 py-4 text-center">No lecture sessions recorded yet.</p>
            ) : (
              <div className="divide-y divide-slate-800/60">
                {sessions.map((s) => (
                  <Link
                    key={s.id}
                    href={`/lectures/${s.id}`}
                    className="py-3 flex items-center justify-between hover:bg-slate-800/30 px-2 rounded-lg transition-colors group"
                  >
                    <div>
                      <div className="text-sm font-semibold text-slate-200 group-hover:text-emerald-400 transition-colors">
                        {s.title}
                      </div>
                      <div className="text-xs text-slate-400 mt-0.5 flex items-center space-x-2">
                        <span>{s.course || "General"}</span>
                        <span>•</span>
                        <span>{new Date(s.started_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                    <span className={`text-[11px] px-2 py-0.5 rounded font-mono ${
                      s.status === "processed"
                        ? "bg-emerald-500/10 text-emerald-400"
                        : s.status === "recording"
                        ? "bg-rose-500/10 text-rose-400 animate-pulse"
                        : "bg-slate-800 text-slate-400"
                    }`}>
                      {s.status}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Col: Coursework Deadlines / Tasks */}
        <div className="space-y-6">
          <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold text-white flex items-center space-x-2">
                <span>Action Items</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">
                  {tasks.length}
                </span>
              </h2>
              <Link href="/tasks" className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center space-x-1 font-medium">
                <span>Kanban</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {tasks.length === 0 ? (
              <div className="text-center py-8">
                <CheckCircle2 className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                <p className="text-xs text-slate-400">All caught up! No pending deadlines detected.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {tasks.map((task) => (
                  <div
                    key={task.id}
                    className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80 hover:border-slate-700 transition-colors space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="font-medium text-xs text-slate-200 leading-snug">
                        {task.title}
                      </div>
                      <button
                        onClick={() => handleCompleteTask(task.id)}
                        title="Mark Done"
                        className="text-slate-500 hover:text-emerald-400 transition-colors shrink-0"
                      >
                        <CheckCircle2 className="w-4 h-4" />
                      </button>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-400">
                      <span className="px-1.5 py-0.5 rounded bg-slate-800/80 text-slate-300">
                        {task.course_name || "General"}
                      </span>
                      {task.due_date && (
                        <span className="flex items-center space-x-1 text-amber-400 font-mono">
                          <Calendar className="w-3 h-3" />
                          <span>{new Date(task.due_date).toLocaleDateString()}</span>
                        </span>
                      )}
                    </div>

                    {task.status === "inbox" && (
                      <div className="text-[10px] text-amber-400/90 bg-amber-500/10 px-2 py-1 rounded border border-amber-500/20">
                        {task.evidence ? `Needs review (quote: "${task.evidence.slice(0, 45)}...")` : "Needs review"}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
