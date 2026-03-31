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
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
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

_indexing_in_progress: bool = False
_indexing_error: Optional[str] = None
_indexing_repo_path: Optional[str] = None
_indexing_lock = threading.Lock()

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI GitHub Repository Brain API",
    description="RAG-powered code question answering",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    print("API started successfully")
    print("Server running on port 8000")


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

class GenerateReadmeRequest(BaseModel):
    repo_path: str

class GenerateReadmeResponse(BaseModel):
    readme_content: str

class ReadmeAnalysis(BaseModel):
    missing_sections: List[str]
    improvements: List[str]
    score_existing: int
    score_generated: int

class CompareReadmeRequest(BaseModel):
    repo_path: str

class CompareReadmeResponse(BaseModel):
    existing_readme: str
    generated_readme: str
    analysis: ReadmeAnalysis

GenerateRequirementsResponse.model_rebuild()


class LoadRepoResponse(BaseModel):
    status: str
    files_found: int
    chunks_created: int
    vectors_indexed: int
    message: str | None = None


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
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"status": "ok"}


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
            ["git", "clone", "--depth", "1", repo_url, str(local_path)],
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
    if not repo:
        raise HTTPException(status_code=400, detail="Repository path cannot be empty")
    
    if repo.startswith("http://") or repo.startswith("https://"):
        repo = clone_repo(repo)

    if not Path(repo).exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {repo}")

    try:
        global _indexing_in_progress, _indexing_error, _indexing_repo_path

        # Quick scan (fast path) for immediate response
        quick_files = get_code_files(repo, max_selected_files=50, include_content=False)
        print("Quick scan done")

        # Always set repo_path, but clear current index until background finishes
        _repo_path = repo
        _model = None
        _retriever = None

        def background_index(repo_path: str) -> None:
            global _model, _retriever, _repo_path
            global _indexing_in_progress, _indexing_error, _indexing_repo_path

            try:
                files = get_code_files(repo_path, max_selected_files=200)
                if not files:
                    with _indexing_lock:
                        _indexing_error = "Repository contains unsupported or non-code files"
                    return

                chunks = chunk_code_files(files)
                if not chunks:
                    with _indexing_lock:
                        _indexing_error = "Repository contains unsupported or non-code files"
                    return

                model = load_model()
                embedded = generate_embeddings(chunks, model, batch_size=64)

                retriever = FAISSRetriever()
                retriever.build_index(embedded)

                _model = model
                _retriever = retriever
                _repo_path = repo_path

            except Exception as exc:
                logger.exception("Background indexing failed")
                with _indexing_lock:
                    _indexing_error = str(exc)
            finally:
                with _indexing_lock:
                    _indexing_in_progress = False
                    _indexing_repo_path = None

        # Start background work only if not already running for this repo
        start_thread = False
        with _indexing_lock:
            if not _indexing_in_progress:
                _indexing_in_progress = True
                _indexing_error = None
                _indexing_repo_path = repo
                start_thread = True
            elif _indexing_repo_path == repo:
                # Already indexing same repo; do not start another thread
                start_thread = False
            else:
                # Indexing something else; still return fast but don't spawn extra
                start_thread = False

        if start_thread:
            print("Background indexing started")
            t = threading.Thread(target=background_index, args=(repo,), daemon=True)
            t.start()

        return LoadRepoResponse(
            status="success",
            files_found=len(quick_files),
            chunks_created=0,
            vectors_indexed=0,
            message="Repository loaded, indexing in progress",
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

    global _indexing_in_progress, _indexing_error
    with _indexing_lock:
        indexing = _indexing_in_progress
        indexing_error = _indexing_error

    if indexing:
        raise HTTPException(
            status_code=400,
            detail="Repository loaded, indexing in progress. Try again shortly."
        )

    if indexing_error and (_model is None or _retriever is None):
        raise HTTPException(status_code=400, detail=f"Indexing failed: {indexing_error}")

    if _model is None or _retriever is None:
        raise HTTPException(
            status_code=400,
            detail="No repository loaded. Call POST /load_repo first."
        )

    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

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
    try:
        repo = body.repo_path.strip()
        if not repo:
            raise HTTPException(status_code=400, detail="Repository path cannot be empty")

        if repo.startswith("http://") or repo.startswith("https://"):
            repo = clone_repo(repo)

        if not Path(repo).exists():
            raise HTTPException(status_code=400, detail=f"Path does not exist: {repo}")

        logger.info("Generating requirements...")
        print("Generating requirements...")

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


@app.post("/generate_readme", response_model=GenerateReadmeResponse)
def api_generate_readme(body: GenerateReadmeRequest):
    """
    Generate a REAL README.md using repository structure and code context via Gemini LLM.
    """
    try:
        repo = body.repo_path.strip()
        if not repo:
            raise HTTPException(status_code=400, detail="Repository path cannot be empty")

        if repo.startswith("http://") or repo.startswith("https://"):
            repo = clone_repo(repo)

        if not Path(repo).exists():
            raise HTTPException(status_code=400, detail=f"Path does not exist: {repo}")

        logger.info(f"Generating REAL README for {repo}...")
        
        # Step 1: Scan files for structure
        files = get_code_files(repo)
        if not files:
            raise HTTPException(status_code=400, detail="No code files found in repository.")
            
        # Step 2: Use actual code chunks for deep context
        chunks = chunk_code_files(files[:50]) # Use first 50 files for speed/RAM
        context_chunks = chunks[:25] # Sample 25 chunks for LLM
        context = "\n\n".join([f"File: {c['file_path']}\nContent:\n{c['content'][:1000]}" for c in context_chunks])

        # Step 3: Build folder structure
        unique_files = list({f['path'] for f in files})
        folder_structure = "\n".join([f"  - {f}" for f in unique_files[:50]])

        # Step 4: Call LLM (Gemini)
        project_name = Path(repo).name
        print(f"[API] 🤖 Generating README for {project_name}...")
        
        sys_prompt = (
            "You are a senior software engineer and technical writer. "
            "Your task is to generate a comprehensive, professional README.md for a GitHub repository. "
            "Use markdown formatting with emojis for headers. Do NOT include placeholder text."
        )

        user_prompt = f"""Generate a high-quality README.md for the repository '{project_name}'.

Folder Structure:
{folder_structure}

Key Code Context:
{context}

Include:
1. Title & Badges
2. Detailed Overview
3. Core Features
4. Tech Stack (languages, frameworks)
5. Step-by-step Installation & Setup
6. Usage Examples
7. File Structure
8. License (MIT)
"""

        models_to_try = [
            "gemini/gemini-2.0-flash",
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-pro",
        ]
        
        readme_content = None
        last_error = None

        for model_name in models_to_try:
            try:
                response = litellm.completion(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=3000
                )
                readme_content = response.choices[0].message.content
                break
            except Exception as e:
                last_error = e
                continue

        if not readme_content or len(readme_content.strip()) < 100:
            return GenerateReadmeResponse(readme_content="# README Generation Failed\n\nPlease check your API key or repo content.")

        return GenerateReadmeResponse(readme_content=readme_content)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error generating README")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/compare_readme", response_model=CompareReadmeResponse)
