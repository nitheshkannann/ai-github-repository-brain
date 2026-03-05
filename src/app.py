"""
app.py — AI GitHub Repository Brain
=====================================
Main CLI application. Ask questions about a codebase in plain English and get
the most relevant code sections as answers.

Usage:
    python src/app.py [--repo PATH] [--top-k N]

Arguments:
    --repo   Path to the repository to analyse (default: project root)
    --top-k  Number of code chunks to retrieve per query (default: 3)
"""

import sys
import argparse
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict

# ── Make sure sibling modules in src/ are importable ──────────────────────────
src_dir = str(Path(__file__).resolve().parent)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from repo_parser import get_code_files           # type: ignore[import]
from chunker import chunk_code_files             # type: ignore[import]
from embedder import load_model, generate_embeddings  # type: ignore[import]
from retriever import FAISSRetriever             # type: ignore[import]

# Only show WARNING+ from libraries so our own prints stay clean
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# ── Build the pipeline ────────────────────────────────────────────────────────

def build_pipeline(repo_path: str, top_k: int):
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
    Embeds the query, retrieves the top-k chunks from FAISS, and pretty-prints
    the results to the terminal.
    """
    # Embed the query with the same model used for the chunks
    query_vec: np.ndarray = model.encode(
        [query], convert_to_numpy=True
    )[0].astype("float32")

    results: List[Dict[str, str]] = retriever.retrieve(query_vec, top_k=top_k)

    if not results:
        print("\n  (No results found)\n")
        return

    print(f"\n{'─'*60}")
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


def main() -> None:
    args = parse_args()
    repo_path = args.repo
    top_k     = args.top_k

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


if __name__ == "__main__":
    main()
