"use client";

import { useState, useEffect, useRef } from "react";
import Sidebar from "@/components/Sidebar";
import Chat from "@/components/Chat";
import { LoadRepoResponse, checkBackendHealth, generateRequirements, GenerateRequirementsResponse, generateReadme, compareReadme, CompareReadmeResponse, loadRepo } from "@/lib/api";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import toast from "react-hot-toast";

export default function Home() {
  const [repoPath, setRepoPath] = useState("");
  const [topK, setTopK] = useState(3);
  const [repoLoaded, setRepoLoaded] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isBackendActive, setIsBackendActive] = useState(true);

  // Lifted state from Sidebar
  const [loadLoading, setLoadLoading] = useState(false);
  const [loadResult, setLoadResult] = useState<LoadRepoResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showStats, setShowStats] = useState(false);

  const [reqLoading, setReqLoading] = useState(false);
  const [reqResult, setReqResult] = useState<GenerateRequirementsResponse | null>(null);
  const [reqError, setReqError] = useState<string | null>(null);
  const [showSetup, setShowSetup] = useState(false);

  const [readmeLoading, setReadmeLoading] = useState(false);
  const [readmeResult, setReadmeResult] = useState<string | null>(null);
  const [readmeError, setReadmeError] = useState<string | null>(null);
  const [showReadmeModal, setShowReadmeModal] = useState(false);

  const [compareLoading, setCompareLoading] = useState(false);
  const [compareResult, setCompareResult] = useState<CompareReadmeResponse | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [showCompareModal, setShowCompareModal] = useState(false);

  // Status message state
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const statusTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  function displayStatus(msg: string) {
      setActionStatus(msg);
      if (statusTimeoutRef.current) clearTimeout(statusTimeoutRef.current);
      statusTimeoutRef.current = setTimeout(() => setActionStatus(null), 3000);
  }

  useEffect(() => {
      let mounted = true;
      async function check() {
          const active = await checkBackendHealth();
          if (mounted) {
              setIsBackendActive(active);
          }
      }
      check();
      const interval = setInterval(check, 3000);
      return () => {
          mounted = false;
          clearInterval(interval);
      };
  }, []);

  function handleRepoLoaded(_info: LoadRepoResponse) {
    setRepoLoaded(true);
  }

  async function handleLoad() {
    console.log("Loading started");
    
    if (!repoPath || repoPath.trim() === "") {
        toast.error("Invalid repo path");
        console.log("Loading finished");
        return;
    }

    setLoadLoading(true);
    setLoadError(null);
    setLoadResult(null);
    
    // Toast: Loading
    const loadingToastId = toast.loading("Indexing repository...");
    displayStatus("⚡ Indexing repository...");

    try {
        // Enforce a 20s timeout safety
        const fetchPromise = loadRepo(repoPath.trim());
        const timeoutPromise = new Promise((_, reject) => 
            setTimeout(() => reject(new Error("Request timeout after 20 seconds")), 20000)
        );
        
        const data = await Promise.race([fetchPromise, timeoutPromise]) as LoadRepoResponse;
        
        setLoadResult(data);
        handleRepoLoaded(data);
        
        // Toast: Success
        toast.success("Repository indexed", { id: loadingToastId });
        displayStatus("✅ Repository Indexed");
    } catch (e: unknown) {
        console.error("Error loading repo:", e);
        const errorMessage = e instanceof Error ? e.message : "Unknown error";
        setLoadError(errorMessage);
        
        // Toast: Error
        toast.error("Failed to load repository", { id: loadingToastId });
        displayStatus("❌ Failed to index repository");
    } finally {
        setLoadLoading(false);
        console.log("Loading finished");
    }
  }

  async function handleGenerateRequirements(setupMode: boolean) {
    if (!repoPath.trim()) return;
    setShowSetup(setupMode);
    setReqLoading(true);
    setReqError(null);
    setReqResult(null);
    displayStatus(setupMode ? "⚡ Generating Setup Guide..." : "⚡ Extracting Dependencies...");
    try {
        const data = await generateRequirements(repoPath.trim());
        setReqResult(data);
        displayStatus(setupMode ? "✅ Setup Guide Ready" : "✅ Dependencies Extracted");
    } catch (e: unknown) {
        setReqError(e instanceof Error ? e.message : "Unknown error");
        displayStatus("❌ Failed to analyze dependencies");
    } finally {
        setReqLoading(false);
    }
  }

  async function handleGenerateReadme() {
    if (!repoPath.trim()) return;
    setReadmeLoading(true);
    setReadmeError(null);
    setReadmeResult(null);
    displayStatus("⚡ Generating README...");
    try {
        const data = await generateReadme(repoPath.trim());
        setReadmeResult(data.readme_content);
        setShowReadmeModal(true);
        displayStatus("✅ README Generated");
    } catch (e: unknown) {
        setReadmeError(e instanceof Error ? e.message : "Unknown error");
        displayStatus("❌ Failed to generate README");
    } finally {
        setReadmeLoading(false);
    }
  }

  async function handleCompareReadme() {
    if (!repoPath.trim()) return;
    setCompareLoading(true);
    setCompareError(null);
    setCompareResult(null);
    displayStatus("⚡ Comparing READMEs...");
    try {
        const data = await compareReadme(repoPath.trim());
        setCompareResult(data);
        setShowCompareModal(true);
        displayStatus("✅ Comparison Complete");
    } catch (e: unknown) {
        setCompareError(e instanceof Error ? e.message : "Unknown error");
        displayStatus("❌ Failed to compare READMEs");
    } finally {
        setCompareLoading(false);
    }
  }

  return (
    <div className="flex h-screen bg-gradient-to-br from-neutral-950 via-neutral-900 to-neutral-950 text-white overflow-hidden">
      {/* Sidebar */}
      <aside
        className={`${sidebarOpen ? "w-80" : "w-0"
          } shrink-0 transition-all duration-300 ease-in-out overflow-hidden border-r border-neutral-800/50 bg-neutral-900/40 backdrop-blur-xl`}
      >
        <Sidebar
          repoPath={repoPath}
          topK={topK}
          onRepoPathChange={setRepoPath}
          onTopKChange={setTopK}
          isBackendActive={isBackendActive}
          
          handleLoad={handleLoad}
          loadLoading={loadLoading}
          loadResult={loadResult}
          loadError={loadError}
          showStats={showStats}
          setShowStats={setShowStats}

          reqLoading={reqLoading}
          reqResult={reqResult}
          reqError={reqError}
          showSetup={showSetup}
          setShowSetup={setShowSetup}

          readmeError={readmeError}
          showReadmeModal={showReadmeModal}
          setShowReadmeModal={setShowReadmeModal}
          readmeResult={readmeResult}

          compareError={compareError}
          showCompareModal={showCompareModal}
          setShowCompareModal={setShowCompareModal}
          compareResult={compareResult}
        />
      </aside>

      {/* Main area */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-16 shrink-0 flex items-center px-6 border-b border-neutral-800/50 bg-neutral-900/30 backdrop-blur-md gap-4 shadow-sm">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="text-neutral-400 hover:text-white transition-all duration-200 p-2.5 rounded-xl hover:bg-white/5 active:scale-95"
            aria-label="Toggle sidebar"
          >
            {sidebarOpen ? (
              <PanelLeftClose size={20} />
            ) : (
              <PanelLeftOpen size={20} />
            )}
          </button>

          <div className="h-8 w-px bg-neutral-700" />

          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-600 via-purple-600 to-pink-600 shadow-lg shadow-purple-600/25">
              <span className="text-white font-bold text-lg">🧠</span>
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Repo Brain</h1>
              <p className="text-xs text-neutral-400">AI-Powered Code Analysis</p>
            </div>
          </div>

          {repoLoaded && (
            <>
              <div className="h-8 w-px bg-neutral-700" />
              <div className="flex items-center gap-2.5 text-sm">
                <div className="relative">
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse shadow-lg shadow-emerald-500/50" />
                  <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping opacity-20" />
                </div>
                <span className="text-emerald-400 font-medium">
                  Repository indexed
                </span>
              </div>
            </>
          )}

          <div className="ml-auto flex items-center gap-4">
            <div className="flex items-center gap-2.5 text-xs text-neutral-400 bg-neutral-800/50 px-3 py-1.5 rounded-full border border-neutral-700">
              <span className="font-medium">Top-K:</span>
              <span className="font-mono text-neutral-300">{topK}</span>
            </div>
            {!isBackendActive && (
              <div className="flex items-center gap-2 text-xs text-red-400 bg-red-900/20 px-3 py-1.5 rounded-full border border-red-500/30">
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                <span className="font-medium">Backend offline</span>
              </div>
            )}
          </div>
        </header>

        {/* Chat takes the rest */}
        <div className="flex-1 flex flex-col min-w-0 bg-gradient-to-br from-neutral-950 via-neutral-900/50 to-neutral-950">
          <Chat 
            topK={topK} 
            repoLoaded={repoLoaded} 
            isBackendActive={isBackendActive}
            onLoadRepository={handleLoad}
            onGenerateRequirements={() => handleGenerateRequirements(false)}
            onSetupGuide={() => handleGenerateRequirements(true)}
            onGenerateReadme={handleGenerateReadme}
            onCompareReadme={handleCompareReadme}
            actionStatus={actionStatus}
          />
        </div>
        {/* Footer */}
        <footer className="h-10 flex items-center justify-center text-xs text-neutral-600 border-t border-neutral-800/50 bg-neutral-900/30 backdrop-blur-sm">
          <div className="flex items-center gap-2">
            <span>Powered by</span>
            <span className="text-neutral-400">AI + FAISS</span>
            <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
          </div>
        </footer>
      </main>
    </div>
  );
}
