"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { 
  BookOpen, 
  Search, 
  Calendar, 
  Clock, 
  FileText, 
  CheckCircle2, 
  AlertCircle,
  Play,
  ArrowRight
} from "lucide-react";
import { getSessions, Session } from "@/lib/api";

export default function LecturesPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [search, setSearch] = useState("");
  const [filterCourse, setFilterCourse] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getSessions()
      .then(setSessions)
      .finally(() => setLoading(false));
  }, []);

  const courses = Array.from(new Set(sessions.map((s) => s.course).filter(Boolean))) as string[];

  const filtered = sessions.filter((s) => {
    const matchesSearch = s.title.toLowerCase().includes(search.toLowerCase()) ||
      (s.course && s.course.toLowerCase().includes(search.toLowerCase()));
    const matchesCourse = filterCourse === "all" || s.course === filterCourse;
    return matchesSearch && matchesCourse;
  });

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-2">
            <BookOpen className="w-6 h-6 text-emerald-400" />
            <span>Lecture Repository</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Browse, search, and review all recorded lectures and synthesized Obsidian study notes.
          </p>
        </div>

        <Link
          href="/live"
          className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs flex items-center space-x-2 transition-colors self-start shadow-lg shadow-emerald-600/20"
        >
          <Play className="w-3.5 h-3.5 fill-current" />
          <span>New Session</span>
        </Link>
      </div>

      {/* Filters Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search lectures by topic or course..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-slate-900 border border-slate-800 text-white placeholder-slate-500 text-xs focus:outline-none focus:border-emerald-500 transition-colors"
          />
        </div>

        {courses.length > 0 && (
          <select
            value={filterCourse}
            onChange={(e) => setFilterCourse(e.target.value)}
            className="px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 text-xs focus:outline-none focus:border-emerald-500"
          >
            <option value="all">All Courses</option>
            {courses.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        )}
      </div>

      {/* Lectures List */}
      {loading ? (
        <div className="text-center py-12 text-xs text-slate-500">Loading lecture archives...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 rounded-2xl bg-slate-900 border border-slate-800">
          <BookOpen className="w-10 h-10 text-slate-600 mx-auto mb-2" />
          <p className="text-sm font-semibold text-slate-300">No lectures found</p>
          <p className="text-xs text-slate-500 mt-1">Start a recording during your next class to build your repository.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((s) => (
            <Link
              key={s.id}
              href={`/lectures/${s.id}`}
              className="p-5 rounded-2xl bg-slate-900 border border-slate-800 hover:border-slate-700 hover:bg-slate-800/40 transition-all flex flex-col justify-between group space-y-4"
            >
              <div>
                <div className="flex items-center justify-between text-[11px] mb-2 font-mono">
                  <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                    {s.course || "General"}
                  </span>
                  <span className={`px-2 py-0.5 rounded font-mono ${
                    s.status === "processed"
                      ? "bg-emerald-500/10 text-emerald-400"
                      : s.status === "recording"
                      ? "bg-rose-500/10 text-rose-400 animate-pulse"
                      : "bg-slate-800 text-slate-400"
                  }`}>
                    {s.status}
                  </span>
                </div>

                <h3 className="text-base font-bold text-white group-hover:text-emerald-400 transition-colors line-clamp-2">
                  {s.title}
                </h3>
              </div>

              <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
                <span className="flex items-center space-x-1">
                  <Calendar className="w-3.5 h-3.5" />
                  <span>{new Date(s.started_at).toLocaleDateString()}</span>
                </span>

                <span className="flex items-center space-x-1 text-emerald-400 group-hover:translate-x-0.5 transition-transform font-medium">
                  <span>Open</span>
                  <ArrowRight className="w-3 h-3" />
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
