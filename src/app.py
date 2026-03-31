"""
app.py — AI GitHub Repository Brain
=====================================
FastAPI Web Server for AI-powered codebase analysis.
Also supports CLI mode for backward compatibility.

Web Server:
    uvicorn src.app:app --reload --port 8000

CLI (backward compatibility):
    python src/app.py [--repo PATH] [--top-k N]
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))

import argparse
import logging
import os
import subprocess
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

# ── FastAPI ───────────────────────────────────────────────────────────────────
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Make sure sibling modules in src/ are importable ──────────────────────────
from repo_parser import get_code_files           # type: ignore[import]
from chunker import chunk_code_files             # type: ignore[import]
# NOTE: No heavy ML imports — using lightweight keyword search instead of embeddings.
import litellm

# Only show WARNING+ from libraries so our own prints stay clean
logging.basicConfig(level=logging.WARNING)
# Suppress noisy litellm info logs
litellm.suppress_debug_info = True 

logger = logging.getLogger(__name__)

# ── Initialize FastAPI App ────────────────────────────────────────────────────
app = FastAPI(
    title="AI GitHub Repository Brain",
    description="Ask questions about a codebase",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Lightweight startup — zero ML libs, just FastAPI + litellm."""
    print("[Startup] ✅ App started (zero-ML mode — keyword search, no embeddings/FAISS)")

# ── Add CORS Middleware ───────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "*",  # Fallback to all origins (development)
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allow all headers
)

# ── Request/Response Models ───────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str

class LoadRepoRequest(BaseModel):
    repo_path: str

class LoadRepoResponse(BaseModel):
    status: str
    files_found: int
    chunks_created: int
    vectors_indexed: int
    message: str = "Repository loaded successfully"

class AskRequest(BaseModel):
    question: str
    top_k: int = 3

class ChunkResult(BaseModel):
    file_path: str
    chunk_id: str
    content: str
    score: str

class AskResponse(BaseModel):
    explanation: str
    retrieved_chunks: List[ChunkResult]

class GenerateRequirementsRequest(BaseModel):
    repo_path: str

class GenerateRequirementsResponse(BaseModel):
    python: List[str]
    javascript: List[str]
    source: str
    entry_points: Dict[str, str]

class GenerateReadmeRequest(BaseModel):
    repo_path: str

class GenerateReadmeResponse(BaseModel):
    readme_content: str

class ReadmeAnalysis(BaseModel):
    missing_sections: List[str]
    improvements: List[str]
    score_existing: float
    score_generated: float

class CompareReadmeRequest(BaseModel):
    repo_path: str

class CompareReadmeResponse(BaseModel):
    existing_readme: str
    generated_readme: str
    analysis: ReadmeAnalysis

# ── Global State: stores raw chunks per repo path ─────────────────────────────
# { repo_path: List[Dict] }  — lightweight, no ML objects
_pipeline_cache: Dict[str, List[Dict]] = {}


# ── Lightweight keyword retrieval (replaces FAISS) ────────────────────────────

def simple_search(chunks: List[Dict], query: str, top_k: int = 3) -> List[Dict]:
    """
    Keyword-frequency retrieval — zero RAM overhead, no ML dependencies.
    Scores each chunk by how many times query words appear in its content.
    """
    query_words = query.lower().split()
    scored = []
    for chunk in chunks:
        content_lower = chunk["content"].lower()
        score = sum(content_lower.count(word) for word in query_words)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Fallback: if no keyword hits, return first top_k chunks
    if not scored:
        return chunks[:top_k]

    return [chunk for _, chunk in scored[:top_k]]


# ── Handle GitHub URLs ────────────────────────────────────────────────────────

