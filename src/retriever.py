import logging
import sys
import numpy as np
import faiss
from pathlib import Path
from typing import List, Dict, Tuple

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class FAISSRetriever:
    """
    Builds a FAISS index from embedded chunks and retrieves the most
    semantically similar chunks for a given query embedding.

    Attributes:
        index     : The FAISS flat index (exact nearest-neighbour search).
        metadata  : List of dicts storing 'file_path', 'chunk_id', 'content'
                    in the same order as the FAISS index rows.
        dimension : Embedding vector dimension (e.g. 384 for all-MiniLM-L6-v2).
    """

    def __init__(self) -> None:
        self.index: faiss.IndexFlatL2 | None = None
        self.metadata: List[Dict[str, str]] = []
        self.dimension: int = 0

    def build_index(self, embedded_chunks: List[Dict]) -> None:
        """
        Builds the FAISS index from a list of embedded chunks.

        Args:
            embedded_chunks (List[Dict]): Output of embedder.generate_embeddings().
                Each dict must contain 'embedding' (np.ndarray), 'file_path',
                'chunk_id', and 'content'.
        """
        if not embedded_chunks:
            raise ValueError("Cannot build index from an empty list of chunks.")

        # Stack all embedding vectors into a 2-D float32 matrix  (N × D)
        vectors: np.ndarray = np.stack(
            [chunk["embedding"] for chunk in embedded_chunks]
        ).astype("float32")

        self.dimension = vectors.shape[1]

        # IndexFlatL2 → exact L2 (Euclidean) distance search, no compression
        # Great for small-to-medium repos; swap for IndexIVFFlat for very large repos
        self.index = faiss.IndexFlatL2(self.dimension)
        self.index.add(vectors)  # type: ignore[union-attr]

        # Keep metadata aligned with FAISS row indices
        self.metadata = [
            {
                "file_path": chunk["file_path"],
                "chunk_id":  chunk["chunk_id"],
                "content":   chunk["content"],
            }
            for chunk in embedded_chunks
        ]

        logger.info(
            f"FAISS index built: {self.index.ntotal} vectors, "  # type: ignore[union-attr]
            f"dimension={self.dimension}"
        )

    def retrieve(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5
    ) -> List[Dict[str, str]]:
        """
        Finds the top-k most similar chunks for a given query embedding.

        Args:
            query_embedding (np.ndarray): 1-D float32 vector for the query.
            top_k (int): Number of results to return.

        Returns:
            List[Dict[str, str]]: Top-k chunks, each with 'file_path',
                'chunk_id', 'content', and 'score' (L2 distance, lower = better).
        """
        if self.index is None:
            raise RuntimeError("Index has not been built yet. Call build_index() first.")

        # FAISS expects shape (1, D) for a single query
        query_vector = query_embedding.reshape(1, -1).astype("float32")

        # Search returns distances and indices arrays, both shape (1, top_k)
        distances, indices = self.index.search(query_vector, top_k)  # type: ignore[union-attr]

        results: List[Dict[str, str]] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                # FAISS uses -1 when there are fewer results than top_k
                continue
            result = dict(self.metadata[idx])   # copy so caller can't mutate metadata
            result["score"] = str(round(float(dist), 6))
            results.append(result)

        return results


# ---------------------------------------------------------------------------
# Full pipeline test — run with:  python src/retriever.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Make src/ importable
    src_dir = str(Path(__file__).resolve().parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    from repo_parser import get_code_files    # type: ignore[import]
    from chunker import chunk_code_files      # type: ignore[import]
    from embedder import load_model, generate_embeddings  # type: ignore[import]

    repo_root = str(Path(__file__).resolve().parent.parent)

    print(f"\n{'='*60}")
    print(f"  AI GitHub Repository Brain — Retriever Pipeline Test")
    print(f"{'='*60}\n")

    # ── Step 1: Parse ──────────────────────────────────────────
    print("Step 1: Scanning repository...")
    files = get_code_files(repo_root)
    print(f"  ✓ Found {len(files)} source files\n")

    # ── Step 2: Chunk ──────────────────────────────────────────
    print("Step 2: Chunking files...")
    chunks = chunk_code_files(files)
    print(f"  ✓ Created {len(chunks)} chunks\n")

    # ── Step 3: Embed ──────────────────────────────────────────
    print("Step 3: Loading model & embedding chunks...")
    model = load_model()
    embedded = generate_embeddings(chunks, model)
    print(f"  ✓ Embedded {len(embedded)} chunks  (dim={len(embedded[0]['embedding'])})\n")

    # ── Step 4: Build FAISS index ──────────────────────────────
    print("Step 4: Building FAISS index...")
    retriever = FAISSRetriever()
    retriever.build_index(embedded)
    print(f"  ✓ Index ready with {retriever.index.ntotal} vectors\n")  # type: ignore[union-attr]

    # ── Step 5: Run a test query ───────────────────────────────
    TEST_QUERY = "how does the chunking function split code into pieces?"
    print(f"Step 5: Running test query...")
    print(f"  Query: \"{TEST_QUERY}\"\n")

    # Embed the query using the same model
    query_embedding = model.encode([TEST_QUERY], convert_to_numpy=True)[0].astype("float32")

    top_results = retriever.retrieve(query_embedding, top_k=3)

    print("=" * 60)
    print("  TOP 3 RESULTS")
    print("=" * 60)
    for rank, result in enumerate(top_results, start=1):
        print(f"\n  [{rank}] {result['file_path']}  (chunk: {result['chunk_id']})")
        print(f"      L2 distance (lower = more similar): {result['score']}")
        print(f"      Content preview:")
        print(f"      {'-'*50}")
        # Show first 200 chars, indented for readability
        preview: str = result["content"]
        for line in preview[:200].splitlines():
            print(f"        {line}")
        print(f"      {'-'*50}")

    print(f"\n{'='*60}\n")
