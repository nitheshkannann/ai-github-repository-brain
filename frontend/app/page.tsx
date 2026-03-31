"use client";

import { useState, useEffect, useRef } from "react";
import Sidebar from "@/components/Sidebar";
import Chat from "@/components/Chat";
import {
  LoadRepoResponse,
  checkBackendHealth,
  generateRequirements,
  GenerateRequirementsResponse,
  generateReadme,
  compareReadme,
  CompareReadmeResponse,
  loadRepo,
} from "@/lib/api";
import { PanelLeftClose, PanelLeftOpen, Cpu, Zap } from "lucide-react";
import toast from "react-hot-toast";

/* ─── Particle canvas background ──────────────────────────────────────────── */
function ParticleCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    const particles: {
      x: number; y: number;
      vx: number; vy: number;
      r: number; alpha: number; color: string;
    }[] = [];

    const COLORS = ["#00d4ff", "#7c3aed", "#0080ff", "#00ff9d"];
    const N = 60;

    function resize() {
      canvas!.width = window.innerWidth;
      canvas!.height = window.innerHeight;
    }
    resize();
    window.addEventListener("resize", resize);

    for (let i = 0; i < N; i++) {
      particles.push({
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
        r: Math.random() * 1.8 + 0.3,
        alpha: Math.random() * 0.5 + 0.15,
        color: COLORS[Math.floor(Math.random() * COLORS.length)],
      });
    }

    function draw() {
      ctx!.clearRect(0, 0, canvas!.width, canvas!.height);

      // Draw connecting lines
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 130) {
            ctx!.beginPath();
            ctx!.moveTo(particles[i].x, particles[i].y);
            ctx!.lineTo(particles[j].x, particles[j].y);
            ctx!.strokeStyle = `rgba(0, 212, 255, ${0.06 * (1 - dist / 130)})`;
            ctx!.lineWidth = 0.6;
            ctx!.stroke();
          }
        }
      }

      // Draw particles
      for (const p of particles) {
        ctx!.beginPath();
        ctx!.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx!.fillStyle = p.color;
        ctx!.globalAlpha = p.alpha;
        ctx!.fill();

        // Glow
        const grad = ctx!.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 6);
        grad.addColorStop(0, p.color + "33");
        grad.addColorStop(1, "transparent");
        ctx!.beginPath();
        ctx!.arc(p.x, p.y, p.r * 6, 0, Math.PI * 2);
        ctx!.fillStyle = grad;
        ctx!.globalAlpha = p.alpha * 0.4;
        ctx!.fill();
        ctx!.globalAlpha = 1;

        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = canvas!.width;
        if (p.x > canvas!.width) p.x = 0;
        if (p.y < 0) p.y = canvas!.height;
        if (p.y > canvas!.height) p.y = 0;
      }

      animId = requestAnimationFrame(draw);
    }
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 z-0 pointer-events-none"
      style={{ opacity: 0.7 }}
    />
  );
}

