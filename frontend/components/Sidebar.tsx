"use client";

import { useState } from "react";
import { loadRepo, LoadRepoResponse } from "@/lib/api";
import {
    FolderOpen,
    RefreshCw,
    CheckCircle2,
    AlertCircle,
    ChevronDown,
    ChevronUp,
    Sliders,
} from "lucide-react";

interface SidebarProps {
    repoPath: string;
    topK: number;
    onRepoPathChange: (v: string) => void;
    onTopKChange: (v: number) => void;
    onRepoLoaded: (info: LoadRepoResponse) => void;
}

export default function Sidebar({
    repoPath,
    topK,
    onRepoPathChange,
    onTopKChange,
    onRepoLoaded,
}: SidebarProps) {
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<LoadRepoResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [showStats, setShowStats] = useState(false);

    async function handleLoad() {
        if (!repoPath.trim()) return;
        setLoading(true);
        setError(null);
        setResult(null);
        try {
            const data = await loadRepo(repoPath.trim());
            setResult(data);
            onRepoLoaded(data);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "Unknown error");
        } finally {
            setLoading(false);
        }
    }

    return (
        <aside className="flex flex-col gap-6 w-full h-full p-6">
            {/* Header */}
            <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-md bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center">
                    <span className="text-emerald-400 text-sm">🧠</span>
                </div>
                <div>
                    <h1 className="text-sm font-semibold text-white leading-none">
                        Repo Brain
                    </h1>
                    <p className="text-xs text-slate-500 mt-0.5">AI Code Explorer</p>
                </div>
            </div>

            <div className="h-px bg-white/5" />

            {/* Repository Path */}
            <div className="flex flex-col gap-2">
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                    <FolderOpen size={12} />
                    Repository Path
                </label>
                <textarea
                    value={repoPath}
                    onChange={(e) => onRepoPathChange(e.target.value)}
                    placeholder="C:\Users\you\my-project"
                    rows={3}
                    className="w-full bg-slate-900 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-slate-200 placeholder-slate-600 resize-none focus:outline-none focus:ring-1 focus:ring-emerald-500/50 focus:border-emerald-500/50 transition-all font-mono"
                />
            </div>

            {/* Top-K Slider */}
            <div className="flex flex-col gap-3">
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wider flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                        <Sliders size={12} />
                        Top-K Results
                    </span>
                    <span className="text-emerald-400 font-mono font-bold bg-emerald-500/10 px-2 py-0.5 rounded-md border border-emerald-500/20">
                        {topK}
                    </span>
                </label>
                <input
                    type="range"
                    min={1}
                    max={10}
                    value={topK}
                    onChange={(e) => onTopKChange(Number(e.target.value))}
                    className="w-full accent-emerald-500 cursor-pointer"
                />
                <div className="flex justify-between text-xs text-slate-600">
                    <span>1</span>
                    <span>5</span>
                    <span>10</span>
                </div>
            </div>

            {/* Load Button */}
            <button
                onClick={handleLoad}
                disabled={loading || !repoPath.trim()}
                className="w-full flex items-center justify-center gap-2 bg-emerald-500 hover:bg-emerald-400 disabled:bg-slate-700 disabled:text-slate-500 text-black disabled:cursor-not-allowed font-semibold text-sm py-2.5 px-4 rounded-lg transition-all duration-200 shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30 active:scale-95"
            >
                {loading ? (
                    <>
                        <RefreshCw size={14} className="animate-spin" />
                        Indexing…
                    </>
                ) : (
                    <>
                        <RefreshCw size={14} />
                        Load Repository
                    </>
                )}
            </button>

            {/* Status */}
            {error && (
                <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                    <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
                    <p className="text-xs text-red-300">{error}</p>
                </div>
            )}

            {result && (
                <div className="flex flex-col gap-2 bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-3">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <CheckCircle2 size={14} className="text-emerald-400" />
                            <span className="text-xs font-medium text-emerald-300">
                                Repository Loaded
                            </span>
                        </div>
                        <button
                            onClick={() => setShowStats(!showStats)}
                            className="text-slate-500 hover:text-slate-300 transition-colors"
                        >
                            {showStats ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </button>
                    </div>

                    {showStats && (
                        <div className="mt-1 grid grid-cols-3 gap-2">
                            {[
                                { label: "Files", value: result.files_found },
                                { label: "Chunks", value: result.chunks_created },
                                { label: "Vectors", value: result.vectors_indexed },
                            ].map((s) => (
                                <div
                                    key={s.label}
                                    className="flex flex-col items-center bg-slate-900/60 rounded-md p-2"
                                >
                                    <span className="text-sm font-bold text-white font-mono">
                                        {s.value}
                                    </span>
                                    <span className="text-xs text-slate-500 mt-0.5">
                                        {s.label}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Footer */}
            <div className="mt-auto text-xs text-slate-700 text-center">
                Powered by Gemini · FAISS
            </div>
        </aside>
    );
}