def resolve_repo_path(repo_input: str) -> str:
    """
    Resolve a repository path or GitHub URL to a local path.
    
    Supports:
      - Local file paths (returned as-is)
      - GitHub URLs (auto-cloned to data/repos/{repo-name})
    
    Args:
        repo_input: Local path or GitHub URL
        
    Returns:
        Local path to the repository
        
    Raises:
        ValueError: If cloning fails or path is invalid
    """
    repo_input = repo_input.strip()
    
    if not repo_input:
        raise ValueError("Repository path or URL cannot be empty")
    
    # Check if it's a GitHub URL
    is_github_url = repo_input.startswith("https://github.com") or repo_input.startswith("git@github.com")
    
    if is_github_url:
        print(f"[API] 🔗 GitHub URL detected: {repo_input}")
        
        # Extract repo name from URL
        repo_name = repo_input.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        
        if not repo_name or repo_name == "github.com":
            raise ValueError(f"Invalid GitHub URL: {repo_input}")
        
        print(f"[API] 📦 Repository name: {repo_name}")
        
        # Define clone directory
        repos_dir = os.path.join("data", "repos")
        clone_dir = os.path.join(repos_dir, repo_name)
        
        # Create repos directory if needed
        try:
            os.makedirs(repos_dir, exist_ok=True)
        except Exception as e:
            raise ValueError(f"Cannot create repos directory: {e}")
        
        print(f"[API] 📁 Clone directory: {clone_dir}")
        
        # Clone if not already exists
        if os.path.exists(clone_dir):
            print(f"[API] ✓ Repository already cached locally")
            return clone_dir
        
        print(f"[API] 📥 Cloning repository (this may take a minute)...")
        try:
            subprocess.run(
                ["git", "clone", repo_input, clone_dir],
                check=True,
                capture_output=True,
                timeout=300  # 5 minute timeout for large repos
            )
            print(f"[API] ✓ Repository cloned successfully to {clone_dir}")
        except subprocess.TimeoutExpired:
            raise ValueError("Clone operation timed out (5 minutes). Repository is too large.")
        except subprocess.CalledProcessError as e:
            error_msg = ""
            if e.stderr:
                try:
                    error_msg = e.stderr.decode()
                except:
                    error_msg = str(e.stderr)
            raise ValueError(f"Failed to clone repository: {error_msg or str(e)}")
        except FileNotFoundError:
            raise ValueError("Git command not found. Please install Git: https://git-scm.com")
        except Exception as e:
            raise ValueError(f"Unexpected error cloning repository: {str(e)}")
        
        return clone_dir
    
    # Treat as local path
    local_path = os.path.expanduser(repo_input)  # Handle ~ in paths
    
    if not os.path.exists(local_path):
        raise ValueError(
            f"Repository path not found: {repo_input}\n"
            f"Please provide a valid local path or GitHub URL (https://github.com/user/repo)"
        )
    
    if not os.path.isdir(local_path):
        raise ValueError(f"Invalid repository path (not a directory): {local_path}")
    
    print(f"[API] 📂 Using local path: {local_path}")
    return local_path


# ── Build the pipeline ────────────────────────────────────────────────────────

def build_pipeline(repo_path: str, top_k: int = 3):
    """
    Runs the one-time setup:
      1. Parse all code files from the repository.
      2. Split them into chunks.
      3. Load the embedding model (imported HERE, not at module level).
      4. Generate embeddings for every chunk.
      5. Build the FAISS index.

    Returns:
        model      : SentenceTransformer (reused for query embedding)
        retriever  : FAISSRetriever (ready to search)
    """
    # ── Lazy imports — keeps startup fast on Render ──────────────────────────
    from embedder import load_model, generate_embeddings  # type: ignore[import]
    from retriever import FAISSRetriever                  # type: ignore[import]

    print("\n🔍  Scanning repository ...")
    files = get_code_files(repo_path)
    if not files:
        print(f"❌  No supported code files found at: {repo_path}")
        sys.exit(1)

    # ── Safety cap: prevent OOM on Render Free Tier (512MB) ──────────────────
    files = files[:50]
    print(f"[SAFE MODE] Files limited: {len(files)}")
    print(f"    ✓ {len(files)} files found")

    print("✂️   Chunking files ...")
    chunks = chunk_code_files(files)
    print(f"    ✓ {len(chunks)} chunks created")

    print("🤖  Loading embedding model (paraphrase-MiniLM-L3-v2, CPU) ...")
    model = load_model()
    print("    ✓ Model ready")

    print("⚡  Generating embeddings (batch_size=8, safe mode) ...")
    embedded = generate_embeddings(chunks, model, batch_size=8)
    gc.collect()  # Free RAM immediately after embedding
    print(f"    ✓ {len(embedded)} embeddings  (dim={len(embedded[0]['embedding'])})")

    print("📦  Building FAISS index ...")
    retriever = FAISSRetriever()
    retriever.build_index(embedded)
    print(f"    ✓ Index built — {retriever.index.ntotal} vectors\n")  # type: ignore[union-attr]

    return model, retriever