/* ─── Main Page ────────────────────────────────────────────────────────────── */
export default function Home() {
  const [repoPath, setRepoPath] = useState("");
  const [topK, setTopK] = useState(3);
  const [repoLoaded, setRepoLoaded] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isBackendActive, setIsBackendActive] = useState(true);
  const [mounted, setMounted] = useState(false);

  // Lifted sidebar state
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

  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const statusTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Mount animation
  useEffect(() => { setMounted(true); }, []);

  function displayStatus(msg: string) {
    setActionStatus(msg);
    if (statusTimeoutRef.current) clearTimeout(statusTimeoutRef.current);
    statusTimeoutRef.current = setTimeout(() => setActionStatus(null), 3000);
  }

  useEffect(() => {
    let mounted = true;
    async function check() {
      const active = await checkBackendHealth();
      if (mounted) setIsBackendActive(active);
    }
    check();
    const interval = setInterval(check, 3000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  function handleRepoLoaded(_info: LoadRepoResponse) { setRepoLoaded(true); }

  async function handleLoad() {
    if (!repoPath || repoPath.trim() === "") {
      toast.error("Invalid repo path");
      return;
    }
    setLoadLoading(true);
    setLoadError(null);
    setLoadResult(null);
    const loadingToastId = toast.loading("Indexing… this can take 1–3 min on Render free tier ☕");
    displayStatus("⚡ Indexing repository...");
    try {
      const data = await loadRepo(repoPath.trim());
      setLoadResult(data);
      handleRepoLoaded(data);
      toast.success("Repository indexed", { id: loadingToastId });
      displayStatus("✅ Repository Indexed");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      setLoadError(msg);
      toast.error("Failed to load repository", { id: loadingToastId });
      displayStatus("❌ Failed to index repository");
    } finally {
      setLoadLoading(false);
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
    } finally { setReqLoading(false); }
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
    } finally { setReadmeLoading(false); }
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
    } finally { setCompareLoading(false); }
  }

  return (
    <>
      {/* ── Scene Background ── */}
      <div className="scene-bg">
        <div className="orb orb-1" />
        <div className="orb orb-2" />
        <div className="orb orb-3" />
        <div className="orb orb-4" />
        <div className="stars" />
        <div className="grid-overlay" />
        <div className="scanline" />
      </div>

      {/* ── Particle Canvas ── */}
      <ParticleCanvas />

      {/* ── App Shell ── */}
      <div
        className="relative z-10 flex h-screen overflow-hidden"
        style={{
          opacity: mounted ? 1 : 0,
          transition: "opacity 0.6s ease",
        }}
      >
        {/* ──────────────────── SIDEBAR ──────────────────── */}
        <aside
          className={`sidebar-3d shrink-0 transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] overflow-hidden ${sidebarOpen ? "w-80" : "w-0"
            } ${mounted ? "animate-slide-left" : ""}`}
          style={{ position: "relative" }}
        >
          {/* Glowing top accent */}
          <div className="glow-line-top" />
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

        {/* ──────────────────── MAIN ──────────────────── */}
        <main className="flex-1 flex flex-col min-w-0">
          {/* ── Header ── */}
          <header
            className={`header-3d h-16 shrink-0 flex items-center px-5 gap-4 relative ${mounted ? "animate-slide-down" : ""
              }`}
          >
            {/* Glowing bottom accent */}
            <div
              style={{
                position: "absolute",
                bottom: 0, left: 0, right: 0,
                height: "1px",
                background: "linear-gradient(90deg, transparent 0%, rgba(0,212,255,0.15) 50%, transparent 100%)",
              }}
            />

            {/* Sidebar toggle */}
            <button
              id="sidebar-toggle-btn"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="toggle-btn"
              aria-label="Toggle sidebar"
            >
              {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
            </button>

            <div className="neon-divider" />

            {/* Logo */}
            <div className="flex items-center gap-3">
              <div className="logo-orb">
                <span style={{ fontSize: 22 }}>🧠</span>
              </div>
              <div>
                <h1
                  style={{
                    margin: 0,
                    fontSize: 18,
                    fontWeight: 800,
                    letterSpacing: "-0.02em",
                    background: "linear-gradient(90deg, #e2eeff 0%, #00d4ff 60%, #7c3aed 100%)",
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent",
                    backgroundClip: "text",
                  }}
                >
                  Repo Brain
                </h1>
                <p
                  style={{
                    margin: 0,
                    fontSize: 11,
                    color: "#3a6080",
                    fontFamily: "'JetBrains Mono', monospace",
                    letterSpacing: "0.05em",
                  }}
                >
                  AI · CODE · ANALYSIS
                </p>
              </div>
            </div>

            {/* Online status */}
            {repoLoaded && (
              <>
                <div className="neon-divider" />
                <div className="badge-online">
                  <div className="pulse-dot pulse-dot-green" />
                  Repository indexed
                </div>
              </>
            )}

            {/* Right side */}
            <div className="ml-auto flex items-center gap-3">
              {/* Top-K pill */}
              <div className="topk-pill">
                <Zap size={11} style={{ color: "#00d4ff" }} />
                <span>Top-K</span>
                <span>{topK}</span>
              </div>

              {/* Backend status */}
              {isBackendActive ? (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    background: "rgba(0,255,157,0.06)",
                    border: "1px solid rgba(0,255,157,0.15)",
                    borderRadius: 100,
                    padding: "4px 10px",
                    fontSize: 11,
                    color: "#00ff9d",
                    fontWeight: 600,
                  }}
                >
                  <Cpu size={11} />
                  API Live
                </div>
              ) : (
                <div className="badge-offline">
                  <div className="pulse-dot pulse-dot-red" />
                  Backend offline
                </div>
              )}
            </div>
          </header>

          {/* ── Chat area ── */}
          <div
            className={`flex-1 flex flex-col min-w-0 chat-bg ${mounted ? "animate-fade-up delay-200" : ""
              }`}
          >
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

          {/* ── Footer ── */}
          <footer className="footer-bar h-9 flex items-center justify-center gap-3">
            <span>POWERED BY</span>
            <div className="footer-dot" />
            <span style={{ color: "#00d4ff" }}>GEMINI</span>
            <div className="footer-dot" style={{ background: "#7c3aed", animationDelay: "0.8s" }} />
            <span style={{ color: "#7c3aed" }}>KEYWORD-SEARCH</span>
            <div className="footer-dot" style={{ background: "#00ff9d", animationDelay: "1.6s" }} />
            <span style={{ color: "#00ff9d" }}>FASTAPI</span>
          </footer>
        </main>
      </div>
    </>
  );
}
