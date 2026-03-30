"use client";

import { useState, useRef, useEffect } from "react";
import { Plus, Box, Terminal, FileText, Search } from "lucide-react";

interface FloatingActionMenuProps {
    onAction: (action: "load" | "dependencies" | "setup" | "readme" | "compare") => void;
    disabled?: boolean;
}

export default function FloatingActionMenu({ onAction, disabled }: FloatingActionMenuProps) {
    const [isOpen, setIsOpen] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const handleSelect = (action: "load" | "dependencies" | "setup" | "readme" | "compare") => {
        setIsOpen(false);
        onAction(action);
    };

    return (
        <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center justify-center z-10" ref={menuRef}>
            {isOpen && (
                <div className="absolute bottom-full mb-3 right-0 w-60 bg-slate-900/95 backdrop-blur-md border border-white/10 rounded-xl shadow-2xl p-1.5 flex flex-col gap-1 z-50 animate-in zoom-in-95 fade-in duration-200">
                    <button
                        type="button"
                        onClick={() => handleSelect("load")}
                        className="w-full flex items-center gap-3 px-3 py-2.5 text-sm font-medium text-emerald-300 hover:text-emerald-200 hover:bg-emerald-900/30 rounded-lg transition-colors text-left group border border-emerald-500/20"
                    >
                        <Search size={16} className="text-emerald-400 group-hover:scale-110 transition-transform" />
                        Load / Index Repository
                    </button>
                    <div className="h-px bg-white/10 my-0.5" />
                    <button
                        type="button"
                        onClick={() => handleSelect("dependencies")}
                        disabled={disabled}
                        className="w-full flex items-center gap-3 px-3 py-2.5 text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800/80 rounded-lg transition-colors text-left disabled:opacity-50 disabled:cursor-not-allowed group"
                    >
                        <Box size={16} className="text-emerald-400 group-hover:scale-110 transition-transform" />
                        Generate Dependencies
                    </button>
                    <button
                        type="button"
                        onClick={() => handleSelect("setup")}
                        disabled={disabled}
                        className="w-full flex items-center gap-3 px-3 py-2.5 text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800/80 rounded-lg transition-colors text-left disabled:opacity-50 disabled:cursor-not-allowed group"
                    >
                        <Terminal size={16} className="text-indigo-400 group-hover:scale-110 transition-transform" />
                        Setup Guide
                    </button>
                    <button
                        type="button"
                        onClick={() => handleSelect("readme")}
                        disabled={disabled}
                        className="w-full flex items-center gap-3 px-3 py-2.5 text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800/80 rounded-lg transition-colors text-left disabled:opacity-50 disabled:cursor-not-allowed group"
                    >
                        <FileText size={16} className="text-blue-400 group-hover:scale-110 transition-transform" />
                        Generate README
                    </button>
                    <button
                        type="button"
                        onClick={() => handleSelect("compare")}
                        disabled={disabled}
                        className="w-full flex items-center gap-3 px-3 py-2.5 text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800/80 rounded-lg transition-colors text-left disabled:opacity-50 disabled:cursor-not-allowed group"
                    >
                        <Search size={16} className="text-purple-400 group-hover:scale-110 transition-transform" />
                        Compare README
                    </button>
                </div>
            )}
            <button
                type="button"
                onClick={() => setIsOpen(!isOpen)}
                disabled={disabled}
                className={`w-8 h-8 flex items-center justify-center rounded-full bg-slate-800 hover:bg-slate-700 border border-white/10 text-slate-400 hover:text-white transition-all duration-200 shadow-md disabled:opacity-50 disabled:cursor-not-allowed group focus:outline-none focus:ring-2 focus:ring-emerald-500/50 ${isOpen ? "bg-slate-700 text-white shadow-emerald-500/20 shadow-lg border-emerald-500/30" : "hover:shadow-white/5"}`}
                aria-label="Repository Actions"
            >
                <Plus size={18} className={`transition-transform duration-200 ${isOpen ? "rotate-45 text-emerald-400" : "group-hover:scale-110"}`} />
            </button>
        </div>
    );
}
