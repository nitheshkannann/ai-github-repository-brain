import os
import logging
from pathlib import Path
from typing import List, Dict

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.go', '.cpp', '.c', '.cs',
    '.json', '.md', '.yaml', '.yml', '.toml'
}

# Standard directories to ignore when scanning
IGNORED_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".next",
    "venv",
}

MAX_SELECTED_FILES = 200
MAX_FILE_SIZE_BYTES = 1_000_000

def get_code_files(
    repo_path: str,
    max_selected_files: int = MAX_SELECTED_FILES,
    include_content: bool = True,
) -> List[Dict[str, str]]:
    """
    Scans a local repository directory and returns the content of all supported code files.
    
    Args:
        repo_path (str): The local path to the repository directory.
        
    Returns:
        List[Dict[str, str]]: A list of dictionaries. Each dictionary contains:
            - 'path': The relative file path.
            - 'content': The text content of the file.
    """
    repo_path_obj = Path(repo_path)
    
    if not repo_path_obj.exists() or not repo_path_obj.is_dir():
        logger.error(f"The repository path does not exist or is not a directory: {repo_path}")
        raise ValueError(f"Invalid repository path: {repo_path}")
        
    if max_selected_files <= 0:
        max_selected_files = 0

    code_files: List[Dict[str, str]] = []
    ignored_dir_count = 0
    total_files_found = 0
    
    logger.info(f"Scanning repository at '{repo_path}' for files with extensions: {', '.join(SUPPORTED_EXTENSIONS)}")
    
    # Walk through all directories and files in the repo path
    for root, dirs, files in os.walk(repo_path_obj):
        # Modify dirs in-place to skip ignored directories (optimization for os.walk)
        # Using clear() + extend() instead of slice assignment to keep type checkers happy
        filtered = []
        for d in dirs:
            if d in IGNORED_DIRS:
                ignored_dir_count += 1
            else:
                filtered.append(d)
                
        dirs.clear()
        dirs.extend(filtered)
            
        for file in files:
            # Skip hidden files
            if file.startswith('.'):
                continue

            total_files_found += 1
                
            file_path = Path(root) / file
            
            # Check if the file has a supported extension
            if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                try:
                    try:
                        if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                            continue
                    except Exception:
                        continue

                    content = ""
                    if include_content:
                        # Read the file content
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                    # Calculate path relative to the repository root for clean output
                    relative_path = file_path.relative_to(repo_path_obj)
                    
                    code_files.append({
                        # Use forward slashes for cross-platform consistency
                        'path': str(relative_path).replace('\\', '/'),
                        'content': content
                    })

                    if max_selected_files and len(code_files) >= max_selected_files:
                        print("Total files found:", total_files_found)
                        print("Code files selected:", len(code_files))
                        logger.info(
                            f"Reached max_selected_files={max_selected_files}. Stopping scan early."
                        )
                        return code_files
                except UnicodeDecodeError:
                    logger.warning(f"Skipping file {file_path} due to encoding issues (not valid UTF-8).")
                except Exception as e:
                    logger.warning(f"Could not read file {file_path}: {e}")
                    
    print("Total files found:", total_files_found)
    print("Code files selected:", len(code_files))
    logger.info(f"Successfully loaded {len(code_files)} code files. Ignored {ignored_dir_count} directories.")
    return code_files

if __name__ == "__main__":
    # Use Path.resolve() for reliable, absolute path resolution on all platforms.
    # This file lives at `src/repo_parser.py`, so .parent gives `src/` and
    # .parent.parent gives the project root.
    current_repo = Path(__file__).resolve().parent.parent
    print(f"Testing repo_parser on: {current_repo}\n")
    
    if not current_repo.exists():
        print(f"ERROR: Resolved path does not exist: {current_repo}")
        exit(1)

    files = get_code_files(str(current_repo))
    
    if files:
        print(f"\nFound {len(files)} supported files. Showing the first one:")
        first_file = files[0]
        print(f"Path: {first_file['path']}")
        
        # Display a short preview of the file content
        content: str = first_file['content']
        preview_length = min(300, len(content))
        print(f"Content snippet (first {preview_length} characters):\n{'-'*40}\n{content[:preview_length]}\n{'-'*40}\n")  # type: ignore[index]
    else:
        print("No supported code files found in the repository.")
