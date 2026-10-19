"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { 
  ArrowLeft, 
  Volume2, 
  FileText, 
  Layers, 
  HelpCircle, 
  Play, 
  Pause, 
  RotateCcw, 
  CheckCircle2, 
  XCircle, 
  Sparkles,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  BookOpen
} from "lucide-react";
import { 
  getSession, 
  getSessionNote, 
  getSessionFlashcards, 
  getSessionQuiz, 
  processSession, 
  getAudioUrl,
  Session, 
  Segment, 
  Note, 
  Flashcard, 
  QuizItem 
} from "@/lib/api";

export default function LectureDetailPage() {
  const params = useParams();
  const sessionId = Number(params.id);

  const [session, setSession] = useState<(Session & { segments: Segment[] }) | null>(null);
  const [note, setNote] = useState<Note | null>(null);
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);
  const [quizzes, setQuizzes] = useState<QuizItem[]>([]);
  const [activeTab, setActiveTab] = useState<"transcript" | "note" | "flashcards" | "quiz">("transcript");
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);

  // Audio Player State
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [audioSource, setAudioSource] = useState<"them" | "me">("them");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Flashcards state
  const [currentCardIdx, setCurrentCardIdx] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);

  // Quiz state
  const [selectedAnswers, setSelectedAnswers] = useState<Record<number, number>>({});
  const [submittedQuiz, setSubmittedQuiz] = useState(false);

  const loadData = async () => {
    try {
      const s = await getSession(sessionId);
      setSession(s);

      const [n, fc, q] = await Promise.all([
        getSessionNote(sessionId).catch(() => null),
        getSessionFlashcards(sessionId).catch(() => []),
        getSessionQuiz(sessionId).catch(() => []),
      ]);
      setNote(n);
      setFlashcards(fc);
      setQuizzes(q);
    } catch (err) {
      console.error("Error loading session:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isNaN(sessionId) || sessionId <= 0) {
      setLoading(false);
      return;
    }
    loadData();
  }, [sessionId]);

  const handleProcess = async () => {
    setProcessing(true);
    try {
      await processSession(sessionId);
      await loadData();
      setActiveTab("note");
    } catch (err: any) {
      alert("Processing failed: " + err.message);
    } finally {
      setProcessing(false);
    }
  };

  // Click-to-play audio citation seek
  const seekToTime = (seconds: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = seconds;
      audioRef.current.play().catch(() => {});
      setIsPlaying(true);
    }
  };

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play().catch(() => {});
      setIsPlaying(true);
    }
  };

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  if (loading) {
    return <div className="p-8 text-center text-xs text-slate-500">Loading lecture details...</div>;
  }

  if (!session) {
    return (
      <div className="p-8 max-w-xl mx-auto text-center space-y-4">
        <p className="text-sm font-semibold text-white">Lecture not found</p>
        <Link href="/lectures" className="text-xs text-emerald-400 hover:underline">
          Return to Lectures
        </Link>
      </div>
    );
  }

  const currentFlashcard = flashcards[currentCardIdx];

  return (
    <div className="flex flex-col h-full bg-slate-950">
      {/* Top Header */}
      <div className="px-8 py-5 border-b border-slate-800 bg-slate-900/40">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <Link href="/lectures" className="text-xs text-slate-400 hover:text-white flex items-center space-x-1.5 transition-colors">
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Lectures</span>
            </Link>
            <h1 className="text-xl font-bold text-white flex items-center space-x-2">
              <span>{session.title}</span>
            </h1>
            <div className="flex items-center space-x-3 text-xs text-slate-400">
              <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-medium">
                {session.course || "General Coursework"}
              </span>
              <span>•</span>
              <span>{new Date(session.started_at).toLocaleString()}</span>
              {note && (
                <>
                  <span>•</span>
                  <span className="text-emerald-400 flex items-center space-x-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Saved in Obsidian</span>
                  </span>
                </>
              )}
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {!note && (
              <button
                onClick={handleProcess}
                disabled={processing}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center space-x-2 shadow-lg shadow-emerald-600/20 transition-colors"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>{processing ? "Synthesizing..." : "Generate Notes & Flashcards"}</span>
              </button>
            )}
          </div>
        </div>

        {/* Audio Player Bar */}
        <div className="mt-4 p-3 rounded-xl bg-slate-900 border border-slate-800 flex items-center space-x-4">
          <button
            onClick={togglePlay}
            className="w-9 h-9 rounded-full bg-emerald-500 text-slate-950 flex items-center justify-center hover:bg-emerald-400 transition-colors shrink-0"
          >
            {isPlaying ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current ml-0.5" />}
          </button>

          <div className="flex-1 space-y-1">
            <input
              type="range"
              min={0}
              max={duration || 100}
              value={currentTime}
              onChange={(e) => {
                const val = Number(e.target.value);
                setCurrentTime(val);
                if (audioRef.current) audioRef.current.currentTime = val;
              }}
              className="w-full h-1.5 rounded-lg appearance-none bg-slate-800 accent-emerald-500 cursor-pointer"
            />
            <div className="flex justify-between text-[11px] text-slate-500 font-mono">
              <span>{formatTime(currentTime)}</span>
              <span>{formatTime(duration)}</span>
            </div>
          </div>

          {/* Hidden HTML Audio Tag */}
          <audio
            ref={audioRef}
            src={getAudioUrl(session.id, audioSource)}
            onTimeUpdate={() => audioRef.current && setCurrentTime(audioRef.current.currentTime)}
            onLoadedMetadata={() => audioRef.current && setDuration(audioRef.current.duration)}
            onEnded={() => setIsPlaying(false)}
          />

          <div className="flex bg-slate-800/80 rounded-lg p-0.5 text-xs">
            <button
              onClick={() => setAudioSource("them")}
              className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                audioSource === "them" ? "bg-slate-700 text-emerald-400" : "text-slate-400"
              }`}
            >
              Speaker
            </button>
            <button
              onClick={() => setAudioSource("me")}
              className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                audioSource === "me" ? "bg-slate-700 text-sky-400" : "text-slate-400"
              }`}
            >
              Mic
            </button>
          </div>
        </div>

        {/* Tab Selector */}
        <div className="flex space-x-6 mt-4 text-xs font-semibold border-b border-slate-800">
          <button
            onClick={() => setActiveTab("transcript")}
            className={`pb-3 transition-colors flex items-center space-x-2 border-b-2 ${
              activeTab === "transcript" ? "border-emerald-500 text-emerald-400" : "border-transparent text-slate-400 hover:text-white"
            }`}
          >
            <Volume2 className="w-3.5 h-3.5" />
            <span>Transcript ({session.segments.length})</span>
          </button>

          <button
            onClick={() => setActiveTab("note")}
            className={`pb-3 transition-colors flex items-center space-x-2 border-b-2 ${
              activeTab === "note" ? "border-emerald-500 text-emerald-400" : "border-transparent text-slate-400 hover:text-white"
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Obsidian Notes</span>
          </button>

          <button
            onClick={() => setActiveTab("flashcards")}
            className={`pb-3 transition-colors flex items-center space-x-2 border-b-2 ${
              activeTab === "flashcards" ? "border-emerald-500 text-emerald-400" : "border-transparent text-slate-400 hover:text-white"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Flashcards ({flashcards.length})</span>
          </button>

          <button
            onClick={() => setActiveTab("quiz")}
            className={`pb-3 transition-colors flex items-center space-x-2 border-b-2 ${
              activeTab === "quiz" ? "border-emerald-500 text-emerald-400" : "border-transparent text-slate-400 hover:text-white"
            }`}
          >
            <HelpCircle className="w-3.5 h-3.5" />
            <span>Self-Test Quiz ({quizzes.length})</span>
          </button>
        </div>
      </div>

      {/* Tab Contents */}
      <div className="flex-1 overflow-y-auto p-8 max-w-4xl w-full mx-auto">
        {/* 1. Transcript Tab */}
        {activeTab === "transcript" && (
          <div className="space-y-3">
            {session.segments.length === 0 ? (
              <p className="text-center py-12 text-xs text-slate-500">No transcribed segments for this lecture.</p>
            ) : (
              session.segments.map((seg) => {
                const isSpeaker = seg.source === "them";
                return (
                  <div
                    key={seg.id}
                    className="p-3.5 rounded-xl bg-slate-900 border border-slate-800/80 hover:border-slate-700 transition-colors flex items-start space-x-3 group"
                  >
                    <button
                      onClick={() => seekToTime(seg.t0)}
                      className="px-2 py-1 rounded bg-slate-800 text-emerald-400 hover:bg-emerald-500 hover:text-slate-950 text-[11px] font-mono shrink-0 transition-colors flex items-center space-x-1"
                      title="Click to play from this moment"
                    >
                      <Play className="w-2.5 h-2.5 fill-current" />
                      <span>{formatTime(seg.t0)}</span>
                    </button>

                    <div className="flex-1">
                      <div className="text-[11px] font-semibold text-slate-400 mb-1 flex items-center space-x-1.5">
                        <span className={isSpeaker ? "text-emerald-400" : "text-sky-400"}>
                          {isSpeaker ? "Instructor / Call" : "You (Microphone)"}
                        </span>
                      </div>
                      <p className="text-sm text-slate-200 leading-relaxed">{seg.text}</p>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* 2. Obsidian Notes Tab */}
        {activeTab === "note" && (
          <div className="space-y-6">
            {!note ? (
              <div className="p-8 text-center rounded-2xl bg-slate-900 border border-slate-800 space-y-3">
                <p className="text-sm font-semibold text-white">No synthesized note yet</p>
                <button
                  onClick={handleProcess}
                  disabled={processing}
                  className="px-4 py-2 rounded-lg bg-emerald-600 text-white font-medium text-xs hover:bg-emerald-500 transition-colors"
                >
                  Generate Obsidian Notes Now
                </button>
              </div>
            ) : (
              <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-6">
                <div>
                  <h2 className="text-xl font-bold text-white">{note.title}</h2>
                  <p className="text-xs text-slate-400 mt-1 font-mono">Vault Path: {note.vault_path}</p>
                </div>

                <div className="space-y-2">
                  <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Executive Summary</h3>
                  <p className="text-sm text-slate-200 leading-relaxed bg-slate-950 p-4 rounded-xl border border-slate-800">
                    {note.summary}
                  </p>
                </div>

                {note.key_takeaways.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Key Takeaways</h3>
                    <ul className="space-y-2">
                      {note.key_takeaways.map((item, i) => (
                        <li key={i} className="flex items-start space-x-2 text-sm text-slate-200">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-2 shrink-0" />
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {note.glossary.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Glossary & Technical Terms</h3>
                    <div className="divide-y divide-slate-800 bg-slate-950 rounded-xl border border-slate-800 overflow-hidden">
                      {note.glossary.map((g, i) => (
                        <div key={i} className="p-3 text-xs">
                          <span className="font-bold text-emerald-400 font-mono">{g.term}: </span>
                          <span className="text-slate-300">{g.definition}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* 3. Flashcards Study Mode */}
        {activeTab === "flashcards" && (
          <div className="space-y-6 max-w-xl mx-auto">
            {flashcards.length === 0 ? (
              <p className="text-center py-12 text-xs text-slate-500">No flashcards generated yet.</p>
            ) : (
              <>
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>Card {currentCardIdx + 1} of {flashcards.length}</span>
                  {currentFlashcard?.topic && (
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      {currentFlashcard.topic}
                    </span>
                  )}
                </div>

                {/* Flip Card Component */}
                <div
                  onClick={() => setIsFlipped(!isFlipped)}
                  className="h-64 rounded-2xl bg-gradient-to-br from-slate-900 to-slate-850 border border-slate-800 p-8 flex flex-col justify-between cursor-pointer select-none shadow-xl hover:border-slate-700 transition-all text-center"
                >
                  <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">
                    {isFlipped ? "Answer" : "Question (Click to flip)"}
                  </div>

                  <div className="text-lg font-bold text-white flex-1 flex items-center justify-center px-4">
                    {isFlipped ? currentFlashcard.back : currentFlashcard.front}
                  </div>

                  <div className="text-[11px] text-slate-500">
                    Click anywhere to reveal {isFlipped ? "front" : "answer"}
                  </div>
                </div>

                {/* Controls */}
                <div className="flex items-center justify-between">
                  <button
                    disabled={currentCardIdx === 0}
                    onClick={() => {
                      setIsFlipped(false);
                      setCurrentCardIdx((prev) => prev - 1);
                    }}
                    className="px-4 py-2 rounded-lg bg-slate-800 text-white font-medium text-xs disabled:opacity-40 flex items-center space-x-1"
                  >
                    <ChevronLeft className="w-4 h-4" />
                    <span>Previous</span>
                  </button>

                  <button
                    disabled={currentCardIdx === flashcards.length - 1}
                    onClick={() => {
                      setIsFlipped(false);
                      setCurrentCardIdx((prev) => prev + 1);
                    }}
                    className="px-4 py-2 rounded-lg bg-slate-800 text-white font-medium text-xs disabled:opacity-40 flex items-center space-x-1"
                  >
                    <span>Next</span>
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* 4. Quiz Tab */}
        {activeTab === "quiz" && (
          <div className="space-y-6">
            {quizzes.length === 0 ? (
              <p className="text-center py-12 text-xs text-slate-500">No quiz questions generated yet.</p>
            ) : (
              <div className="space-y-6">
                {quizzes.map((q, idx) => {
                  const selectedOpt = selectedAnswers[idx];
                  return (
                    <div key={q.id} className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
                      <div className="font-semibold text-sm text-white">
                        <span className="text-emerald-400 font-mono mr-2">{idx + 1}.</span>
                        {q.question}
                      </div>

                      <div className="space-y-2">
                        {q.options.map((opt, optIdx) => {
                          const isSelected = selectedOpt === optIdx;
                          const isCorrect = q.correct_index === optIdx;
                          let btnStyle = "bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-700";

                          if (submittedQuiz) {
                            if (isCorrect) {
                              btnStyle = "bg-emerald-500/10 border-emerald-500 text-emerald-400 font-semibold";
                            } else if (isSelected && !isCorrect) {
                              btnStyle = "bg-rose-500/10 border-rose-500 text-rose-400";
                            }
                          } else if (isSelected) {
                            btnStyle = "bg-emerald-500/10 border-emerald-500 text-emerald-400 font-medium";
                          }

                          return (
                            <button
                              key={optIdx}
                              onClick={() => {
                                if (!submittedQuiz) {
                                  setSelectedAnswers((prev) => ({ ...prev, [idx]: optIdx }));
                                }
                              }}
                              className={`w-full p-3 rounded-xl border text-xs text-left transition-colors flex items-center justify-between ${btnStyle}`}
                            >
                              <span>{opt}</span>
                              {submittedQuiz && isCorrect && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
                              {submittedQuiz && isSelected && !isCorrect && <XCircle className="w-4 h-4 text-rose-400" />}
                            </button>
                          );
                        })}
                      </div>

                      {submittedQuiz && (
                        <div className="p-3 rounded-lg bg-slate-950 text-xs text-slate-300 border border-slate-800">
                          <span className="font-bold text-slate-400">Explanation: </span>
                          {q.explanation}
                        </div>
                      )}
                    </div>
                  );
                })}

                <div className="pt-4 flex justify-end">
                  <button
                    onClick={() => setSubmittedQuiz(!submittedQuiz)}
                    className="px-6 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-colors shadow-lg shadow-emerald-600/20"
                  >
                    {submittedQuiz ? "Reset Quiz" : "Submit Answers"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