def api_compare_readme(body: CompareReadmeRequest):
    """
    Compare existing README.md with an AI-generated README and provide analysis.
    """
    try:
        repo = body.repo_path.strip()
        if not repo:
            raise HTTPException(status_code=400, detail="Repository path cannot be empty")

        if repo.startswith("http://") or repo.startswith("https://"):
            repo = clone_repo(repo)

        repo_path_obj = Path(repo)
        if not repo_path_obj.exists():
            raise HTTPException(status_code=400, detail=f"Path does not exist: {repo}")

        # 1. Detect if repo has existing README
        existing_readme_content = ""
        readme_candidates = ["README.md", "readme.md", "Readme.md", "README"]
        found_readme = False
        for candidate in readme_candidates:
            candidate_path = repo_path_obj / candidate
            if candidate_path.exists() and candidate_path.is_file():
                try:
                    with open(candidate_path, "r", encoding="utf-8") as f:
                        existing_readme_content = f.read()
                    found_readme = True
                    break
                except Exception:
                    pass
                
        if not found_readme:
            raise HTTPException(status_code=404, detail="No README found in the repository root.")

        # 2. Generate new README by reusing the logic (this relies on the same endpoint code)
        # We call our own api_generate_readme
        try:
            gen_response = api_generate_readme(GenerateReadmeRequest(repo_path=body.repo_path))
            generated_readme_content = gen_response.readme_content
        except HTTPException as e:
            raise e
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to generate new README: {str(exc)}")

        # 3. Compare both using LLM
        sys_prompt = "You are an expert technical writer and code reviewer."
        user_prompt = f"""Compare the following two GitHub READMEs for a project.

Existing README:
```markdown
{existing_readme_content}
```

Generated README:
```markdown
{generated_readme_content}
```

Perform an analysis comparing the two. Focus on:
- Title quality
- Missing sections (Installation, Usage, Architecture, Examples)
- Clarity
- Structure

Score both READMEs out of 10.

Return ONLY a valid JSON object matching exactly this schema, without any markdown formatting or code blocks:
{{
  "missing_sections": ["string"],
  "improvements": ["string"],
  "score_existing": integer,
  "score_generated": integer
}}"""

        models_to_try = [
            "gemini/gemini-2.5-flash",
            "gemini/gemini-2.0-flash",
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-flash-latest"
        ]
        
        analysis_data = None
        last_error = None

        for model_name in models_to_try:
            try:
                response = litellm.completion(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    # some litellm providers support response_format={"type": "json_object"} but text parsing is safer across all gemini models
                )
                raw_content = response.choices[0].message.content
                if raw_content.startswith("```json"):
                    raw_content = raw_content[7:]
                if raw_content.startswith("```"):
                    raw_content = raw_content[3:]
                if raw_content.endswith("```"):
                    raw_content = raw_content[:-3]
                    
                analysis_dict = json.loads(raw_content.strip())
                
                # Simple validation to avoid 500 crashes
                if "missing_sections" in analysis_dict and "score_existing" in analysis_dict:
                    analysis_data = ReadmeAnalysis(
                        missing_sections=analysis_dict.get("missing_sections", []),
                        improvements=analysis_dict.get("improvements", []),
                        score_existing=int(analysis_dict.get("score_existing", 0)),
                        score_generated=int(analysis_dict.get("score_generated", 0))
                    )
                    break
            except Exception as e:
                last_error = e
                continue

        if not analysis_data:
            analysis_data = ReadmeAnalysis(
                missing_sections=["Analysis failed."],
                improvements=[f"LLM Error: {last_error}"],
                score_existing=0,
                score_generated=0
            )

        return CompareReadmeResponse(
            existing_readme=existing_readme_content,
            generated_readme=generated_readme_content,
            analysis=analysis_data
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error comparing README")
        raise HTTPException(status_code=500, detail=str(exc))
        
# ─────────────────────────────────────────────────────────────
# 🔥 WEBHOOK + README STORAGE (FINAL STABLE VERSION)
# ─────────────────────────────────────────────────────────────

from fastapi import Request

@app.post("/webhook/github")
async def github_webhook(request: Request):
    """
    GitHub webhook endpoint:
    - Receives push event
    - Clones or updates repo
    - Generates README
    - Stores it locally
    """
    try:
        payload = await request.json()

        # ✅ Only process push events
        if "commits" not in payload:
            return {"status": "ignored", "message": "Not a push event"}

        if "repository" not in payload:
            return {"status": "ignored", "message": "No repository data"}

        repo_url = payload["repository"]["clone_url"]
        repo_name = repo_url.split("/")[-1].replace(".git", "")

        print(f"[Webhook] Push received for: {repo_name}")

        # ✅ Clone repo
        local_path = clone_repo(repo_url)

        # 🔥 Ensure latest code is pulled (UPDATED FIX)
        try:
            result = subprocess.run(
                ["git", "-C", local_path, "pull"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print("[Webhook] Repo updated:", result.stdout)
            else:
                print("[Webhook] Pull error:", result.stderr)

        except Exception as e:
            print("[Webhook] Pull failed:", str(e))

        # ✅ Generate README
        readme_response = api_generate_readme(
            GenerateReadmeRequest(repo_path=local_path)
        )
        readme_content = readme_response.readme_content

        # ✅ Store README
        save_dir = Path("data/generated_readmes")
        save_dir.mkdir(parents=True, exist_ok=True)

        file_path = save_dir / f"{repo_name}.md"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(readme_content)

        print(f"[Webhook] README stored at: {file_path}")

        return {
            "status": "success",
            "repo": repo_name,
            "stored_at": str(file_path)
        }

    except Exception as e:
        print("[Webhook Error]", str(e))
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/get_saved_readme")
def get_saved_readme(repo_name: str):
    """
    Fetch stored README generated via webhook
    """
    try:
        file_path = Path("data/generated_readmes") / f"{repo_name}.md"

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="README not found")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "repo": repo_name,
            "content": content
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────
# 📥 GET SAVED README API (REQUIRED FOR FRONTEND)
# ─────────────────────────────────────────────────────────────

@app.get("/get_readme")
def get_readme(repo_name: str):
    """
    Fetch generated README for frontend
    """
    try:
        file_path = Path("data/generated_readmes") / f"{repo_name}.md"

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="README not found")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "content": content
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
