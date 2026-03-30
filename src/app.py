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
import numpy as np
import os
import subprocess
from typing import List, Dict, Optional
from dotenv import load_dotenv
from contextlib import contextmanager

load_dotenv()

# ── FastAPI ───────────────────────────────────────────────────────────────────
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Make sure sibling modules in src/ are importable ──────────────────────────
from repo_parser import get_code_files           # type: ignore[import]
from chunker import chunk_code_files             # type: ignore[import]
from embedder import load_model, generate_embeddings  # type: ignore[import]
from retriever import FAISSRetriever             # type: ignore[import]
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

# ── Global State (pipeline cache) ─────────────────────────────────────────────
_pipeline_cache: Dict[str, tuple] = {}

@contextmanager
def get_cached_pipeline(repo_path: str, top_k: int = 3):
    """Cache pipelines to avoid rebuilding on every query."""
    if repo_path not in _pipeline_cache:
        model, retriever = build_pipeline(repo_path, top_k)
        _pipeline_cache[repo_path] = (model, retriever)
    model, retriever = _pipeline_cache[repo_path]
    yield model, retriever


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
      3. Load the embedding model.
      4. Generate embeddings for every chunk.
      5. Build the FAISS index.

    Returns:
        model      : SentenceTransformer (reused for query embedding)
        retriever  : FAISSRetriever (ready to search)
        top_k      : int (passed through for convenience)
    """
    print("\n🔍  Scanning repository ...")
    files = get_code_files(repo_path)
    if not files:
        print(f"❌  No supported code files found at: {repo_path}")
        sys.exit(1)
    print(f"    ✓ {len(files)} files found")

    print("✂️   Chunking files ...")
    chunks = chunk_code_files(files)
    print(f"    ✓ {len(chunks)} chunks created")

    print("🤖  Loading embedding model (all-MiniLM-L6-v2) ...")
    model = load_model()
    print("    ✓ Model ready")

    print("⚡  Generating embeddings ...")
    embedded = generate_embeddings(chunks, model, batch_size=64)
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
    retriever: FAISSRetriever,
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
            "gemini/gemini-2.5-flash",
            "gemini/gemini-2.5-pro",
            "gemini/gemini-2.0-flash",
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-flash-latest",
            "gemini/gemini-1.5-pro",
            "gemini/gemini-1.5-pro-latest",
            "gemini/gemini-1.5-flash-001",
            "gemini/gemini-1.5-flash-002",
            "gemini/gemini-pro"
        ]
        explanation = None
        last_error = None
        
        for model_name in models_to_try:
            try:
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
        
        files_count = len(files)
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
        
        # Generate embeddings and build index
        try:
            print(f"[API] 🤖 Loading embedding model...")
            model = load_model()
            
            print(f"[API] ⚡ Generating {chunks_count} embeddings...")
            embedded = generate_embeddings(chunks, model, batch_size=64)
            
            print(f"[API] 📦 Building FAISS index...")
            retriever = FAISSRetriever()
            retriever.build_index(embedded)
        except Exception as e:
            print(f"[API] ✗ Error building index: {e}")
            raise HTTPException(status_code=500, detail=f"Cannot build search index: {str(e)}")
        
        vectors_count = retriever.index.ntotal if retriever.index else 0  # type: ignore[union-attr]
        print(f"[API] ✓ {vectors_count} vectors indexed")
        
        # Cache for later use
        _pipeline_cache[repo_path] = (model, retriever)
        
        message = (
            f"Repository indexed successfully!\n"
            f"Files: {files_count} | Chunks: {chunks_count} | Vectors: {vectors_count}"
        )
        
        return {
            "status": "success",
            "files_found": files_count,
            "chunks_created": chunks_count,
            "vectors_indexed": vectors_count,
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
        
        # For now, we require a repo to be loaded first
        # In production, this might default to a main repo or require repo_path in request
        if not _pipeline_cache:
            raise HTTPException(status_code=400, detail="No repository loaded. Use /load_repo first.")
        
        # Use the first cached pipeline (in a real app, you'd track which repo is active)
        repo_path = list(_pipeline_cache.keys())[0]
        model, retriever = _pipeline_cache[repo_path]
        
        # Embed the question
        query_vec: np.ndarray = model.encode(
            [request.question], convert_to_numpy=True
        )[0].astype("float32")
        
        # Retrieve chunks
        results: List[Dict[str, str]] = retriever.retrieve(query_vec, top_k=request.top_k)
        
        if not results:
            print(f"[API] No results found for question")
            return {
                "explanation": "No relevant code sections found.",
                "retrieved_chunks": []
            }
        
        # Build context
        context_blocks = []
        for rank, chunk in enumerate(results, start=1):
            context_blocks.append(
                f"--- Code Section {rank} ---\n"
                f"File: {chunk['file_path']}\n"
                f"Content:\n{chunk['content']}\n"
            )
        context_str = "\n".join(context_blocks)
        
        # Call LLM
        sys_prompt = "You are a helpful coding assistant. Using the following code context, explain the answer to the user's question."
        user_prompt = f"Context:\n{context_str}\n\nQuestion: {request.question}"
        
        print(f"[API] 🤖 Calling LLM...")
        explanation = None
        last_error = None
        
        models_to_try = [
            "gemini/gemini-2.5-flash",
            "gemini/gemini-2.5-pro",
            "gemini/gemini-2.0-flash",
            "gemini/gemini-1.5-flash",
        ]
        
        for model_name in models_to_try:
            try:
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
                score=str(chunk.get("score", "N/A"))
            )
            for chunk in results
        ]
        
        return {
            "explanation": explanation,
            "retrieved_chunks": chunk_results
        }
    except Exception as e:
        print(f"[API] ✗ Error in /ask: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate_requirements", response_model=GenerateRequirementsResponse)
async def generate_requirements(request: GenerateRequirementsRequest):
    """Generate requirements from repository analysis."""
    try:
        print(f"[API] POST /generate_requirements - {request.repo_path}")
        # Placeholder implementation
        return {
            "python": [],
            "javascript": [],
            "source": "placeholder",
            "entry_points": {}
        }
    except Exception as e:
        print(f"[API] ✗ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate_readme", response_model=GenerateReadmeResponse)
async def generate_readme(request: GenerateReadmeRequest):
    """Generate README for repository."""
    try:
        print(f"[API] POST /generate_readme - {request.repo_path}")
        # Placeholder implementation
        return {"readme_content": "# README\n\nPlaceholder content"}
    except Exception as e:
        print(f"[API] ✗ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/compare_readme", response_model=CompareReadmeResponse)
async def compare_readme(request: CompareReadmeRequest):
    """Compare existing and generated README."""
    try:
        print(f"[API] POST /compare_readme - {request.repo_path}")
        # Placeholder implementation
        return {
            "existing_readme": "",
            "generated_readme": "# README\n\nPlaceholder",
            "analysis": {
                "missing_sections": [],
                "improvements": [],
                "score_existing": 0.0,
                "score_generated": 0.0
            }
        }
    except Exception as e:
        print(f"[API] ✗ Error: {e}")
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
