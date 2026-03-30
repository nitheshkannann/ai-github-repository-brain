/**
 * =============================================================================
 * API CLIENT - AI GitHub Repository Brain
 * =============================================================================
 * Production-ready API client with:
 * - Robust error handling & retries
 * - Automatic timeout management
 * - Comprehensive logging
 * - Fallback strategies
 * =============================================================================
 */

// ==============================
// CONFIG
// ==============================

/** Render backend — always the source of truth.
 *  Override with NEXT_PUBLIC_API_BASE for local dev. */
const RENDER_BACKEND = "https://ai-github-repository-brain.onrender.com";

function getAPIBase(): string {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE) {
    return process.env.NEXT_PUBLIC_API_BASE.replace(/\/$/, ""); // strip trailing slash
  }
  return RENDER_BACKEND;
}

const API_BASE = getAPIBase();
const ALT_API_BASE = API_BASE; // No local fallback — keep same base
const API_TIMEOUT = 90000;      // 90 s — Render free tier can be slow
const HEALTH_CHECK_TIMEOUT = 15000; // 15 s health check
const MAX_RETRIES = 1;

console.log(`[API] Base URL: ${API_BASE}`);

// ==============================
// TYPES
// ==============================

export interface LoadRepoResponse {
  status: string;
  files_found: number;
  chunks_created: number;
  vectors_indexed: number;
  message?: string;
}

export interface GenerateRequirementsResponse {
  python: string[];
  javascript: string[];
  source: string;
  entry_points: Record<string, string>;
}

export interface ChunkResult {
  file_path: string;
  chunk_id: string;
  content: string;
  score: string;
}

export interface AskResponse {
  explanation: string;
  retrieved_chunks: ChunkResult[];
}

export interface GenerateReadmeResponse {
  readme_content: string;
}

export interface ReadmeAnalysis {
  missing_sections: string[];
  improvements: string[];
  score_existing: number;
  score_generated: number;
}

export interface CompareReadmeResponse {
  existing_readme: string;
  generated_readme: string;
  analysis: ReadmeAnalysis;
}

export interface HealthResponse {
  status: "ok" | "error";
  message?: string;
}

// ==============================
// HELPERS
// ==============================

/** Create fetch with automatic timeout */
function createFetchWithTimeout(timeoutMs: number) {
  return (input: RequestInfo, init?: RequestInit) => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    return fetch(input, { ...init, signal: controller.signal })
      .then((res) => {
        clearTimeout(timeout);
        return res;
      })
      .catch((err) => {
        clearTimeout(timeout);
        throw err;
      });
  };
}

/** Retry with exponential backoff */
async function withRetry<T>(
  fn: () => Promise<T>,
  maxRetries: number = MAX_RETRIES
): Promise<T> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));

      // Don't retry user/request errors
      if (lastError.message.includes("400") || lastError.message.includes("404")) {
        throw lastError;
      }

      if (attempt === maxRetries) throw lastError;

      const delayMs = Math.pow(2, attempt) * 100;
      console.log(`[API] Retry ${attempt + 1}/${maxRetries} in ${delayMs}ms`);
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }

  throw lastError || new Error("Unknown error");
}

// ==============================
// GENERIC FETCH
// ==============================

async function apiFetch<T>(
  method: "GET" | "POST",
  path: string,
  body?: Record<string, any>,
  timeoutMs: number = API_TIMEOUT
): Promise<T> {
  const fetchWithTimeout = createFetchWithTimeout(timeoutMs);

  async function tryFetch(base: string): Promise<T> {
    const url = `${base}${path}`;
    console.log(`[API] ${method} ${path} via ${base}`, body || "");

    return withRetry(async () => {
      let response: Response;

      try {
        response = await fetchWithTimeout(url, {
          method,
          headers: { "Content-Type": "application/json" },
          body: body ? JSON.stringify(body) : undefined,
        });
      } catch (err: any) {
        if (err.name === "AbortError") {
          throw new Error(`Request timeout (${timeoutMs / 1000}s). The Render free tier may be waking up — wait 30s and retry.`);
        }
        throw new Error(`Cannot reach backend at ${base}. Check Render deployment status.`);
      }

      if (!response.ok) {
        let detail = `HTTP ${response.status}: ${response.statusText}`;
        try {
          const json = await response.json();
          detail = json.detail || detail;
        } catch {}
        throw new Error(detail);
      }

      try {
        const data = (await response.json()) as T;
        console.log(`[API] ✓ ${path} via ${base}:`, data);
        return data;
      } catch (err) {
        throw new Error("Invalid JSON response from backend");
      }
    }, MAX_RETRIES);
  }

  // Only try one base — it's always Render in production
  return tryFetch(API_BASE);
}

