const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface LoadRepoResponse {
  status: string;
  files_found: number;
  chunks_created: number;
  vectors_indexed: number;
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

async function apiFetch<T>(path: string, body: object): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    // Network-level failure (backend not running, wrong port, CORS preflight blocked, etc.)
    console.error(`[api] Network error calling ${path}:`, err);
    throw new Error(
      `Cannot reach the backend at ${API_BASE}. ` +
      "Make sure the FastAPI server is running:\n" +
      "  uvicorn src.api:app --reload --port 8000"
    );
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const json = await res.json();
      detail = json.detail ?? JSON.stringify(json);
    } catch {
      /* ignore parse errors */
    }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

export async function loadRepo(repo_path: string): Promise<LoadRepoResponse> {
  return apiFetch<LoadRepoResponse>("/load_repo", { repo_path });
}

export async function askQuestion(
  question: string,
  top_k: number
): Promise<AskResponse> {
  return apiFetch<AskResponse>("/ask", { question, top_k });
}

export async function generateRequirements(repo_path: string): Promise<GenerateRequirementsResponse> {
  return apiFetch<GenerateRequirementsResponse>("/generate_requirements", { repo_path });
}
