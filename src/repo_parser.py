import os
import logging
from pathlib import Path
from typing import List, Dict

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {'.py', '.js', '.cpp', '.ts', '.java'}

# Standard directories to ignore when scanning
IGNORED_DIRS = {'.git', 'node_modules', 'venv', 'env', '__pycache__', '.pytest_cache', 'dist', 'build'}

def get_code_files(repo_path: str) -> List[Dict[str, str]]:
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
        
    code_files = []
    
    logger.info(f"Scanning repository at '{repo_path}' for files with extensions: {', '.join(SUPPORTED_EXTENSIONS)}")
    
    # Walk through all directories and files in the repo path
    for root, dirs, files in os.walk(repo_path_obj):
        # Modify dirs in-place to skip ignored directories (optimization for os.walk)
        # Using clear() + extend() instead of slice assignment to keep type checkers happy
        filtered = [d for d in dirs if d not in IGNORED_DIRS]
        dirs.clear()
        dirs.extend(filtered)
            
        for file in files:
            file_path = Path(root) / file
            
            # Check if the file has a supported extension
            if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                try:
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
                except UnicodeDecodeError:
                    logger.warning(f"Skipping file {file_path} due to encoding issues (not valid UTF-8).")
                except Exception as e:
                    logger.warning(f"Could not read file {file_path}: {e}")
                    
    logger.info(f"Successfully loaded {len(code_files)} code files.")
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
