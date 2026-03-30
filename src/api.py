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
    allow_origins=["*"],
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
    repo = body.repo_path.strip()
    if not repo:
        raise HTTPException(status_code=400, detail="Repository path cannot be empty")

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


@app.post("/generate_readme", response_model=GenerateReadmeResponse)
def api_generate_readme(body: GenerateReadmeRequest):
    """
    Generate a README.md using repository structure and dependencies data.
    """
    repo = body.repo_path.strip()
    if not repo:
        raise HTTPException(status_code=400, detail="Repository path cannot be empty")

    if repo.startswith("http://") or repo.startswith("https://"):
        repo = clone_repo(repo)

    if not Path(repo).exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {repo}")

    logger.info("Generating README...")
    print("Generating README...")

    try:
        # Step 1: Use repo_parser -> get files
        files = get_code_files(repo)
        
        # Step 2 & 3: Use dependency_analyzer -> get deps & entry points
        req_data = generate_requirements(repo)

        # Step 4: Build structured context
        file_tree = []
        for f in files[:50]: # Limit to 50 files for context fitting
            file_tree.append(f['path'])
        
        context_data = {
            "files": file_tree,
            "dependencies": {
                "python": req_data.get("python", []),
                "javascript": req_data.get("javascript", [])
            },
            "entry_points": req_data.get("entry_points", {})
        }

        # Step 5: Send to LLM with prompt
        project_name = Path(repo).name

        sys_prompt = "You are an expert software engineer and technical writer."
        user_prompt = f"""Generate a high-quality, professional, GitHub-ready README.md using the provided data. Do NOT hallucinate technologies or assume frameworks not present.

Project Name: {project_name}

Project Data:
{context_data}

Requirements for the README:

1. Title:
   - Use the repository name dynamically.
   - Format: "# {project_name}"
   - Avoid generic titles like "Project Documentation".

2. Add the following structured sections:

## 📌 Overview
- What the project does (clear, concise).
- Use repo content and detected purpose.

## 🏗 Architecture
- Explain the system pipeline clearly with bullet points, focusing on:
  - Repo Parser
  - Chunker
  - Embedder
  - FAISS Retriever
  - LLM Layer

## 🛠 Tech Stack
- Split into:
  - Python
  - JavaScript (if exists)
- Use detected dependencies.

## 🚀 Installation
For Python, include:
```bash
python -m venv .venv
# activate env
pip install -r requirements.txt
```
For JS (if exists), include:
```bash
npm install
```

## ▶️ Usage
- Example command (e.g., `python src/app.py --repo <path>` or `uvicorn ...`).
- Explain what the user can ask or do.

## 💡 Example
- Show a sample question + answer.

## 📂 Project Structure
- Show key folders explicitly: src/, frontend/, data/ (based on files detected).

## ⚙️ Features
- AI code understanding
- FAISS search
- Dependency generator
- Setup guide
- README generator

3. Tone:
- Clean and Professional.
- No generic AI text or conversational filler (e.g. "Here is your README").
- Concise but informative.

Output ONLY clean markdown string compatible with GitHub README.md. Do not wrap in ```markdown if possible."""

        models_to_try = [
            "gemini/gemini-2.5-flash",
            "gemini/gemini-2.0-flash",
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-flash-latest",
            "gemini/gemini-1.5-pro",
        ]
        
        readme_content: Optional[str] = None
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
                readme_content = response.choices[0].message.content
                break
            except Exception as e:
                last_error = e
                continue

        if not readme_content:
            readme_content = (
                f"# Error Generating README\n\n"
                f"[LLM Error: {last_error}]\n"
                "Make sure GEMINI_API_KEY is set in your .env file."
            )
            
        # Optional: remove ```markdown and ``` wrappers if present
        if readme_content.startswith("```markdown"):
            readme_content = readme_content[len("```markdown"):].strip()
            if readme_content.endswith("```"):
                readme_content = readme_content[:-3].strip()
        elif readme_content.startswith("```"):
            readme_content = readme_content[len("```"):].strip()
            if readme_content.endswith("```"):
                readme_content = readme_content[:-3].strip()

        # Step 6: Return markdown string
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


