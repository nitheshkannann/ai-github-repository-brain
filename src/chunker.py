import logging
import sys
import os
from pathlib import Path
from typing import List, Dict

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Chunking configuration ---
# A chunk should be roughly 300-500 characters long.
# We try to split at natural line boundaries when possible.
DEFAULT_CHUNK_SIZE = 400       # target characters per chunk
DEFAULT_CHUNK_OVERLAP = 50     # characters of overlap between adjacent chunks


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[str]:
    """
    Splits a long text string into smaller overlapping chunks.

    Strategy:
      1. Prefer splitting at line boundaries to keep logical code together.
      2. If a single line is longer than chunk_size, fall back to a hard split.
      3. Add a small overlap so context is not lost at chunk edges.

    Args:
        text (str): The raw text to split.
        chunk_size (int): Approximate maximum characters per chunk.
        overlap (int): Number of characters to repeat at the start of the next chunk.

    Returns:
        List[str]: A list of text chunks.
    """
    lines = text.splitlines(keepends=True)   # keep newline chars so content is authentic
    chunks: List[str] = []
    current_chunk = ""

    for line in lines:
        # If adding this line would bust the chunk size, save what we have and start a new chunk
        if len(current_chunk) + len(line) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Keep the last `overlap` characters to provide context continuity
            current_chunk = current_chunk[-overlap:] + line
        else:
            current_chunk += line

    # Don't forget the final remaining chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def chunk_code_files(
    code_files: List[Dict[str, str]],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP
) -> List[Dict[str, str]]:
    """
    Takes the output of repo_parser.get_code_files() and splits every file
    into smaller chunks, preserving file path metadata.

    Args:
        code_files (List[Dict[str, str]]): List of dicts with 'path' and 'content'.
        chunk_size (int): Approximate max characters per chunk.
        overlap (int): Overlap characters between consecutive chunks.

    Returns:
        List[Dict[str, str]]: A flat list of chunk dicts, each containing:
            - 'file_path' : relative file path (from repo root)
            - 'chunk_id'  : unique id in the form "<filename>_chunk_<N>"
            - 'content'   : the text of this chunk
    """
    all_chunks: List[Dict[str, str]] = []

    for file in code_files:
        file_path: str = file['path']
        content: str = file['content']

        # Skip empty files
        if not content.strip():
            logger.warning(f"Skipping empty file: {file_path}")
            continue

        text_chunks = chunk_text(content, chunk_size, overlap)

        # Use just the filename (without extension) as a readable prefix for chunk IDs
        file_basename = Path(file_path).stem

        for idx, chunk_text_content in enumerate(text_chunks):
            all_chunks.append({
                "file_path": file_path,
                "chunk_id": f"{file_basename}_chunk_{idx}",
                "content": chunk_text_content
            })

    logger.info(f"Created {len(all_chunks)} chunks from {len(code_files)} files.")
    return all_chunks


# ---------------------------------------------------------------------------
# Quick test — run with:  python src/chunker.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Add the src/ directory to the path so we can import repo_parser
    src_dir = str(Path(__file__).resolve().parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    from repo_parser import get_code_files  # type: ignore[import]

    # Point at the project root (one level above src/)
    repo_root = str(Path(__file__).resolve().parent.parent)
    print(f"Scanning repository at: {repo_root}\n")

    # Step 1: Parse the repo
    files = get_code_files(repo_root)
    print(f"Total files found     : {len(files)}")

    # Step 2: Chunk all files
    chunks = chunk_code_files(files)
    print(f"Total chunks created  : {len(chunks)}\n")

    # Step 3: Print a sample of the first 3 chunks
    print("=" * 60)
    print("SAMPLE CHUNKS (first 3)")
    print("=" * 60)
    for chunk in chunks[:3]:
        print(f"\nFile Path : {chunk['file_path']}")
        print(f"Chunk ID  : {chunk['chunk_id']}")
        print(f"Length    : {len(chunk['content'])} characters")
        print(f"Content Preview:\n{'-'*40}")
        preview: str = chunk['content']
        print(preview[:200])   # show up to 200 chars of the chunk
        print(f"{'-'*40}")
