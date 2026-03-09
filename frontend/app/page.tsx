"use client";

import { useState } from "react";
import Sidebar from "@/components/Sidebar";
import Chat from "@/components/Chat";
import { LoadRepoResponse } from "@/lib/api";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

export default function Home() {
  const [repoPath, setRepoPath] = useState("");
  const [topK, setTopK] = useState(3);
  const [repoLoaded, setRepoLoaded] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  function handleRepoLoaded(_info: LoadRepoResponse) {
    setRepoLoaded(true);
  }

  return (
    <div className="flex h-screen bg-[#0d1117] text-white overflow-hidden">
      {/* Sidebar */}
      <aside
        className={`${sidebarOpen ? "w-72" : "w-0"
          } shrink-0 transition-all duration-300 overflow-hidden border-r border-white/6 bg-slate-950/80`}
      >
        <Sidebar
          repoPath={repoPath}
          topK={topK}
          onRepoPathChange={setRepoPath}
          onTopKChange={setTopK}
          onRepoLoaded={handleRepoLoaded}
        />
      </aside>

      {/* Main area */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-12 shrink-0 flex items-center px-4 border-b border-white/6 bg-slate-950/60 backdrop-blur-sm gap-3">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="text-slate-500 hover:text-white transition-colors p-1 rounded-md hover:bg-white/5"
            aria-label="Toggle sidebar"
          >
            {sidebarOpen ? (
              <PanelLeftClose size={18} />
            ) : (
              <PanelLeftOpen size={18} />
            )}
          </button>

          <div className="h-4 w-px bg-white/10" />

          <span className="text-sm font-medium text-slate-300">
            AI GitHub Repository Brain
          </span>

          {repoLoaded && (
            <>
              <div className="h-4 w-px bg-white/10" />
              <div className="flex items-center gap-1.5 text-xs">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-emerald-400 font-medium">
                  Repository indexed
                </span>
              </div>
            </>
          )}

          <div className="ml-auto flex items-center gap-2 text-xs text-slate-600">
            <span>Top-K:</span>
            <span className="font-mono text-slate-400">{topK}</span>
          </div>
        </header>

        {/* Chat takes the rest */}
        <div className="flex-1 overflow-hidden">
          <Chat topK={topK} repoLoaded={repoLoaded} />
        </div>
      </main>
    </div>
  );
}
