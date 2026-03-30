"use client";

import { useState, useRef, useEffect } from "react";
import { askQuestion, AskResponse, ChunkResult, fetchReadme } from "@/lib/api";
import CodeBlock from "./CodeBlock";
import ReactMarkdown from "react-markdown";
import { Send, Bot, User, Sparkles, Layers, Copy } from "lucide-react";
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
    const [readme, setReadme] = useState("");
    const bottomRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, loading]);

    useEffect(() => {
        async function autoLoadReadme() {
            if (!repoLoaded) return;

            try {
                const data = await fetchReadme("ai-github-repository-brain");
                setReadme(data.content);
                console.log("✅ README loaded successfully");
            } catch (e: any) {
                console.error("Failed to auto-load README:", e.message);
                // Don't show error to user, just log it
                // README will appear when it's generated
            }
        }

        autoLoadReadme();
    }, [repoLoaded]);

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
        <div className="flex flex-col h-full relative">
            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
                {messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center max-w-2xl mx-auto">
                        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center mb-4 shadow-lg shadow-blue-500/25">
                            <Bot size={32} className="text-white" />
                        </div>
                        <ReactMarkdown>{WELCOME}</ReactMarkdown>
                    </div>
                ) : (
                    messages.map((msg, i) => (
                        <div
                            key={i}
                            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} animate-fade-in`}
                        >
                            <div
                                className={`max-w-2xl ${
                                    msg.role === "user"
                                        ? "bg-blue-600 text-white rounded-2xl rounded-br-sm px-4 py-3 shadow-lg shadow-blue-600/25"
                                        : "bg-neutral-800 text-neutral-100 rounded-2xl rounded-bl-sm px-4 py-3 shadow-lg border border-neutral-700"
                                }`}
                            >
                                <div className="flex items-start gap-3">
                                    {msg.role === "assistant" && (
                                        <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                                            <Bot size={14} className="text-white" />
                                        </div>
                                    )}
                                    <div className="flex-1 space-y-2">
                                        {msg.error ? (
                                            <div className="flex items-center gap-2 text-red-400 text-sm">
                                                <span className="font-medium">Error:</span>
                                                <span>{msg.text}</span>
                                            </div>
                                        ) : (
                                            <div className="prose prose-invert prose-neutral max-w-none">
                                                <ReactMarkdown
                                                    components={{
                                                        code: ({ node, className, children, ...props }) => (
                                                            <code className={`${className} bg-neutral-700 px-1.5 py-0.5 rounded text-xs`} {...props}>
                                                                {children}
                                                            </code>
                                                        ),
                                                        pre: ({ children }) => {
                                                            const codeText = String(children).replace(/^\n+|\n+$/g, "");
                                                            return (
                                                                <div className="relative">
                                                                    <pre className="bg-neutral-900 p-3 rounded-lg overflow-x-auto text-sm">
                                                                        <code>{codeText}</code>
                                                                    </pre>
                                                                    <button
                                                                        onClick={() => navigator.clipboard.writeText(codeText)}
                                                                        className="absolute top-2 right-2 p-1 rounded bg-neutral-700 hover:bg-neutral-600 transition-colors"
                                                                        title="Copy code"
                                                                    >
                                                                        <Copy size={14} />
                                                                    </button>
                                                                </div>
                                                            );
                                                        },
                                                        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                                                        ul: ({ children }) => <ul className="list-disc list-inside space-y-1 mb-2">{children}</ul>,
                                                        ol: ({ children }) => <ol className="list-decimal list-inside space-y-1 mb-2">{children}</ol>,
                                                        strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
                                                        em: ({ children }) => <em className="italic text-neutral-300">{children}</em>,
                                                    }}
                                                >
                                                    {msg.text}
                                                </ReactMarkdown>
                                            </div>
                                        )}
                                        {msg.chunks && msg.chunks.length > 0 && (
                                            <div className="border-t border-neutral-700 pt-2 mt-2">
                                                <div className="flex items-center gap-2 text-xs text-neutral-400 mb-2">
                                                    <Layers size={12} />
                                                    <span>Sources</span>
                                                </div>
                                                <div className="space-y-1">
                                                    {msg.chunks.map((chunk, idx) => (
                                                        <div key={idx} className="text-xs text-neutral-500 font-mono bg-neutral-900/50 px-2 py-1 rounded">
                                                            {chunk.file_path}
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        {msg.role === "assistant" && (
                                            <div className="flex items-center gap-2 text-xs text-neutral-500">
                                                <button
                                                    onClick={() => navigator.clipboard.writeText(msg.text)}
                                                    className="hover:text-neutral-300 transition-colors"
                                                    title="Copy message"
                                                >
                                                    Copy
                                                </button>
                                                <span>•</span>
                                                <span>{new Date().toLocaleTimeString()}</span>
                                            </div>
                                        )}
                                    </div>
                                    {msg.role === "user" && (
                                        <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                                            <User size={14} className="text-white" />
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))
                )}
                {loading && (
                    <div className="flex justify-start">
                        <div className="bg-neutral-800 rounded-2xl rounded-bl-sm px-4 py-3 shadow-lg border border-neutral-700">
                            <div className="flex items-center gap-3">
                                <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                                    <Bot size={14} className="text-white" />
                                </div>
                                <div className="flex space-x-1">
                                    <div className="w-2 h-2 bg-neutral-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }}></div>
                                    <div className="w-2 h-2 bg-neutral-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }}></div>
                                    <div className="w-2 h-2 bg-neutral-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }}></div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
                <div ref={bottomRef} />
            </div>

            {/* README Display */}
            {repoLoaded && (
                <div className="px-6 pb-4">
                    {readme ? (
                        <div className="bg-neutral-900/60 backdrop-blur-sm rounded-2xl p-6 border border-neutral-800/50">
                            <h2 className="text-lg font-semibold mb-4 text-white flex items-center gap-2">
                                📄 Generated README
                            </h2>
                            <div className="prose prose-invert prose-neutral max-w-none text-sm text-neutral-300">
                                <ReactMarkdown>{readme}</ReactMarkdown>
                            </div>
                        </div>
                    ) : (
                        <div className="bg-neutral-900/30 backdrop-blur-sm rounded-2xl p-6 border border-neutral-800/30">
                            <div className="text-center text-neutral-500 text-sm">
                                <div className="w-12 h-12 rounded-full bg-neutral-800 flex items-center justify-center mx-auto mb-3">
                                    📄
                                </div>
                                <p>README not generated yet</p>
                                <p className="text-xs mt-1">Use the "Generate README" button to create one</p>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Input area */}
            <div className="border-t border-neutral-800 bg-neutral-900/40 backdrop-blur-sm p-4">
                <div className="max-w-4xl mx-auto">
                    {!repoLoaded ? (
                        <div className="flex items-center justify-center py-8">
                            <div className="text-center">
                                <div className="w-12 h-12 rounded-full bg-neutral-800 flex items-center justify-center mx-auto mb-3">
                                    <Bot size={24} className="text-neutral-400" />
                                </div>
                                <p className="text-neutral-400 text-sm mb-2">No repository loaded</p>
                                <button
                                    onClick={onLoadRepository}
                                    className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-all duration-200 hover:scale-105 active:scale-95"
                                >
                                    Load Repository
                                </button>
                            </div>
                        </div>
                    ) : !isBackendActive ? (
                        <div className="flex items-center justify-center py-8">
                            <div className="text-center">
                                <div className="w-12 h-12 rounded-full bg-red-900/20 flex items-center justify-center mx-auto mb-3">
                                    <div className="w-3 h-3 rounded-full bg-red-500 animate-pulse" />
                                </div>
                                <p className="text-red-400 text-sm">Backend is offline</p>
                            </div>
                        </div>
                    ) : (
                        <div className="flex gap-3">
                            <textarea
                                ref={textareaRef}
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="Ask anything about your codebase..."
                                className="flex-1 bg-neutral-800 border border-neutral-700 rounded-xl px-4 py-3 text-white placeholder-neutral-500 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
                                rows={1}
                                disabled={loading}
                            />
                            <button
                                onClick={handleSubmit}
                                disabled={!input.trim() || loading}
                                className="bg-blue-600 hover:bg-blue-700 disabled:bg-neutral-700 disabled:text-neutral-500 text-white p-3 rounded-xl transition-all duration-200 hover:scale-105 active:scale-95 disabled:scale-100 disabled:cursor-not-allowed"
                            >
                                <Send size={20} className={loading ? "animate-pulse" : ""} />
                            </button>
                        </div>
                    )}
                    {actionStatus && (
                        <div className="mt-3 text-center">
                            <span className="text-xs text-neutral-500 bg-neutral-800 px-3 py-1 rounded-full inline-block">
                                {actionStatus}
                            </span>
                        </div>
                    )}
                </div>
            </div>
            {/* Floating Action Menu */}
            <FloatingActionMenu
                onAction={handleActionMenu}
                disabled={!repoLoaded || !isBackendActive}
            />
        </div>
    );
}
