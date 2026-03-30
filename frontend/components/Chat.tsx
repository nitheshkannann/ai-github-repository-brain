"use client";

import { useState, useRef, useEffect } from "react";
import { askQuestion, AskResponse, ChunkResult } from "@/lib/api";
import CodeBlock from "./CodeBlock";
import ReactMarkdown from "react-markdown";
import { Send, Bot, User, Sparkles, Layers } from "lucide-react";
import FloatingActionMenu from "./FloatingActionMenu";

interface Message {
    role: "user" | "assistant";
    text: string;
    chunks?: ChunkResult[];
    error?: boolean;
}

interface ChatProps {
    topK: number;
    repoLoaded: boolean;
    isBackendActive: boolean;
    onLoadRepository: () => void;
    onGenerateRequirements: () => void;
    onSetupGuide: () => void;
    onGenerateReadme: () => void;
    onCompareReadme: () => void;
    actionStatus: string | null;
}

const WELCOME = `Welcome! I'm your **AI Codebase Assistant**.

Load a repository using the sidebar, then ask me anything about the code — like:

- *"How does the chunking logic work?"*
- *"What does the embedder module do?"*
- *"Explain the retrieval pipeline."*`;

export default function Chat({ 
    topK, 
    repoLoaded, 
    isBackendActive,
    onLoadRepository,
    onGenerateRequirements,
    onSetupGuide,
    onGenerateReadme,
    onCompareReadme,
    actionStatus
}: ChatProps) {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const bottomRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, loading]);

    async function handleSubmit() {
        const question = input.trim();
        if (!question || loading || !repoLoaded) return;

        setInput("");
        setMessages((prev) => [...prev, { role: "user", text: question }]);
        setLoading(true);

        try {
            const data: AskResponse = await askQuestion(question, topK);
            setMessages((prev) => [
                ...prev,
                {
                    role: "assistant",
                    text: data.explanation,
                    chunks: data.retrieved_chunks,
                },
            ]);
        } catch (e: unknown) {
            setMessages((prev) => [
                ...prev,
                {
                    role: "assistant",
                    text: e instanceof Error ? e.message : "An error occurred.",
                    error: true,
                },
            ]);
        } finally {
            setLoading(false);
        }
    }

    function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    }

    // Auto-resize textarea
    function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
        setInput(e.target.value);
        const el = textareaRef.current;
        if (el) {
            el.style.height = "auto";
            el.style.height = Math.min(el.scrollHeight, 160) + "px";
        }
    }

    function handleActionMenu(action: "load" | "dependencies" | "setup" | "readme" | "compare") {
        switch(action) {
            case "load": onLoadRepository(); break;
            case "dependencies": onGenerateRequirements(); break;
            case "setup": onSetupGuide(); break;
            case "readme": onGenerateReadme(); break;
            case "compare": onCompareReadme(); break;
        }
    }

    return (
        <div className="flex flex-col h-full">
            {/* Messages area */}
            <div className="flex-1 overflow-y-auto px-4 py-6 scroll-smooth">
                {messages.length === 0 ? (
                    /* Welcome screen */
                    <div className="flex flex-col items-center justify-center h-full gap-6 text-center max-w-lg mx-auto">
                        <div className="w-16 h-16 rounded-2xl bg-emerald-500/15 border border-emerald-500/25 flex items-center justify-center shadow-xl shadow-emerald-500/5">
                            <Sparkles size={28} className="text-emerald-400" />
                        </div>
                        <div>
                            <h2 className="text-2xl font-bold text-white mb-2">
                                AI Codebase Explorer
                            </h2>
                            <div className="text-slate-400 text-sm leading-relaxed prose prose-invert prose-sm">
                                <ReactMarkdown>{WELCOME}</ReactMarkdown>
                            </div>
                        </div>
                        {!repoLoaded && (
                            <div className="inline-flex items-center gap-2 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/25 px-4 py-2 rounded-full">
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                                Load a repository from the sidebar to begin
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="flex flex-col gap-6 max-w-3xl mx-auto w-full">
                        {messages.map((msg, i) => (
                            <div
                                key={i}
                                className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"
                                    }`}
                            >
                                {/* Avatar */}
                                <div
                                    className={`w-8 h-8 shrink-0 rounded-lg flex items-center justify-center ${msg.role === "user"
                                            ? "bg-blue-500/20 border border-blue-500/30"
                                            : "bg-emerald-500/20 border border-emerald-500/30"
                                        }`}
                                >
                                    {msg.role === "user" ? (
                                        <User size={14} className="text-blue-400" />
                                    ) : (
                                        <Bot size={14} className="text-emerald-400" />
                                    )}
                                </div>

                                {/* Bubble */}
                                <div
                                    className={`flex flex-col gap-3 max-w-[85%] ${msg.role === "user" ? "items-end" : "items-start"
                                        }`}
                                >
                                    <div
                                        className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${msg.role === "user"
                                                ? "bg-blue-600/80 text-white rounded-tr-sm"
                                                : msg.error
                                                    ? "bg-red-500/10 border border-red-500/20 text-red-300 rounded-tl-sm"
                                                    : "bg-slate-800/80 border border-white/6 text-slate-200 rounded-tl-sm"
                                            }`}
                                    >
                                        {msg.role === "user" ? (
                                            <p>{msg.text}</p>
                                        ) : (
                                            <div className="prose prose-invert prose-sm max-w-none">
                                                <ReactMarkdown>{msg.text}</ReactMarkdown>
                                            </div>
                                        )}
                                    </div>

                                    {/* Code snippet cards */}
                                    {msg.chunks && msg.chunks.length > 0 && (
                                        <div className="w-full flex flex-col gap-2">
                                            <div className="flex items-center gap-1.5 text-xs text-slate-500">
                                                <Layers size={11} />
                                                <span>
                                                    {msg.chunks.length} code section
                                                    {msg.chunks.length !== 1 ? "s" : ""} retrieved
                                                </span>
                                            </div>
                                            {msg.chunks.map((chunk, j) => (
                                                <CodeBlock key={j} chunk={chunk} rank={j + 1} />
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}

                        {/* Typing indicator */}
                        {loading && (
                            <div className="flex gap-3 flex-row">
                                <div className="w-8 h-8 shrink-0 rounded-lg bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center">
                                    <Bot size={14} className="text-emerald-400" />
                                </div>
                                <div className="bg-slate-800/80 border border-white/6 rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-2">
                                    <span className="text-sm text-slate-400">AI is thinking</span>
                                    <span className="flex gap-1">
                                        {[0, 1, 2].map((i) => (
                                            <span
                                                key={i}
                                                className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-bounce"
                                                style={{ animationDelay: `${i * 0.15}s` }}
                                            />
                                        ))}
                                    </span>
                                </div>
                            </div>
                        )}
                    </div>
                )}
                <div ref={bottomRef} />
            </div>

            {/* Input bar */}
            <div className="p-4 border-t border-white/6 bg-slate-950/60 backdrop-blur-sm">
                <div className="max-w-3xl mx-auto flex flex-col gap-2 w-full">
                    {actionStatus && (
                        <div className="text-blue-400 text-xs px-2 animate-pulse font-medium flex items-center gap-2">
                            {actionStatus}
                        </div>
                    )}
                    <div className="flex gap-3 items-end w-full">
                        <div className="flex-1 relative">
                            <textarea
                            ref={textareaRef}
                            value={input}
                            onChange={handleInput}
                            onKeyDown={handleKeyDown}
                            placeholder={
                                repoLoaded
                                    ? "Ask anything about the codebase… (Enter to send)"
                                    : "Load a repository first…"
                            }
                            disabled={!repoLoaded || loading}
                            rows={1}
                            className="w-full bg-slate-800/80 border border-white/10 rounded-xl pl-4 pr-14 py-3 text-sm text-slate-200 placeholder-slate-600 resize-none focus:outline-none focus:ring-1 focus:ring-emerald-500/50 focus:border-emerald-500/50 transition-all disabled:opacity-40 disabled:cursor-not-allowed leading-relaxed"
                        />
                        <FloatingActionMenu 
                            onAction={handleActionMenu} 
                            disabled={!repoLoaded || !isBackendActive} 
                        />
                    </div>
                    <button
                        onClick={handleSubmit}
                        disabled={!repoLoaded || loading || !input.trim()}
                        className="w-10 h-10 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:bg-slate-700 disabled:text-slate-600 text-black flex items-center justify-center transition-all duration-200 shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30 active:scale-95 disabled:cursor-not-allowed shrink-0"
                    >
                        <Send size={16} />
                    </button>
                    </div>
                </div>
                <p className="text-center text-xs text-slate-700 mt-2">
                    Press <kbd className="text-slate-600 font-mono">Enter</kbd> to send ·{" "}
                    <kbd className="text-slate-600 font-mono">Shift+Enter</kbd> for new
                    line
                </p>
            </div>
        </div>
    );
}
