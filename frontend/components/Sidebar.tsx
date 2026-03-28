"use client";

import { useState } from "react";
import { loadRepo, LoadRepoResponse, generateRequirements, GenerateRequirementsResponse } from "@/lib/api";
import {
    FolderOpen,
    RefreshCw,
    CheckCircle2,
    AlertCircle,
    ChevronDown,
    ChevronUp,
    Sliders,
    Box,
    Download,
    Terminal,
    Copy
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

    const [reqLoading, setReqLoading] = useState(false);
    const [reqResult, setReqResult] = useState<GenerateRequirementsResponse | null>(null);
    const [reqError, setReqError] = useState<string | null>(null);
    const [showSetup, setShowSetup] = useState(false);

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

    async function handleGenerateRequirements() {
        if (!repoPath.trim()) return;
        setReqLoading(true);
        setReqError(null);
        setReqResult(null);
        try {
            const data = await generateRequirements(repoPath.trim());
            setReqResult(data);
        } catch (e: unknown) {
            setReqError(e instanceof Error ? e.message : "Unknown error");
        } finally {
            setReqLoading(false);
        }
    }

    function handleDownloadReqs() {
        if (!reqResult) return;
        
        const lines: string[] = [];
        if (reqResult.python.length > 0) {
            lines.push("# Python");
            reqResult.python.forEach(d => lines.push(d));
            lines.push("");
        }
        if (reqResult.javascript.length > 0) {
            lines.push("# JavaScript");
            reqResult.javascript.forEach(d => lines.push(d));
            lines.push("");
        }
        
        const text = lines.join("\n").trim() + "\n";
        const blob = new Blob([text], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "requirements.txt";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function generateSetupText() {
        if (!reqResult) return "";
        const lines: string[] = [];
        
        if (reqResult.python.length > 0) {
            lines.push("# Python Setup");
            lines.push(`pip install ${reqResult.python.join(" ")}`);
            if (reqResult.entry_points && reqResult.entry_points.python) {
                lines.push(`python ${reqResult.entry_points.python}`);
            }
            lines.push("");
        }
        
        if (reqResult.javascript.length > 0) {
            lines.push("# JavaScript Setup");
            lines.push(`npm install ${reqResult.javascript.join(" ")}`);
            if (reqResult.entry_points && reqResult.entry_points.javascript) {
                lines.push(reqResult.entry_points.javascript);
            }
            lines.push("");
        }
        
        return lines.join("\n").trim();
    }

    function handleCopySetup() {
        const text = generateSetupText();
        if (text) {
            navigator.clipboard.writeText(text);
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

            {/* Generate Button Group */}
            <div className="flex gap-2 w-full mt-[-10px]">
                <button
                    onClick={() => { setShowSetup(false); handleGenerateRequirements(); }}
                    disabled={reqLoading || !repoPath.trim()}
                    className="flex-1 flex items-center justify-center gap-1.5 bg-slate-800 hover:bg-slate-700 disabled:bg-slate-800/50 border border-slate-700 text-slate-200 text-xs py-2 rounded-lg transition-colors active:scale-95"
                >
                    {reqLoading && !showSetup ? <RefreshCw size={12} className="animate-spin" /> : <Box size={12} />}
                    Dependencies
                </button>
                <button
                    onClick={() => { setShowSetup(true); handleGenerateRequirements(); }}
                    disabled={reqLoading || !repoPath.trim()}
                    className="flex-1 flex items-center justify-center gap-1.5 bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/30 text-indigo-300 text-xs py-2 rounded-lg transition-colors active:scale-95"
                >
                    {reqLoading && showSetup ? <RefreshCw size={12} className="animate-spin" /> : <Terminal size={12} />}
                    Setup Guide
                </button>
            </div>

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

            {/* Req Status */}
            {reqError && (
                <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                    <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
                    <p className="text-xs text-red-300">{reqError}</p>
                </div>
            )}

            {reqResult && (
                <div className="flex flex-col max-h-80 flex-shrink-0 gap-2 bg-slate-800/50 border border-slate-700 rounded-lg p-3">
                    <div className="flex items-center justify-between shrink-0 border-b border-slate-700/50 pb-2">
                        <div className="flex gap-4">
                            <button onClick={() => setShowSetup(false)} className={`text-xs font-semibold transition-colors ${!showSetup ? "text-emerald-400" : "text-slate-500 hover:text-slate-300"}`}>Dependencies</button>
                            <button onClick={() => setShowSetup(true)} className={`text-xs font-semibold transition-colors ${showSetup ? "text-indigo-400" : "text-slate-500 hover:text-slate-300"}`}>Setup Guide</button>
                        </div>
                    </div>
                    
                    {!showSetup ? (
                        <>
                            <div className="mt-1 bg-slate-900 rounded p-2 overflow-y-auto flex-grow min-h-0 border border-slate-700/50">
                                {reqResult.python.length === 0 && reqResult.javascript.length === 0 ? (
                                    <p className="text-xs text-slate-500 italic">No dependencies found.</p>
                                ) : (
                                    <div className="flex flex-col gap-3">
                                        {reqResult.python.length > 0 && (
                                            <div>
                                                <p className="text-xs font-semibold text-emerald-400 mb-1">Python Dependencies</p>
                                                <ul className="flex flex-col gap-1">
                                                    {reqResult.python.map((dep, i) => (
                                                        <li key={`py-${i}`} className="text-xs font-mono text-slate-400 flex items-center gap-2 before:content-['•'] before:text-slate-600">
                                                            {dep}
                                                        </li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                        {reqResult.javascript.length > 0 && (
                                            <div>
                                                <p className="text-xs font-semibold text-emerald-400 mb-1">JavaScript Dependencies</p>
                                                <ul className="flex flex-col gap-1">
                                                    {reqResult.javascript.map((dep, i) => (
                                                        <li key={`js-${i}`} className="text-xs font-mono text-slate-400 flex items-center gap-2 before:content-['•'] before:text-slate-600">
                                                            {dep}
                                                        </li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                    </div>
                                )}
                                <p className="text-[10px] text-slate-500 mt-2 border-t border-slate-800 pt-2">
                                    Source: {reqResult.source}
                                </p>
                            </div>

                            <button
                                onClick={handleDownloadReqs}
                                className="mt-auto shrink-0 w-full flex items-center justify-center gap-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs py-1.5 rounded transition-colors"
                            >
                                <Download size={12} />
                                Download requirements.txt
                            </button>
                        </>
                    ) : (
                        <>
                            <div className="mt-1 bg-slate-900 rounded p-3 overflow-y-auto flex-grow min-h-0 border border-slate-700/50">
                                <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap leading-relaxed">
                                    {generateSetupText() || <span className="text-slate-500 italic">No instructions available.</span>}
                                </pre>
                            </div>

                            <button
                                onClick={handleCopySetup}
                                className="mt-auto shrink-0 w-full flex items-center justify-center gap-1.5 bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/30 text-indigo-300 text-xs py-1.5 rounded transition-colors"
                            >
                                <Copy size={12} />
                                Copy Install Commands
                            </button>
                        </>
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
