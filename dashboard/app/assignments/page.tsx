"use client";

import React, { useState, useRef } from "react";
import {
  FileText,
  Upload,
  Sparkles,
  BookOpen,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  FileCode,
  ListOrdered,
  Layers,
  GraduationCap
} from "lucide-react";
import {
  analyzeAssignment,
  uploadAssignment,
  AssignmentAnalysis,
  OutlineSection,
  RubricItem,
  LectureCitationRef
} from "@/lib/api";

export default function AssignmentHelperPage() {
  const [mode, setMode] = useState<"text" | "file">("file");
  const [promptText, setPromptText] = useState("");
  const [course, setCourse] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AssignmentAnalysis | null>(null);
  const [copied, setCopied] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Record<number, boolean>>({});

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const f = e.target.files[0];
      const ext = f.name.toLowerCase();
      if (!ext.endsWith(".pdf") && !ext.endsWith(".docx") && !ext.endsWith(".txt") && !ext.endsWith(".md")) {
        setError(`Unsupported file format "${f.name}". Please select a .pdf, .docx, .txt, or .md file.`);
        setSelectedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
        return;
      }
      if (f.size > 20 * 1024 * 1024) {
        setError("File size exceeds 20MB limit.");
        setSelectedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
        return;
      }
      setSelectedFile(f);
      setError(null);
    }
  };

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      let data: AssignmentAnalysis;
      if (mode === "file") {
        if (!selectedFile) {
          setError("Please select a document to upload.");
          setLoading(false);
          return;
        }
        data = await uploadAssignment(selectedFile, course.trim() || undefined);
      } else {
        if (!promptText.trim()) {
          setError("Please enter the assignment prompt or rubric details.");
          setLoading(false);
          return;
        }
        data = await analyzeAssignment(promptText.trim(), course.trim() || undefined);
      }
      setResult(data);
      // Auto-expand all sections
      const exp: Record<number, boolean> = {};
      data.outline_sections.forEach((_, idx) => (exp[idx] = true));
      setExpandedSections(exp);
    } catch (err: any) {
      setError(err.message || "Failed to analyze assignment.");
    } finally {
      setLoading(false);
    }
  };

  const handleCopyDraft = () => {
    if (!result) return;
    const text = `# ${result.title}
${result.course_name ? `Course: ${result.course_name}\n` : ""}
> ${result.academic_integrity_notice}

## Executive Summary
${result.summary}

## Deliverables
${result.deliverables.map((d) => `- [ ] ${d}`).join("\n")}

## Recommended Coursework Outline
${result.outline_sections
  .map(
    (s, idx) =>
      `### ${idx + 1}. ${s.section_title}\n${s.recommended_content.map((c) => `- ${c}`).join("\n")}${
        s.lecture_connection ? `\n*Lecture Link: ${s.lecture_connection}*` : ""
      }`
  )
  .join("\n\n")}

## Draft Overview & Walkthrough
${result.draft_overview}
`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const toggleSection = (idx: number) => {
    setExpandedSections((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  return (
    <div className="flex-1 overflow-y-auto p-8 space-y-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <div className="flex items-center space-x-2 text-emerald-400 font-mono text-xs uppercase tracking-wider mb-1">
            <GraduationCap className="w-4 h-4" />
            <span>Coursework Intelligence</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center space-x-2">
            <span>Assignment Helper & Outliner</span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Analyze assignment rubrics, ground requirements against historical lecture notes, and generate structured study outlines.
          </p>
        </div>
      </div>

      {/* Input Section */}
      <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-6">
        <div className="flex items-center space-x-4 border-b border-slate-800 pb-4">
          <button
            type="button"
            onClick={() => setMode("file")}
            className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              mode === "file"
                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Upload className="w-4 h-4" />
            <span>Upload Document (PDF / DOCX)</span>
          </button>
          <button
            type="button"
            onClick={() => setMode("text")}
            className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              mode === "text"
                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <FileText className="w-4 h-4" />
            <span>Paste Prompt / Rubric Text</span>
          </button>
        </div>

        <form onSubmit={handleAnalyze} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
              Course Name / Code (Optional)
            </label>
            <input
              type="text"
              value={course}
              onChange={(e) => setCourse(e.target.value)}
              placeholder="e.g. IT 312, CS 211, Systems Analysis..."
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition-colors"
            />
          </div>

          {mode === "file" ? (
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                Assignment File (.pdf, .docx, .txt, .md — max 20MB)
              </label>
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-slate-800 hover:border-slate-700 bg-slate-950/60 rounded-xl p-8 text-center cursor-pointer transition-colors"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.docx,.txt,.md"
                  onChange={handleFileChange}
                  className="hidden"
                />
                <Upload className="w-8 h-8 text-slate-500 mx-auto mb-2" />
                {selectedFile ? (
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-emerald-400">{selectedFile.name}</p>
                    <p className="text-xs text-slate-500">
                      {(selectedFile.size / 1024 / 1024).toFixed(2)} MB • Click to change file
                    </p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-slate-300">
                      Click to choose an assignment document or drag & drop here
                    </p>
                    <p className="text-xs text-slate-500">
                      Parsed safely in-memory with pypdf and python-docx
                    </p>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                Assignment Prompt & Rubric Text
              </label>
              <textarea
                rows={6}
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                placeholder="Paste the assignment description, guidelines, deliverables, and rubric here..."
                className="w-full bg-slate-950 border border-slate-800 rounded-xl p-4 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition-colors font-mono"
              />
            </div>
          )}

          {error && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center space-x-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={loading || (mode === "file" ? !selectedFile : !promptText.trim())}
              className="flex items-center space-x-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Sparkles className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              <span>{loading ? "Grounding with Lectures & Outlining..." : "Analyze Coursework"}</span>
            </button>
          </div>
        </form>
      </div>

      {/* Analysis Results View */}
      {result && (
        <div className="space-y-6 animate-fadeIn">
          {/* Academic Integrity Notice Banner */}
          <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-start space-x-3 text-amber-300">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="text-xs space-y-1">
              <span className="font-bold uppercase tracking-wider">Academic Integrity Policy</span>
              <p className="text-amber-200/90 leading-relaxed font-sans">
                {result.academic_integrity_notice}
              </p>
            </div>
          </div>

          {/* Title & Metadata Card */}
          <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                {result.course_name && (
                  <span className="px-2.5 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 text-xs font-mono font-medium border border-emerald-500/20">
                    {result.course_name}
                  </span>
                )}
                <span className="text-xs text-slate-500">Structured Study Outline</span>
              </div>
              <h2 className="text-xl font-bold text-white">{result.title}</h2>
            </div>

            <button
              onClick={handleCopyDraft}
              className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-colors shrink-0"
            >
              {copied ? (
                <>
                  <Check className="w-4 h-4 text-emerald-400" />
                  <span className="text-emerald-400">Copied to Clipboard!</span>
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4" />
                  <span>Copy Markdown Outline</span>
                </>
              )}
            </button>
          </div>

          {/* Executive Summary */}
          <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-2">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center space-x-2">
              <FileCode className="w-4 h-4 text-emerald-400" />
              <span>Assignment Summary</span>
            </h3>
            <p className="text-sm text-slate-200 leading-relaxed">{result.summary}</p>
          </div>

          {/* Deliverables Checklist & Rubric Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Deliverables */}
            <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-3">
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Required Deliverables</span>
              </h3>
              <ul className="space-y-2 text-xs">
                {result.deliverables.map((deliv, idx) => (
                  <li key={idx} className="flex items-start space-x-2.5 text-slate-300">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0 mt-1.5" />
                    <span>{deliv}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Rubric Criteria */}
            <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-3">
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center space-x-2">
                <ListOrdered className="w-4 h-4 text-teal-400" />
                <span>Rubric Expectations</span>
              </h3>
              <div className="space-y-2 text-xs max-h-60 overflow-y-auto pr-1">
                {result.rubric_criteria.map((r, idx) => (
                  <div key={idx} className="p-2.5 rounded-xl bg-slate-950 border border-slate-800/80 space-y-1">
                    <div className="font-semibold text-teal-300">{r.criterion}</div>
                    <div className="text-slate-400 text-[11px] leading-relaxed">{r.expectation}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Suggested Past Lecture Citations */}
          {result.suggested_citations && result.suggested_citations.length > 0 && (
            <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-3">
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center space-x-2">
                <BookOpen className="w-4 h-4 text-purple-400" />
                <span>Grounded Past Lecture Connections</span>
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {result.suggested_citations.map((cite, idx) => (
                  <div key={idx} className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-purple-300 text-xs">{cite.topic}</span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">
                        {cite.citation_label}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">{cite.relevance}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Section-by-Section Coursework Outline */}
          <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-4">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center space-x-2">
              <Layers className="w-4 h-4 text-emerald-400" />
              <span>Section-by-Section Solution Outline</span>
            </h3>

            <div className="space-y-3">
              {result.outline_sections.map((section, idx) => {
                const isExpanded = expandedSections[idx] ?? true;
                return (
                  <div
                    key={idx}
                    className="rounded-xl border border-slate-800 bg-slate-950/60 overflow-hidden"
                  >
                    <div
                      onClick={() => toggleSection(idx)}
                      className="p-3.5 flex items-center justify-between cursor-pointer hover:bg-slate-800/40 transition-colors"
                    >
                      <div className="flex items-center space-x-3">
                        <span className="w-6 h-6 rounded-lg bg-emerald-500/10 text-emerald-400 font-mono text-xs flex items-center justify-center font-bold">
                          {idx + 1}
                        </span>
                        <span className="font-semibold text-sm text-slate-200">
                          {section.section_title}
                        </span>
                      </div>
                      <div className="flex items-center space-x-3">
                        {section.lecture_connection && (
                          <span className="hidden sm:inline-block text-[11px] text-purple-400 font-mono">
                            {section.lecture_connection}
                          </span>
                        )}
                        {isExpanded ? (
                          <ChevronUp className="w-4 h-4 text-slate-400" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-slate-400" />
                        )}
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="px-4 pb-4 pt-1 border-t border-slate-900 space-y-2">
                        <ul className="space-y-1.5 text-xs text-slate-300">
                          {section.recommended_content.map((c, cIdx) => (
                            <li key={cIdx} className="flex items-start space-x-2">
                              <span className="text-emerald-400">•</span>
                              <span className="leading-relaxed">{c}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Draft Walkthrough / Student Revision Guide */}
          <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-3">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-emerald-400" />
              <span>Draft Walkthrough & Student Revision Guide</span>
            </h3>
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 whitespace-pre-wrap leading-relaxed font-sans">
              {result.draft_overview}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
