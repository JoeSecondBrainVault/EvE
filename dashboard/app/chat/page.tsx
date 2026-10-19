"use client";

import React, { useState } from "react";
import Link from "next/link";
import { 
  MessageSquare, 
  Send, 
  Sparkles, 
  BookOpen, 
  Clock, 
  Play, 
  ArrowRight,
  ExternalLink,
  Bot,
  User as UserIcon
} from "lucide-react";
import { chatRAG, RAGAnswer, Citation } from "@/lib/api";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

function renderMarkdown(text: string) {
  const lines = text.split("\n");
  return lines.map((line, lIdx) => {
    const parts = [];
    const regex = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
    let lastIndex = 0;
    let match;
    let keyIdx = 0;

    while ((match = regex.exec(line)) !== null) {
      if (match.index > lastIndex) {
        parts.push(<span key={keyIdx++}>{line.substring(lastIndex, match.index)}</span>);
      }
      const token = match[0];
      if (token.startsWith("**") && token.endsWith("**")) {
        parts.push(
          <strong key={keyIdx++} className="font-semibold text-white">
            {token.slice(2, -2)}
          </strong>
        );
      } else if (token.startsWith("*") && token.endsWith("*")) {
        parts.push(
          <em key={keyIdx++} className="italic text-slate-300">
            {token.slice(1, -1)}
          </em>
        );
      } else if (token.startsWith("`") && token.endsWith("`")) {
        parts.push(
          <code key={keyIdx++} className="px-1.5 py-0.5 rounded bg-slate-800 text-emerald-400 font-mono text-xs">
            {token.slice(1, -1)}
          </code>
        );
      }
      lastIndex = regex.lastIndex;
    }
    if (lastIndex < line.length) {
      parts.push(<span key={keyIdx++}>{line.substring(lastIndex)}</span>);
    }

    return (
      <p key={lIdx} className={line.trim() === "" ? "h-2" : "mb-1 last:mb-0"}>
        {parts.length > 0 ? parts : "\u00A0"}
      </p>
    );
  });
}

export default function AskEvePage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content: "Hello! I am E.V.E. You can ask me anything about your past recorded lectures. I search your transcripts with hybrid BM25 + vector search and ground every answer with exact audio timestamp citations.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [courseFilter, setCourseFilter] = useState("");

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const query = input.trim();
    if (!query || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: query }]);
    setLoading(true);

    try {
      const res: RAGAnswer = await chatRAG(query, courseFilter || undefined);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          citations: res.citations,
        },
      ]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, I encountered an error while searching your lecture memory: " + err.message,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSuggestion = (text: string) => {
    setInput(text);
  };

  return (
    <div className="flex flex-col h-full bg-slate-950">
      {/* Top Header */}
      <header className="px-8 py-4 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
            <MessageSquare className="w-4 h-4" />
          </div>
          <div>
            <h1 className="text-base font-bold text-white flex items-center space-x-2">
              <span>Ask Your Lectures</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-mono">RAG Hybrid</span>
            </h1>
            <p className="text-[11px] text-slate-400">
              Semantic vector & BM25 keyword search across all transcribed speech.
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <input
            type="text"
            placeholder="Course filter (e.g. IT 222)"
            value={courseFilter}
            onChange={(e) => setCourseFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 w-44"
          />
        </div>
      </header>

      {/* Chat Messages Scroll */}
      <div className="flex-1 overflow-y-auto p-8 space-y-6 max-w-4xl w-full mx-auto">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex items-start space-x-3 ${msg.role === "user" ? "flex-row-reverse space-x-reverse" : ""}`}
          >
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold ${
                msg.role === "user"
                  ? "bg-sky-500 text-slate-950"
                  : "bg-gradient-to-tr from-emerald-500 to-teal-400 text-slate-950"
              }`}
            >
              {msg.role === "user" ? <UserIcon className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
            </div>

            <div
              className={`p-5 rounded-2xl max-w-2xl text-sm leading-relaxed space-y-3 ${
                msg.role === "user"
                  ? "bg-sky-600 text-white rounded-tr-none"
                  : "bg-slate-900 border border-slate-800 text-slate-200 rounded-tl-none shadow-sm"
              }`}
            >
              {msg.role === "user" ? (
                <div className="whitespace-pre-wrap">{msg.content}</div>
              ) : (
                <div className="leading-relaxed">{renderMarkdown(msg.content)}</div>
              )}

              {/* Citations Box */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="pt-3 border-t border-slate-800 space-y-2">
                  <div className="text-[11px] font-semibold text-slate-400 flex items-center space-x-1.5">
                    <Sparkles className="w-3 h-3 text-emerald-400" />
                    <span>Citations & Timestamp Playback:</span>
                  </div>

                  <div className="grid grid-cols-1 gap-2">
                    {msg.citations.map((c, cIdx) => (
                      <Link
                        key={cIdx}
                        href={`/lectures/${c.session_id}`}
                        className="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80 hover:border-slate-700 hover:bg-slate-800/40 transition-colors flex items-center justify-between text-xs group"
                      >
                        <div className="space-y-0.5">
                          <div className="font-semibold text-slate-200 group-hover:text-emerald-400 flex items-center space-x-1.5">
                            <span>{c.course_name || "General"}</span>
                            <span>•</span>
                            <span className="font-mono text-emerald-400">[{c.timestamp_label}]</span>
                          </div>
                          <p className="text-[11px] text-slate-400 line-clamp-1 italic">
                            "{c.snippet}"
                          </p>
                        </div>

                        <ExternalLink className="w-3.5 h-3.5 text-slate-500 group-hover:text-white shrink-0 ml-2" />
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex items-center space-x-3 text-slate-400 text-xs py-2">
            <Bot className="w-6 h-6 animate-spin text-emerald-400" />
            <span>Searching transcripts and synthesizing answer...</span>
          </div>
        )}
      </div>

      {/* Suggested Prompts */}
      <div className="px-8 pb-3 max-w-4xl w-full mx-auto flex flex-wrap gap-2 text-xs">
        <button
          onClick={() => handleSuggestion("What did the instructor say about subnetting and CIDR?")}
          className="px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 transition-colors"
        >
          Subnetting & CIDR
        </button>
        <button
          onClick={() => handleSuggestion("Are there any upcoming assignments or lab deadlines mentioned?")}
          className="px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 transition-colors"
        >
          Upcoming deadlines
        </button>
        <button
          onClick={() => handleSuggestion("Explain the difference between network bits and host bits.")}
          className="px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 transition-colors"
        >
          Network vs Host bits
        </button>
      </div>

      {/* Input Form */}
      <div className="p-6 border-t border-slate-800 bg-slate-900/60">
        <form onSubmit={handleSend} className="max-w-4xl w-full mx-auto relative flex items-center">
          <input
            type="text"
            placeholder="Ask a question about your lectures (e.g. 'What is the formula for usable IP addresses?')..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
            className="w-full pl-4 pr-12 py-3 rounded-xl bg-slate-950 border border-slate-800 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-emerald-500 transition-colors shadow-inner"
          />

          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="absolute right-2 p-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-30 text-white transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
