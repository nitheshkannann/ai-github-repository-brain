"use client";

import { useState, useEffect } from "react";
import { loadRepo, LoadRepoResponse, generateRequirements, GenerateRequirementsResponse, generateReadme, GenerateReadmeResponse, compareReadme, CompareReadmeResponse, checkBackendHealth } from "@/lib/api";
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
    Copy,
    FileText,
    X
} from "lucide-react";
import ReactMarkdown from "react-markdown";

interface SidebarProps {
    repoPath: string;
    topK: number;
    onRepoPathChange: (v: string) => void;
    onTopKChange: (v: number) => void;
    isBackendActive: boolean;

    handleLoad: () => void;
    loadLoading: boolean;
    loadResult: LoadRepoResponse | null;
    loadError: string | null;
    showStats: boolean;
    setShowStats: (v: boolean) => void;

    reqLoading: boolean;
    reqResult: GenerateRequirementsResponse | null;
    reqError: string | null;
    showSetup: boolean;
    setShowSetup: (v: boolean) => void;

    readmeError: string | null;
    showReadmeModal: boolean;
    setShowReadmeModal: (v: boolean) => void;
    readmeResult: string | null;

    compareError: string | null;
    showCompareModal: boolean;
    setShowCompareModal: (v: boolean) => void;
    compareResult: CompareReadmeResponse | null;
}

