"use client";

import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useState } from "react";
import { ChevronDown, ChevronUp, FileCode, Hash, Gauge } from "lucide-react";
import { ChunkResult } from "@/lib/api";

interface CodeBlockProps {
    chunk: ChunkResult;
    rank: number;
}

function getLanguage(filePath: string): string {
    const ext = filePath.split(".").pop()?.toLowerCase() || "";
    const map: Record<string, string> = {
        py: "python",
        ts: "typescript",
        tsx: "tsx",
        js: "javascript",
        jsx: "jsx",
        json: "json",
        md: "markdown",
        css: "css",
        html: "html",
        sh: "bash",
        yaml: "yaml",
        yml: "yaml",
        toml: "toml",
        rs: "rust",
        go: "go",
        java: "java",
        c: "c",
        cpp: "cpp",
        cs: "csharp",
        rb: "ruby",
    };
    return map[ext] || "text";
}

export default function CodeBlock({ chunk, rank }: CodeBlockProps) {
    const [expanded, setExpanded] = useState(false);
    const fileName = chunk.file_path.split(/[\\/]/).pop() || chunk.file_path;
    const scoreNum = parseFloat(chunk.score);

    return (
        <div className="rounded-xl border border-white/8 bg-slate-900/70 overflow-hidden transition-all duration-200 hover:border-white/15">
            {/* Header row */}
            <div className="flex items-center justify-between px-4 py-3 bg-slate-800/60 gap-3">
                <div className="flex items-center gap-2 min-w-0">
                    <span className="shrink-0 w-5 h-5 rounded-md bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 text-xs font-bold">
                        {rank}
                    </span>
                    <FileCode size={13} className="shrink-0 text-slate-400" />
                    <span
                        className="text-xs font-mono text-slate-200 truncate"
                        title={chunk.file_path}
                    >
                        {fileName}
                    </span>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                    {/* Score badge */}
                    <div className="hidden sm:flex items-center gap-1 text-xs text-slate-500">
                        <Gauge size={11} />
                        <span className="font-mono">
                            {isNaN(scoreNum) ? chunk.score : scoreNum.toFixed(4)}
                        </span>
                    </div>
                    {/* Chunk id */}
                    <div className="hidden md:flex items-center gap-1 text-xs text-slate-600">
                        <Hash size={11} />
                        <span className="font-mono">{chunk.chunk_id}</span>
                    </div>

                    <button
                        onClick={() => setExpanded(!expanded)}
                        className="flex items-center gap-1 text-xs text-slate-400 hover:text-white transition-colors bg-white/5 hover:bg-white/10 px-2 py-1 rounded-md"
                    >
                        {expanded ? (
                            <>
                                <ChevronUp size={12} /> Hide
                            </>
                        ) : (
                            <>
                                <ChevronDown size={12} /> View
                            </>
                        )}
                    </button>
                </div>
            </div>

            {/* Code body — only shown when expanded */}
            {expanded && (
                <div className="text-xs">
                    <SyntaxHighlighter
                        language={getLanguage(chunk.file_path)}
                        style={vscDarkPlus}
                        customStyle={{
                            margin: 0,
                            padding: "1rem",
                            background: "transparent",
                            fontSize: "0.75rem",
                            lineHeight: "1.6",
                        }}
                        showLineNumbers
                        wrapLongLines
                    >
                        {chunk.content}
                    </SyntaxHighlighter>
                </div>
            )}
        </div>
    );
}
