"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  Radio, 
  BookOpen, 
  CheckSquare, 
  MessageSquare, 
  Settings as SettingsIcon, 
  Home,
  Mic,
  Cpu,
  Sparkles,
  GraduationCap,
  Terminal
} from "lucide-react";
import { getStatus, SystemStatus } from "@/lib/api";

export default function Navbar() {
  const pathname = usePathname();
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    let mounted = true;
    const fetchStatus = async () => {
      try {
        const s = await getStatus();
        if (mounted) setStatus(s);
      } catch {
        // Backend might be offline
      }
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const navItems = [
    { name: "Overview", href: "/", icon: Home },
    { name: "Live Captions", href: "/live", icon: Radio },
    { name: "Lectures", href: "/lectures", icon: BookOpen },
    { name: "Coursework", href: "/tasks", icon: CheckSquare },
    { name: "Assignments", href: "/assignments", icon: GraduationCap },
    { name: "Tools & MCP", href: "/tools", icon: Terminal },
    { name: "Ask E.V.E.", href: "/chat", icon: MessageSquare },
    { name: "Settings", href: "/settings", icon: SettingsIcon },
  ];


  const isRecording = Boolean(status?.active_session_id);

  return (
    <aside className="w-64 bg-slate-900 text-slate-100 flex flex-col border-r border-slate-800 shrink-0 select-none">
      {/* Brand Header */}
      <div className="p-6 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center font-bold text-slate-950 text-lg shadow-lg shadow-emerald-500/20">
            E
          </div>
          <div>
            <div className="font-bold text-base tracking-wide flex items-center space-x-1.5">
              <span>E.V.E.</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-mono border border-emerald-500/20">v0.1</span>
            </div>
            <div className="text-xs text-slate-400 font-medium">Study & Work Assistant</div>
          </div>
        </div>
      </div>

      {/* Live Recording Indicator */}
      {isRecording && (
        <div className="mx-4 mt-4 px-3 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse" />
            <span className="text-xs font-semibold text-rose-300 uppercase tracking-wider">Recording</span>
          </div>
          <Link href="/live" className="text-xs text-rose-400 hover:text-rose-200 underline font-medium">
            View Live
          </Link>
        </div>
      )}

      {/* Navigation Links */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center space-x-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-emerald-500/10 text-emerald-400 font-semibold border border-emerald-500/20 shadow-sm"
                  : "text-slate-300 hover:bg-slate-800/60 hover:text-white"
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? "text-emerald-400" : "text-slate-400"}`} />
              <span>{item.name}</span>
            </Link>
          );
        })}
      </nav>

      {/* System Hardware & Model Status Footnote */}
      <div className="p-4 border-t border-slate-800 bg-slate-950/40 text-xs space-y-2">
        <div className="flex items-center justify-between text-slate-400">
          <span className="flex items-center space-x-1.5">
            <Cpu className="w-3.5 h-3.5 text-slate-400" />
            <span>STT Model:</span>
          </span>
          <span className={`font-mono text-[11px] px-1.5 py-0.5 rounded ${
            status?.model === "ready" ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
          }`}>
            {status?.model || "Connecting..."}
          </span>
        </div>

        <div className="flex items-center justify-between text-slate-400">
          <span className="flex items-center space-x-1.5">
            <Sparkles className="w-3.5 h-3.5 text-teal-400" />
            <span>Intelligence:</span>
          </span>
          <span className="text-[11px] font-medium text-slate-300">
            {status?.has_cloud_llm ? "Gemini 2.5 Flash" : "Local Ollama 7B"}
          </span>
        </div>
      </div>
    </aside>
  );
}
