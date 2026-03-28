"""
api.py — AI GitHub Repository Brain · FastAPI Backend
======================================================
Exposes two REST endpoints:

  POST /load_repo   – parse, chunk, embed and index a repository
  POST /ask         – answer a question using retrieval + Gemini LLM

Run with:
  uvicorn src.api:app --reload
"""

import os
import sys
import logging
import numpy as np
import subprocess
import urllib.parse
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# ── Make sure sibling modules in src/ are importable ──────────────────────────
src_dir = str(Path(__file__).resolve().parent)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from repo_parser import get_code_files            # type: ignore[import]
from chunker import chunk_code_files              # type: ignore[import]
from embedder import load_model, generate_embeddings  # type: ignore[import]
from retriever import FAISSRetriever              # type: ignore[import]
from dependency_analyzer import generate_requirements  # type: ignore[import]
import litellm

# ── Startup ───────────────────────────────────────────────────────────────────
load_dotenv()
logging.basicConfig(level=logging.WARNING)
litellm.suppress_debug_info = True
logger = logging.getLogger(__name__)

# ── In-process pipeline state (populated by /load_repo) ──────────────────────
_model = None
_retriever: Optional[FAISSRetriever] = None
_repo_path: Optional[str] = None

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI GitHub Repository Brain API",
    description="RAG-powered code question answering",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response schemas ────────────────────────────────────────────────

class LoadRepoRequest(BaseModel):
    repo_path: str


class GenerateRequirementsRequest(BaseModel):
    repo_path: str


class GenerateRequirementsResponse(BaseModel):
    python: List[str] = []
    javascript: List[str] = []
    source: str = "detected_from_files"
    entry_points: Dict[str, str] = {}

GenerateRequirementsResponse.model_rebuild()


class LoadRepoResponse(BaseModel):
    status: str
    files_found: int
    chunks_created: int
    vectors_indexed: int


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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "AI GitHub Repository Brain API is running 🧠"}


def clone_repo(repo_url: str) -> str:
    """
    Clones a GitHub repository into a local data/repos/ directory.
    Returns the local path.
    """
    try:
        # Extract repo name from URL
        parsed_url = urllib.parse.urlparse(repo_url)
        path_parts = parsed_url.path.strip("/").split("/")
        if len(path_parts) < 2:
            raise ValueError("Invalid GitHub URL format.")
            
        repo_name = path_parts[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
            
        repos_dir = Path("data/repos")
        repos_dir.mkdir(parents=True, exist_ok=True)
        
        local_path = repos_dir / repo_name
        
        if local_path.exists():
            logger.info(f"Repository already exists locally at {local_path}. Skipping clone.")
            print(f"Repository already exists locally at {local_path}. Skipping clone.")
            return str(local_path)
            
        logger.info(f"Cloning repository from {repo_url} to {local_path}...")
        print("Cloning repository...")
        
        result = subprocess.run(
            ["git", "clone", repo_url, str(local_path)],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"Clone failed: {result.stderr}")
            raise RuntimeError(f"Failed to clone repository: {result.stderr}")
            
        logger.info("Clone completed")
        print("Clone completed")
        return str(local_path)
        
    except Exception as e:
        logger.error(f"Error cloning repository: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to clone repository: {str(e)}")


@app.post("/load_repo", response_model=LoadRepoResponse)
def load_repo(body: LoadRepoRequest):
    """
    Parse, chunk, embed and FAISS-index a repository.
    Must be called before /ask.
    """
    global _model, _retriever, _repo_path

    repo = body.repo_path.strip()
    if repo.startswith("http://") or repo.startswith("https://"):
        repo = clone_repo(repo)

    if not Path(repo).exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {repo}")

    try:
        files = get_code_files(repo)
        if not files:
            raise HTTPException(
                status_code=400,
                detail="No supported code files found in the repository."
            )

        chunks = chunk_code_files(files)

        model = load_model()
        embedded = generate_embeddings(chunks, model, batch_size=64)

        retriever = FAISSRetriever()
        retriever.build_index(embedded)

        # Store in module-level state
        _model = model
        _retriever = retriever
        _repo_path = repo

        return LoadRepoResponse(
            status="success",
            files_found=len(files),
            chunks_created=len(chunks),
            vectors_indexed=retriever.index.ntotal,  # type: ignore[union-attr]
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error during load_repo")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest):
    """
    Answer a question about the loaded repository.
    Requires /load_repo to have been called first.
    """
    global _model, _retriever

    if _model is None or _retriever is None:
        raise HTTPException(
            status_code=400,
            detail="No repository loaded. Call POST /load_repo first."
        )

    # 1. Embed the question
    query_vec: np.ndarray = _model.encode(
        [body.question], convert_to_numpy=True
    )[0].astype("float32")

    # 2. Retrieve top-k chunks
    results = _retriever.retrieve(query_vec, top_k=body.top_k)
    if not results:
        raise HTTPException(status_code=404, detail="No relevant code chunks found.")

    # 3. Build context for the LLM
    context_blocks = []
    for rank, chunk in enumerate(results, start=1):
        context_blocks.append(
            f"--- Code Section {rank} ---\n"
            f"File: {chunk['file_path']}\n"
            f"Content:\n{chunk['content']}\n"
        )
    context_str = "\n".join(context_blocks)

    sys_prompt = (
        "You are a helpful coding assistant. Using the following code context, "
        "explain the answer to the user's question clearly and concisely."
    )
    user_prompt = f"Context:\n{context_str}\n\nQuestion: {body.question}"

    # 4. Call LLM — try Gemini models in priority order
    models_to_try = [
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.0-flash",
        "gemini/gemini-1.5-flash",
        "gemini/gemini-1.5-flash-latest",
        "gemini/gemini-1.5-pro",
    ]
    explanation: Optional[str] = None
    last_error: Optional[Exception] = None

    for model_name in models_to_try:
        try:
            response = litellm.completion(
                model=model_name,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            explanation = response.choices[0].message.content
            break
        except Exception as e:
            last_error = e
            continue

    if not explanation:
        explanation = (
            f"[LLM Error: {last_error}]\n"
            "Make sure GEMINI_API_KEY is set in your .env file."
        )

    # 5. Return structured response
    return AskResponse(
        explanation=explanation,
        retrieved_chunks=[
            ChunkResult(
                file_path=c["file_path"],
                chunk_id=c["chunk_id"],
                content=c["content"],
                score=c.get("score", "N/A"),
            )
            for c in results
        ],
    )


@app.post("/generate_requirements", response_model=GenerateRequirementsResponse)
def api_generate_requirements(body: GenerateRequirementsRequest):
    """
    Generate a list of Python dependencies for a given repository.
    Does not use the LLM or FAISS retriever.
    """
    repo = body.repo_path.strip()

    if repo.startswith("http://") or repo.startswith("https://"):
        repo = clone_repo(repo)

    if not Path(repo).exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {repo}")

    logger.info("Generating requirements...")
    print("Generating requirements...")

    try:
        # Run dependency analyzer
        result = generate_requirements(repo)
        
        logger.info("Requirements generated successfully")
        print("Requirements generated successfully")
        
        return GenerateRequirementsResponse(
            python=result.get("python") or [],
            javascript=result.get("javascript") or [],
            source=result.get("source") or "detected_from_files",
            entry_points=result.get("entry_points") or {}
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error generating requirements")
        raise HTTPException(status_code=500, detail=str(exc))