// ==============================
// API CALLS
// ==============================

export async function loadRepo(repo_path: string): Promise<LoadRepoResponse> {
  if (!repo_path?.trim()) throw new Error("Repository path is required");
  return apiFetch<LoadRepoResponse>("POST", "/load_repo", { repo_path });
}

export async function askQuestion(
  question: string,
  top_k: number = 3
): Promise<AskResponse> {
  if (!question?.trim()) throw new Error("Question is required");
  return apiFetch<AskResponse>("POST", "/ask", { question, top_k });
}

export async function generateRequirements(
  repo_path: string
): Promise<GenerateRequirementsResponse> {
  if (!repo_path?.trim()) throw new Error("Repository path is required");
  return apiFetch<GenerateRequirementsResponse>("POST", "/generate_requirements", { repo_path });
}

export async function generateReadme(
  repo_path: string
): Promise<GenerateReadmeResponse> {
  if (!repo_path?.trim()) throw new Error("Repository path is required");
  return apiFetch<GenerateReadmeResponse>("POST", "/generate_readme", { repo_path });
}

export async function compareReadme(
  repo_path: string
): Promise<CompareReadmeResponse> {
  if (!repo_path?.trim()) throw new Error("Repository path is required");
  return apiFetch<CompareReadmeResponse>("POST", "/compare_readme", { repo_path });
}
// ==============================
// HEALTH CHECK
// ==============================

export async function checkBackendHealth(): Promise<boolean> {
  async function tryHealth(base: string): Promise<boolean> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60000); // 60s timeout
    const startTime = Date.now();

    console.log(`[API] Checking health → ${base}/health (timeout: 60000ms)`);

    try {
      const response = await fetch(`${base}/health`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
      });

      clearTimeout(timeout);
      const elapsed = Date.now() - startTime;
      console.log(`[API] Health check to ${base} completed in ${elapsed}ms`);

      if (!response.ok) {
        console.warn(`[API] Health check responded ${response.status} on ${base}`);
        return false;
      }

      const data = (await response.json()) as HealthResponse;
      const isHealthy = data.status === "ok";
      console.log(`[API] Backend: ${isHealthy ? "✓ OK" : "✗ DOWN"} via ${base}`, data);
      return isHealthy;
    } catch (err: any) {
      clearTimeout(timeout);
      const elapsed = Date.now() - startTime;
      if (err.name === "AbortError") {
        console.error(`[API] Health check to ${base} timed out after ${elapsed}ms`);
      } else {
        console.error(`[API] Health check error on ${base} (${elapsed}ms):`, err.message);
      }
      return false;
    }
  }

  // Single base — Render URL
  return tryHealth(API_BASE);
}

/** Wait for backend to be ready with retries */
export async function waitForBackendReady(
  maxAttempts: number = 5,
  initialDelayMs: number = 500
): Promise<boolean> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const isHealthy = await checkBackendHealth();
    if (isHealthy) {
      console.log(`[API] Backend ready after ${attempt + 1} attempt(s)`);
      return true;
    }

    if (attempt < maxAttempts - 1) {
      const delayMs = initialDelayMs * Math.pow(2, attempt);
      console.log(`[API] Retrying in ${delayMs}ms...`);
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }

  console.error("[API] Backend did not become ready");
  return false;
}

// ==============================
// 📥 FETCH STORED README (WEBHOOK)
// ==============================

export async function fetchReadme(
  repoName: string
): Promise<{ content: string }> {
  if (!repoName?.trim()) throw new Error("Repository name is required");

  return apiFetch<{ content: string }>(
    "GET",
    `/get_saved_readme?repo_name=${encodeURIComponent(repoName)}`
  );
}