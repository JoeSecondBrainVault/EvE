"use client";

import React, { useEffect, useState } from "react";
import { 
  CheckSquare, 
  Calendar, 
  Clock, 
  AlertCircle, 
  Plus, 
  CheckCircle2, 
  ArrowRight,
  Filter,
  RefreshCw,
  Sparkles,
  BookOpen
} from "lucide-react";
import { getTasks, updateTaskStatus, syncGoogle, Task } from "@/lib/api";

type ColumnId = "inbox" | "todo" | "doing" | "done";

export default function TasksKanbanPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [courseFilter, setCourseFilter] = useState("all");

  const loadTasks = async () => {
    try {
      const data = await getTasks();
      setTasks(data);
    } catch (err) {
      console.error("Failed to load tasks:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTasks();
  }, []);

  const handleStatusChange = async (taskId: number, newStatus: ColumnId) => {
    try {
      await updateTaskStatus(taskId, newStatus);
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, status: newStatus } : t))
      );
    } catch (err: any) {
      alert("Failed to update status: " + err.message);
    }
  };

  const handleSyncGoogle = async () => {
    setSyncing(true);
    setSyncMsg(null);
    try {
      const res = await syncGoogle("all");
      const c = res.results.classroom?.new_tasks ?? 0;
      const cal = res.results.calendar?.created_events ?? 0;
      setSyncMsg(`Sync complete! +${c} Classroom assignments, +${cal} Calendar events.`);
      await loadTasks();
      setTimeout(() => setSyncMsg(null), 4000);
    } catch (err: any) {
      setSyncMsg(err.message || "Failed to sync Google Classroom & Calendar.");
      setTimeout(() => setSyncMsg(null), 5000);
    } finally {
      setSyncing(false);
    }
  };

  const courses = Array.from(new Set(tasks.map((t) => t.course_name).filter(Boolean))) as string[];

  const filteredTasks = tasks.filter((t) => {
    if (courseFilter === "all") return true;
    return t.course_name === courseFilter;
  });

  const columns: { id: ColumnId; title: string; subtitle: string; color: string }[] = [
    { id: "inbox", title: "Inbox (Review)", subtitle: "Spoken in call — confirm before tracking", color: "border-amber-500/50 text-amber-400" },
    { id: "todo", title: "To Do", subtitle: "Confirmed assignments and coursework", color: "border-sky-500/50 text-sky-400" },
    { id: "doing", title: "In Progress", subtitle: "Currently active assignments", color: "border-purple-500/50 text-purple-400" },
    { id: "done", title: "Done", subtitle: "Completed coursework", color: "border-emerald-500/50 text-emerald-400" },
  ];

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6 flex flex-col h-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-2">
            <CheckSquare className="w-6 h-6 text-emerald-400" />
            <span>Coursework & Deadlines</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Deadlines automatically parsed from lecture transcripts and synced read-only from Google Classroom.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {courses.length > 0 && (
            <div className="flex items-center space-x-2">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={courseFilter}
                onChange={(e) => setCourseFilter(e.target.value)}
                className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-emerald-500"
              >
                <option value="all">All Courses ({tasks.length})</option>
                {courses.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          )}

          <button
            onClick={handleSyncGoogle}
            disabled={syncing}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 text-xs font-medium flex items-center space-x-1.5 transition-colors border border-slate-700"
            title="Sync with Google Classroom & Calendar"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin text-sky-400" : ""}`} />
            <span>{syncing ? "Syncing..." : "Sync Google"}</span>
          </button>
        </div>
      </div>

      {syncMsg && (
        <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-emerald-400 flex items-center justify-between">
          <span>{syncMsg}</span>
          <button onClick={() => setSyncMsg(null)} className="text-slate-400 hover:text-white text-xs">✕</button>
        </div>
      )}

      {/* Kanban Board Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 flex-1 items-start">
        {columns.map((col) => {
          const colTasks = filteredTasks.filter((t) => t.status === col.id);
          return (
            <div
              key={col.id}
              className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 flex flex-col h-full max-h-[calc(100vh-12rem)]"
            >
              <div className="pb-3 border-b border-slate-800/80 mb-3">
                <div className="flex items-center justify-between">
                  <span className={`text-xs font-bold uppercase tracking-wider ${col.color}`}>
                    {col.title}
                  </span>
                  <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 text-[11px] font-mono">
                    {colTasks.length}
                  </span>
                </div>
                <p className="text-[10px] text-slate-500 mt-1">{col.subtitle}</p>
              </div>

              {/* Tasks List */}
              <div className="flex-1 overflow-y-auto space-y-3 pr-1">
                {colTasks.length === 0 ? (
                  <p className="text-center py-8 text-[11px] text-slate-600">No items</p>
                ) : (
                  colTasks.map((t) => (
                    <div
                      key={t.id}
                      className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80 hover:border-slate-700 transition-colors space-y-2.5 shadow-sm"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="font-medium text-xs text-slate-200 leading-snug">
                          {t.title}
                        </div>
                        {t.external_id ? (
                          <span className="shrink-0 px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400 text-[9px] font-mono border border-sky-500/20" title="Imported from Google Classroom">
                            Classroom
                          </span>
                        ) : (
                          <span className="shrink-0 px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 text-[9px] font-mono border border-emerald-500/20" title="Extracted from lecture audio">
                            Lecture
                          </span>
                        )}
                      </div>

                      <div className="flex items-center justify-between text-[11px] text-slate-400">
                        <span className="px-1.5 py-0.5 rounded bg-slate-800/80 text-slate-300">
                          {t.course_name || "General"}
                        </span>
                        {t.due_date && (
                          <span className="flex items-center space-x-1 text-amber-400 font-mono">
                            <Calendar className="w-3 h-3" />
                            <span>{new Date(t.due_date).toLocaleDateString()}</span>
                          </span>
                        )}
                      </div>

                      {t.calendar_event_id && (
                        <div className="flex items-center space-x-1 text-[10px] text-purple-400">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>Synced to E.V.E. Calendar</span>
                        </div>
                      )}

                      {t.evidence && (
                        <div className="text-[10px] text-slate-400 bg-slate-900/60 p-2 rounded border border-slate-800/60 italic">
                          &quot;{t.evidence}&quot;
                        </div>
                      )}

                      {/* Action buttons */}
                      <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
                        {col.id === "inbox" && (
                          <button
                            onClick={() => handleStatusChange(t.id, "todo")}
                            className="px-2 py-1 rounded bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 font-medium transition-colors"
                          >
                            Confirm Task
                          </button>
                        )}

                        {col.id === "todo" && (
                          <button
                            onClick={() => handleStatusChange(t.id, "doing")}
                            className="px-2 py-1 rounded bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 font-medium transition-colors"
                          >
                            Start Doing
                          </button>
                        )}

                        {col.id === "doing" && (
                          <button
                            onClick={() => handleStatusChange(t.id, "done")}
                            className="px-2 py-1 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 font-medium transition-colors"
                          >
                            Mark Done
                          </button>
                        )}

                        {col.id !== "done" && (
                          <button
                            onClick={() => handleStatusChange(t.id, "done")}
                            className="text-slate-500 hover:text-emerald-400 transition-colors ml-auto"
                            title="Directly mark done"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