export default function Sidebar({
    repoPath,
    topK,
    onRepoPathChange,
    onTopKChange,
    isBackendActive,
    
    handleLoad,
    loadLoading: loading,
    loadResult: result,
    loadError: error,
    showStats,
    setShowStats,

    reqLoading,
    reqResult,
    reqError,
    showSetup,
    setShowSetup,

    readmeError,
    showReadmeModal,
    setShowReadmeModal,
    readmeResult,

    compareError,
    showCompareModal,
    setShowCompareModal,
    compareResult
}: SidebarProps) {
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

    function handleCopyReadme() {
        if (readmeResult) {
            navigator.clipboard.writeText(readmeResult);
        }
    }

    function handleDownloadReadme() {
        if (!readmeResult) return;
        const blob = new Blob([readmeResult], { type: "text/markdown" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "README.md";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function handleDownloadCompareReadme() {
        if (!compareResult) return;
        const blob = new Blob([compareResult.generated_readme], { type: "text/markdown" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "README_improved.md";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    return (
        <aside className="flex flex-col gap-6 w-full h-full p-6">
            {/* Header */}
            <div className="flex items-center justify-between">
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
            </div>

            {!isBackendActive && (
                <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/20 rounded-lg p-2.5">
                    <AlertCircle size={14} className="text-red-400 shrink-0" />
                    <span className="text-xs font-semibold text-red-400">Backend not running</span>
                </div>
            )}

            <div className="h-px bg-white/5 shrink-0" />

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
                disabled={!isBackendActive || loading || !repoPath.trim()}
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

            {/* Readme Error */}
            {readmeError && (
                <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                    <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
                    <p className="text-xs text-red-300">{readmeError}</p>
                </div>
            )}

            {/* Compare Error */}
            {compareError && (
                <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                    <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
                    <p className="text-xs text-red-300">{compareError}</p>
                </div>
            )}

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
                Powered by Gemini · Keyword-Search
            </div>

            {/* README Modal */}
            {showReadmeModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 sm:p-6 text-white text-left">
                    <div className="bg-slate-900 border border-white/10 rounded-xl shadow-2xl w-full max-w-4xl max-h-full flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                        {/* Header */}
                        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 shrink-0 bg-slate-950/50">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded-lg">
                                    <FileText size={18} />
                                </div>
                                <h2 className="text-lg font-semibold text-slate-100 placeholder-slate-600">Generated README.md</h2>
                            </div>
                            <button
                                onClick={() => setShowReadmeModal(false)}
                                className="text-slate-400 hover:text-white transition-colors bg-white/5 hover:bg-white/10 p-2 rounded-lg"
                                aria-label="Close modal"
                            >
                                <X size={18} />
                            </button>
                        </div>

                        {/* Content Area */}
                        <div className="flex-1 overflow-y-auto p-6 bg-[#0d1117] prose prose-invert prose-emerald max-w-none text-sm leading-relaxed custom-scrollbar">
                            {readmeResult ? (
                                <ReactMarkdown>
                                    {readmeResult}
                                </ReactMarkdown>
                            ) : (
                                <div className="text-center text-slate-500 mt-10">No content generated.</div>
                            )}
                        </div>

                        {/* Footer / Actions */}
                        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/10 shrink-0 bg-slate-950/50">
                            <button
                                onClick={handleCopyReadme}
                                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                            >
                                <Copy size={16} />
                                Copy Markdown
                            </button>
                            <button
                                onClick={handleDownloadReadme}
                                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white transition-colors shadow-lg shadow-blue-500/20"
                            >
                                <Download size={16} />
                                Download README.md
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Compare Readme Modal */}
            {showCompareModal && compareResult && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 sm:p-6 text-white text-left">
                    <div className="bg-slate-900 border border-white/10 rounded-xl shadow-2xl w-full max-w-7xl h-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                        {/* Header */}
                        <div className="flex flex-col border-b border-white/10 shrink-0 bg-slate-950/50">
                            <div className="flex items-center justify-between px-6 py-4">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 bg-purple-500/20 text-purple-400 border border-purple-500/30 rounded-lg">
                                        <FileText size={18} />
                                    </div>
                                    <h2 className="text-lg font-semibold text-slate-100 placeholder-slate-600">README Comparison</h2>
                                </div>
                                <button
                                    onClick={() => setShowCompareModal(false)}
                                    className="text-slate-400 hover:text-white transition-colors bg-white/5 hover:bg-white/10 p-2 rounded-lg"
                                >
                                    <X size={18} />
                                </button>
                            </div>
                            
                            {/* Scoreboard Bar */}
                            <div className="flex items-center justify-between px-6 py-3 bg-slate-900 border-t border-white/5">
                                <div className="flex gap-8 items-center">
                                    <div className="flex flex-col">
                                        <span className="text-xs text-slate-500 uppercase tracking-wider font-semibold">Existing Score</span>
                                        <span className={`text-xl font-bold ${compareResult.analysis.score_existing < 5 ? "text-red-400" : "text-amber-400"}`}>
                                            {compareResult.analysis.score_existing}/10
                                        </span>
                                    </div>
                                    <div className="flex flex-col">
                                        <span className="text-xs text-slate-500 uppercase tracking-wider font-semibold">Generated Score</span>
                                        <span className={`text-xl font-bold ${compareResult.analysis.score_generated > compareResult.analysis.score_existing ? "text-emerald-400" : "text-blue-400"}`}>
                                            {compareResult.analysis.score_generated}/10
                                        </span>
                                    </div>
                                    {compareResult.analysis.score_generated > compareResult.analysis.score_existing && (
                                        <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-3 py-1 rounded-full text-sm font-semibold flex items-center gap-1.5 ml-2">
                                            <span className="text-emerald-500">↑</span>
                                            Improved by +{compareResult.analysis.score_generated - compareResult.analysis.score_existing} points
                                        </div>
                                    )}
                                </div>
                                <div className="text-right">
                                    <span className="text-sm font-medium text-slate-300 italic">
                                        {compareResult.analysis.score_generated > compareResult.analysis.score_existing + 2 ? "Generated README is significantly better" : 
                                         compareResult.analysis.score_generated > compareResult.analysis.score_existing ? "Generated README is improved" : "Both versions are similar in quality"}
                                    </span>
                                </div>
                            </div>
                        </div>

                        {/* Content Area - Side by Side */}
                        <div className="flex flex-1 overflow-hidden">
                            <div className="w-1/2 flex flex-col border-r border-white/10">
                                <div className="bg-slate-800/50 py-2 px-4 text-xs font-semibold text-slate-400 uppercase tracking-wide border-b border-white/5 shrink-0">
                                    Existing README.md
                                </div>
                                <div className="flex-1 overflow-y-auto p-6 bg-[#0d1117] prose prose-invert prose-emerald max-w-none text-sm leading-relaxed custom-scrollbar">
                                    <ReactMarkdown>{compareResult.existing_readme}</ReactMarkdown>
                                </div>
                            </div>
                            <div className="w-1/2 flex flex-col">
                                <div className="bg-slate-800/50 py-2 px-4 text-xs font-semibold text-slate-400 uppercase tracking-wide border-b border-white/5 shrink-0">
                                    Generated README.md
                                </div>
                                <div className="flex-1 overflow-y-auto p-6 bg-[#0d1117] prose prose-invert prose-emerald max-w-none text-sm leading-relaxed custom-scrollbar">
                                    <ReactMarkdown>{compareResult.generated_readme}</ReactMarkdown>
                                </div>
                            </div>
                        </div>
                        
                        {/* Insights & Actions */}
                        <div className="flex flex-col border-t border-white/10 shrink-0 bg-slate-950/50 p-4">
                            <div className="flex gap-6 mb-4">
                                <div className="flex-1">
                                    <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 flex items-center gap-1.5"><AlertCircle size={14} className="text-amber-400"/> Missing Sections Detected</h4>
                                    <ul className="text-sm text-slate-300 space-y-1">
                                        {compareResult.analysis.missing_sections.length > 0 ? 
                                            compareResult.analysis.missing_sections.map((m: string, i: number) => <li key={i} className="flex items-start gap-2 before:content-['•'] before:text-slate-500">{m}</li>) :
                                            <li className="text-emerald-400/80 italic">No missing sections found!</li>
                                        }
                                    </ul>
                                </div>
                                <div className="flex-1">
                                    <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 flex items-center gap-1.5"><CheckCircle2 size={14} className="text-emerald-400"/> Key Improvements</h4>
                                    <ul className="text-sm text-slate-300 space-y-1">
                                        {compareResult.analysis.improvements.length > 0 ? 
                                            compareResult.analysis.improvements.map((m: string, i: number) => <li key={i} className="flex items-start gap-2 before:content-['•'] before:text-slate-500">{m}</li>) :
                                            <li className="text-slate-500 italic">No major improvements noted.</li>
                                        }
                                    </ul>
                                </div>
                            </div>
                            <div className="flex justify-end pt-3 border-t border-white/5">
                                <button
                                    onClick={handleDownloadCompareReadme}
                                    className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-emerald-600 hover:bg-emerald-500 text-white transition-colors shadow-lg shadow-emerald-500/20"
                                >
                                    <Download size={16} />
                                    Download Improved README 🚀
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </aside>
    );
}
