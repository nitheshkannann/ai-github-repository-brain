import logging
import sys
import numpy as np
from pathlib import Path
from typing import List, Dict
from tqdm import tqdm
from sentence_transformers import SentenceTransformer

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Lightweight model for Render Free Tier (512MB RAM limit)
# L3 (~100-150MB RAM) vs L6 (~400-500MB RAM)
MODEL_NAME = "paraphrase-MiniLM-L3-v2"


def load_model(model_name: str = MODEL_NAME) -> SentenceTransformer:
    """
    Loads and returns a SentenceTransformer model.

    Args:
        model_name (str): HuggingFace model identifier.

    Returns:
        SentenceTransformer: The loaded embedding model.
    """
    logger.info(f"Loading embedding model: '{model_name}' (CPU mode) ...")
    model = SentenceTransformer(model_name, device="cpu")  # Force CPU — avoids GPU overhead on Render
    logger.info("Model loaded successfully.")
    return model


def generate_embeddings(
    chunks: List[Dict[str, str]],
    model: SentenceTransformer,
    batch_size: int = 8  # Small batch to avoid RAM spikes on Render Free Tier
) -> List[Dict]:
    """
    Converts a list of text chunks into vector embeddings.

    Each output dict contains everything from the input chunk plus an
    'embedding' key holding a numpy float32 array.

    Args:
        chunks (List[Dict[str, str]]): Output of chunker.chunk_code_files().
            Each dict must have 'file_path', 'chunk_id', and 'content'.
        model (SentenceTransformer): A loaded embedding model.
        batch_size (int): How many chunks to encode in one forward pass.
            Larger = faster but uses more memory.

    Returns:
        List[Dict]: List of dicts, each containing:
            - 'file_path'  (str)         : relative path to the source file
            - 'chunk_id'   (str)         : unique chunk identifier
            - 'content'    (str)         : raw text of the chunk
            - 'embedding'  (np.ndarray)  : float32 vector of shape (embedding_dim,)
    """
    if not chunks:
        logger.warning("No chunks provided, returning empty list.")
        return []

    logger.info(f"Generating embeddings for {len(chunks)} chunks (batch_size={batch_size}) ...")

    # Extract just the text content for the model
    texts: List[str] = [chunk['content'] for chunk in chunks]

    # encode() handles batching internally; show_progress_bar gives us a tqdm bar
    raw_embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
    )
    # Cast to float32 explicitly for consistency and FAISS compatibility
    embeddings: np.ndarray = raw_embeddings.astype("float32")

    # Stitch embeddings back onto the original chunk metadata
    embedded_chunks: List[Dict] = []
    for chunk, embedding in zip(chunks, embeddings):
        embedded_chunks.append({
            "file_path": chunk["file_path"],
            "chunk_id":  chunk["chunk_id"],
            "content":   chunk["content"],
            "embedding": embedding           # numpy float32 array
        })

    logger.info(f"Embedding complete. Vector dimension: {embeddings.shape[1]}")
    return embedded_chunks


# ---------------------------------------------------------------------------
# Full pipeline test — run with:  python src/embedder.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Make sure the src/ directory is importable
    src_dir = str(Path(__file__).resolve().parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    from repo_parser import get_code_files   # type: ignore[import]
    from chunker import chunk_code_files     # type: ignore[import]

    repo_root = str(Path(__file__).resolve().parent.parent)
    print(f"\n{'='*60}")
    print(f"  AI GitHub Repository Brain — Embedding Pipeline Test")
    print(f"{'='*60}\n")

    # ── Step 1: Parse ──────────────────────────────────────────
    print("Step 1: Scanning repository...")
    files = get_code_files(repo_root)
    print(f"  ✓ Found {len(files)} source files\n")

    # ── Step 2: Chunk ──────────────────────────────────────────
    print("Step 2: Chunking files...")
    chunks = chunk_code_files(files)
    print(f"  ✓ Created {len(chunks)} chunks\n")

    # ── Step 3: Load model ─────────────────────────────────────
    print("Step 3: Loading embedding model...")
    embedding_model = load_model(MODEL_NAME)
    print()

    # ── Step 4: Embed ──────────────────────────────────────────
    print("Step 4: Generating embeddings...")
    embedded = generate_embeddings(chunks, embedding_model)
    print()

    # ── Step 5: Summary ────────────────────────────────────────
    if embedded:
        sample = embedded[0]
        dim = len(sample["embedding"])
        dtype = sample["embedding"].dtype

        print(f"{'='*60}")
        print(f"  RESULTS")
        print(f"{'='*60}")
        print(f"  Total embedded chunks : {len(embedded)}")
        print(f"  Embedding dimension   : {dim}  (each chunk → {dim}-d vector)")
        print(f"  Embedding dtype       : {dtype}")
        print()
        print(f"  Sample chunk:")
        print(f"    file_path : {sample['file_path']}")
        print(f"    chunk_id  : {sample['chunk_id']}")
        print(f"    embedding : [{sample['embedding'][0]:.6f}, {sample['embedding'][1]:.6f}, "
              f"{sample['embedding'][2]:.6f}, ...] (showing first 3 values)")
        print(f"{'='*60}\n")
    else:
        print("No embeddings were generated.")