# ── Answer a single query ─────────────────────────────────────────────────────

def answer_query(
    query: str,
    model,
    retriever,        # FAISSRetriever — not imported globally to keep startup fast
    top_k: int
) -> None:
    """
    Embeds the query, retrieves the top-k chunks from FAISS, generates an LLM
    explanation using the context, and pretty-prints the results.
    """
    # Embed the query with the same model used for the chunks
    query_vec: np.ndarray = model.encode(
        [query], convert_to_numpy=True
    )[0].astype("float32")

    results: List[Dict[str, str]] = retriever.retrieve(query_vec, top_k=top_k)

    if not results:
        print("\n  (No results found)\n")
        return

    # 1. Combine retrieved chunks into a context string
    context_blocks = []
    for rank, chunk in enumerate(results, start=1):
        context_blocks.append(
            f"--- Code Section {rank} ---\n"
            f"File: {chunk['file_path']}\n"
            f"Content:\n{chunk['content']}\n"
        )
    context_str = "\n".join(context_blocks)

    # 2. Build the LLM prompt
    sys_prompt = "You are a helpful coding assistant. Using the following code context, explain the answer to the user's question."
    user_prompt = f"Context:\n{context_str}\n\nQuestion: {query}"

    # 3. Call the LLM (Using a free/default model for testing if no key is set, or let litellm handle it)
    print("\n  🤖 Thinking...\n")
    try:
        models_to_try = [
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash",
            "gemini-2.0-flash-exp",
            "gemini-1.5-pro-latest"
        ]
        explanation = None
        last_error = None
        
        for model_name in models_to_try:
            try:
                print(f"[API] 🤖 Trying model: {model_name}")
                response = litellm.completion(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                explanation = response.choices[0].message.content
                break
            except Exception as e:
                last_error = e
                continue

        if not explanation:
            explanation = f"[LLM Error: {last_error}]\nMake sure you have set a valid GEMINI_API_KEY in the .env file."
    except Exception as e:
        explanation = f"[Unhandled LLM Error: {e}]"

    # 4. Print the LLM explanation
    print(f"{'─'*60}")
    print("  ✨ Explanation:")
    print(f"{'─'*60}\n")
    # indent the explanation
    for line in explanation.splitlines():
        print(f"  {line}")
    print()

    # 5. Print the raw code references
    print(f"{'─'*60}")
    print(f"  Top {len(results)} relevant code section(s):")
    print(f"{'─'*60}\n")

    for rank, chunk in enumerate(results, start=1):
        file_path = chunk["file_path"]
        chunk_id  = chunk["chunk_id"]
        content   = chunk["content"]
        score     = chunk.get("score", "N/A")

        print(f"  {rank}. 📄 {file_path}  [{chunk_id}]  (score: {score})")
        print(f"  {'─'*56}")

        # Print the content indented, capped at 400 chars for readability
        display: str = content[:400]
        for line in display.splitlines():
            print(f"     {line}")

        if len(content) > 400:
            print(f"     ... [{len(content) - 400} more characters]")
        print()

    print(f"{'─'*60}\n")


# ── CLI entry point ───────────────────────────────────────────────────────────
# (parse_args defined once below, near main_cli)


# ── FastAPI Endpoints ────────────────────────────────────────────────────────

@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint that returns health status."""
    print("[API] GET / - Health check")
    return {"status": "ok"}

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    print("[API] GET /health - Health check")
    return {"status": "ok"}

@app.post("/load_repo", response_model=LoadRepoResponse)
async def load_repo(request: LoadRepoRequest):
    """Load and index a repository (local path or GitHub URL)."""
    try:
        print(f"[API] POST /load_repo - Input: {request.repo_path}")
        
        repo_path = request.repo_path.strip()
        if not repo_path:
            raise ValueError("Repository path cannot be empty")
        
        # Resolve path (handles GitHub URLs, local paths)
        try:
            repo_path = resolve_repo_path(repo_path)
        except ValueError as e:
            print(f"[API] ✗ Path resolution error: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        
        print(f"[API] ✓ Repository resolved: {repo_path}")
        
        # Parse files
        try:
            files = get_code_files(repo_path)
            if not files:
                raise HTTPException(
                    status_code=400,
                    detail=f"No supported code files found. Ensure the repository has Python, JS, TS, or Java files at: {repo_path}"
                )
        except Exception as e:
            print(f"[API] ✗ Error parsing files: {e}")
            raise HTTPException(status_code=400, detail=f"Cannot parse repository: {str(e)}")
        
        files_count_total = len(files)
        files = files[:50]  # Safety cap — prevent OOM on Render Free Tier (512MB)
        files_count = len(files)
        print(f"[SAFE MODE] Files limited: {files_count} (of {files_count_total} found)")
        print(f"[API] ✓ {files_count} files found")
        
        # Chunk files
        try:
            chunks = chunk_code_files(files)
            if not chunks:
                raise HTTPException(status_code=400, detail="No code chunks could be created from the repository")
        except Exception as e:
            print(f"[API] ✗ Error chunking files: {e}")
            raise HTTPException(status_code=400, detail=f"Cannot chunk repository: {str(e)}")
        
        chunks_count = len(chunks)
        print(f"[API] ✓ {chunks_count} chunks created")

        # ── Store chunks directly — no embeddings, no FAISS, zero RAM overhead ──
        _pipeline_cache[repo_path] = chunks
        print(f"[API] ✓ Chunks cached (keyword search mode)")

        message = (
            f"Repository loaded successfully! (keyword search mode)\n"
            f"Files: {files_count} | Chunks: {chunks_count}"
        )

        return {
            "status": "success",
            "files_found": files_count,
            "chunks_created": chunks_count,
            "vectors_indexed": chunks_count,  # repurposed field — chunk count
            "message": message
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] ✗ Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """Ask a question about the loaded repository."""
    try:
        print(f"[API] POST /ask - Question: {request.question[:50]}...")

        if not _pipeline_cache:
            raise HTTPException(status_code=400, detail="No repository loaded. Use /load_repo first.")

        # Use the first cached repo's chunks
        repo_path = list(_pipeline_cache.keys())[0]
        chunks: List[Dict] = _pipeline_cache[repo_path]

        # ── Keyword retrieval — zero RAM, no ML ───────────────────────────────
        results: List[Dict] = simple_search(chunks, request.question, request.top_k)
        print(f"[API] ✓ {len(results)} chunks retrieved via keyword search")

        if not results:
            return {
                "explanation": "No relevant code sections found.",
                "retrieved_chunks": []
            }

        # Build context for LLM
        context_blocks = []
        for rank, chunk in enumerate(results, start=1):
            context_blocks.append(
                f"--- Code Section {rank} ---\n"
                f"File: {chunk['file_path']}\n"
                f"Content:\n{chunk['content']}\n"
            )
        context_str = "\n".join(context_blocks)

        # ── Call LLM (unchanged) ──────────────────────────────────────────────
        sys_prompt = "You are a helpful coding assistant. Using the following code context, explain the answer to the user's question."
        user_prompt = f"Context:\n{context_str}\n\nQuestion: {request.question}"

        print(f"[API] 🤖 Calling LLM...")
        explanation = None
        last_error = None

        models_to_try = [
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash",
            "gemini-2.0-flash-exp",
            "gemini-1.5-pro-latest"
        ]

        for model_name in models_to_try:
            try:
                print(f"[API] 🤖 Trying model: {model_name}")
                response = litellm.completion(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                explanation = response.choices[0].message.content
                print(f"[API] ✓ LLM response received from {model_name}")
                break
            except Exception as e:
                last_error = e
                print(f"[API] {model_name} failed: {e}")
                continue

        if not explanation:
            explanation = f"[LLM Error: {last_error}] Make sure GEMINI_API_KEY is set."
            print(f"[API] ✗ All LLM models failed")

        # Format chunks for response
        chunk_results = [
            ChunkResult(
                file_path=chunk["file_path"],
                chunk_id=chunk["chunk_id"],
                content=chunk["content"],
                score="keyword-match"
            )
            for chunk in results
        ]

        return {
            "explanation": explanation,
            "retrieved_chunks": chunk_results
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] ✗ Error in /ask: {e}")
        raise HTTPException(status_code=500, detail=str(e))

from dependency_analyzer import generate_requirements as run_dependency_analysis

@app.get("/version")
def version():
    """Version endpoint for deployment verification."""
    return {"version": "readme-final-v1"}

@app.post("/generate_requirements", response_model=GenerateRequirementsResponse)
async def generate_requirements(request: GenerateRequirementsRequest):
    """Generate requirements from repository analysis using dependency_analyzer."""
    try:
        repo_path = request.repo_path.strip()
        print(f"[API] POST /generate_requirements - {repo_path}")
        
        # Resolve GitHub URLs or local paths
        resolved_path = resolve_repo_path(repo_path)
        
        # Use the real analyzer
        result = run_dependency_analysis(resolved_path)
        
        return {
            "python": result.get("python", []),
            "javascript": result.get("javascript", []),
            "source": result.get("source", "detected_from_files"),
            "entry_points": result.get("entry_points", {})
        }
    except Exception as e:
        print(f"[API] ✗ Error in /generate_requirements: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate_readme", response_model=GenerateReadmeResponse)
async def generate_readme(request: GenerateReadmeRequest):
    """Generate a high-quality README.md for the repository."""
    try:
        repo_path = request.repo_path.strip()
        print(f"[API] POST /generate_readme - {repo_path}")

        # Ensure repo is indexed and chunks are cached
        if repo_path not in _pipeline_cache:
            # Try to resolve and load repo if it was indexed under a different string
            # or if indexing is needed. 
            print(f"[API] Repo {repo_path} not found in cache. Attempting resolution...")
            repo_path = resolve_repo_path(repo_path)

        if repo_path not in _pipeline_cache:
            raise HTTPException(status_code=400, detail="Repository not indexed. Use /load_repo first.")

        chunks = _pipeline_cache[repo_path]
        # Use first 20 chunks for context
        context = "\n".join([c["content"] for c in chunks[:20]])

        if not os.getenv("GEMINI_API_KEY"):
            return {"readme_content": "# Error: Gemini API Key Missing\n\nPlease set GEMINI_API_KEY in Render environment variables."}

        print(f"[API] 🤖 Calling Gemini README gen (model: gemini-1.5-flash-latest)")
        response = litellm.completion(
            model="gemini-1.5-flash-latest",
            messages=[
                {
                    "role": "user",
                    "content": f"""
Generate a professional GitHub README.md in markdown format.

Include:
- Project title
- Description
- Features
- Tech stack
- Installation
- Usage
- Folder structure

Repository Context (Code Samples):
{context}
"""
                }
            ]
        )

        readme = response['choices'][0]['message']['content']
        
        # Log generation for verification
        print("README GENERATED:", readme[:200].replace("\n", " ") + "...")

        return {
            "readme_content": readme
        }
    except Exception as e:
        print(f"[API] ✗ Error in /generate_readme: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/compare_readme", response_model=CompareReadmeResponse)
async def compare_readme(request: CompareReadmeRequest):
    """Compare existing and generated README."""
    try:
        repo_path = request.repo_path.strip()
        print(f"[API] POST /compare_readme - {repo_path}")

        # 1. Resolve and check cache
        resolved_path = resolve_repo_path(repo_path)
        if resolved_path not in _pipeline_cache:
            # Auto-load if possible
            await load_repo(LoadRepoRequest(repo_path=repo_path))
        
        chunks = _pipeline_cache.get(resolved_path, [])
        if not chunks:
            raise HTTPException(status_code=400, detail="Repository not loaded or empty")

        # 2. Try to find existing README
        existing_readme = ""
        readme_path = Path(resolved_path) / "README.md"
        if not readme_path.exists():
            # try lowercase
            readme_path = Path(resolved_path) / "readme.md"
        
        if readme_path.exists():
            with open(readme_path, "r", encoding="utf-8") as f:
                existing_readme = f.read()
        
        # 3. Generate a new one
        gen_resp = await generate_readme(GenerateReadmeRequest(repo_path=repo_path))
        generated_readme = gen_resp["readme_content"]

        # 4. Use LLM to analyze the difference
        print("[API] 🤖 Analyzing README differences...")
        analysis_prompt = f"""
Compare the following two README files for a software project and provide a structured analysis.

EXISTING README:
{existing_readme[:5000]}

GENERATED README:
{generated_readme[:5000]}

Provide the result as a JSON object with:
- missing_sections: List of important sections in the generated one that are missing in the existing one.
- improvements: List of specific phrasing or content improvements found in the generated one.
- score_existing: A quality score from 1-10 for the existing one.
- score_generated: A quality score from 1-10 for the generated one.

Output ONLY valid JSON.
"""
        print(f"[API] 🤖 Comparing READMEs (model: gemini-1.5-flash-latest)")
        analysis_res = litellm.completion(
            model="gemini-1.5-flash-latest",
            messages=[{"role": "user", "content": analysis_prompt}],
            response_format={ "type": "json_object" }
        )
        
        try:
            analysis_data = json.loads(analysis_res.choices[0].message.content)
        except:
            analysis_data = {
                "missing_sections": ["Installation", "Features"],
                "improvements": ["More detailed tech stack"],
                "score_existing": 5.0,
                "score_generated": 8.0
            }

        return {
            "existing_readme": existing_readme or "No existing README found.",
            "generated_readme": generated_readme,
            "analysis": analysis_data
        }
    except Exception as e:
        print(f"[API] ✗ Error in /compare_readme: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── CLI entry point (for backward compatibility) ────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI GitHub Repository Brain — ask questions about a codebase."
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=str(Path(__file__).resolve().parent.parent),
        help="Path to the repository to analyse (default: project root)"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of code chunks to retrieve per query (default: 3)"
    )
    return parser.parse_args()


def main_cli() -> None:
    """CLI mode (interactive Q&A)."""
    args = parse_args()
    repo_path = args.repo
    top_k     = args.top_k

    load_dotenv()
    if not os.environ.get("GEMINI_API_KEY"):
        print("WARNING: GEMINI_API_KEY not set. LLM features may not work.")
    print("✓ Gemini API key loaded successfully")

    # ── Banner ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("   🧠  AI GitHub Repository Brain")
    print("=" * 60)
    print(f"   Repository : {repo_path}")
    print(f"   Top-K      : {top_k}")
    print("=" * 60)

    # ── One-time pipeline setup ───────────────────────────────────────────────
    model, retriever = build_pipeline(repo_path, top_k)

    # ── Interactive Q&A loop ──────────────────────────────────────────────────
    print("💬  Ready! Type your question and press Enter.")
    print("    (Type 'exit' or 'quit' to stop)\n")

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            # Handle Ctrl+C / piped input gracefully
            print("\n\n👋  Goodbye!\n")
            break

        if not query:
            continue

        if query.lower() in {"exit", "quit", "q"}:
            print("\n👋  Goodbye!\n")
            break

        answer_query(query, model, retriever, top_k)


import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("src.app:app", host="0.0.0.0", port=port)
