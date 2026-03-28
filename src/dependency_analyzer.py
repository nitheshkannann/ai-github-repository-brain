import ast
import os
import sys
import json
from typing import List, Set, Dict, Any
from pathlib import Path
import re

# Try importing from src.repo_parser or repo_parser directly
try:
    from src.repo_parser import get_code_files
except ImportError:
    from repo_parser import get_code_files

PACKAGE_MAPPING = {
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "sentence_transformers": "sentence-transformers",
    "faiss": "faiss-cpu",
}

def extract_imports_from_code(code: str) -> List[str]:
    """Parses Python code and extracts a list of imported top-level modules."""
    imports = []
    try:
        tree = ast.parse(code)
    except Exception:
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                imports.append(node.module.split('.')[0])
    return imports

def get_ast_python_dependencies(repo_path: str) -> List[str]:
    files = get_code_files(repo_path)
    all_imports: Set[str] = set()
    local_modules: Set[str] = set(["src"])

    # First pass: identify local module names
    for f in files:
        if f['path'].endswith('.py'):
            file_name = Path(f['path']).stem
            local_modules.add(file_name)
            parts = Path(f['path']).parts
            if len(parts) > 0:
                local_modules.add(parts[0])

    # Second pass: extract all imports
    for f in files:
        if f['path'].endswith('.py'):
            imports = extract_imports_from_code(f['content'])
            all_imports.update(imports)

    stdlib: Set[str] = set()
    try:
        if hasattr(sys, 'stdlib_module_names'):
            stdlib = set(sys.stdlib_module_names)
    except Exception:
        pass

    dependencies = set()
    for imp in all_imports:
        if imp in stdlib or imp in local_modules or imp.startswith('_'):
            continue

        pkg = PACKAGE_MAPPING.get(imp, imp)
        if pkg not in PACKAGE_MAPPING.values():
            pkg = pkg.replace('_', '-')
            
        dependencies.add(pkg)

    return sorted(list(dependencies))


def parse_requirements_txt(path: Path) -> List[str]:
    deps = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    match = re.split(r'[=<>~!]', line)[0]
                    if match:
                        deps.append(match)
        return sorted(list(set(deps)))
    except Exception:
        return []


def parse_pyproject_toml(path: Path) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            deps_match = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
            if deps_match:
                items = re.findall(r'["\'](.*?)["\']', deps_match.group(1))
                deps = [re.split(r'[=<>~!]', item)[0] for item in items]
                return sorted(list(set(deps)))
    except Exception:
        pass
    return []


def parse_package_json(path: Path) -> List[str]:
    deps = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "dependencies" in data:
                deps.extend(data["dependencies"].keys())
            if "devDependencies" in data:
                deps.extend(data["devDependencies"].keys())
        return sorted(list(set(deps)))
    except Exception:
        return []

def detect_entry_points(repo_path: Path) -> Dict[str, str]:
    entry_points = {}
    
    # Python
    py_candidates = ["main.py", "app.py", "src/main.py", "src/app.py", "src/api.py", "api.py"]
    for cand in py_candidates:
        if (repo_path / cand).exists():
            entry_points["python"] = cand
            break
            
    # JS
    pkg_json_paths = list(repo_path.rglob("package.json"))
    pkg_json_paths = [p for p in pkg_json_paths if "node_modules" not in str(p)]
    
    for p in pkg_json_paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "scripts" in data:
                    scripts = data["scripts"]
                    if "dev" in scripts:
                        rel_dir = p.parent.relative_to(repo_path)
                        cmd = "npm run dev" if str(rel_dir) == "." else f"cd {rel_dir} && npm run dev"
                        entry_points["javascript"] = cmd
                        break
                    elif "start" in scripts:
                        rel_dir = p.parent.relative_to(repo_path)
                        cmd = "npm start" if str(rel_dir) == "." else f"cd {rel_dir} && npm start"
                        entry_points["javascript"] = cmd
                        break
        except Exception:
            pass
            
    return entry_points


def generate_requirements(repo_path: str) -> Dict[str, Any]:
    """
    Analyzes a repository, extracts multi-language dependencies (Python, JS),
    and returns them structurally.
    """
    repo = Path(repo_path)
    
    python_deps: List[str] = []
    javascript_deps: List[str] = []
    source = "detected_from_files"

    req_txt = repo / "requirements.txt"
    pyproj = repo / "pyproject.toml"
    
    if req_txt.exists():
        python_deps = parse_requirements_txt(req_txt)
        source = "requirements.txt"
    elif pyproj.exists():
        python_deps = parse_pyproject_toml(pyproj)
        source = "pyproject.toml"
        
    if not python_deps:
        python_deps = get_ast_python_dependencies(repo_path)

    pkg_json_paths = list(repo.rglob("package.json"))
    pkg_json_paths = [p for p in pkg_json_paths if "node_modules" not in str(p)]
    
    if pkg_json_paths:
        js_set = set()
        for p in pkg_json_paths:
            js_set.update(parse_package_json(p))
        javascript_deps = sorted(list(js_set))
        if source == "detected_from_files":
            source = "package.json"
        else:
            source += " + package.json"

    entry_pts = detect_entry_points(repo)

    result = {
        "python": python_deps,
        "javascript": javascript_deps,
        "source": source,
        "entry_points": entry_pts
    }
    
    return result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate dependencies")
    
    current_dir = Path(__file__).resolve().parent
    default_repo = str(current_dir.parent) if current_dir.name == "src" else str(current_dir)
    
    parser.add_argument("repo_path", nargs="?", default=default_repo, help="Path to repository")
    args = parser.parse_args()

    repo_path_obj = Path(args.repo_path).resolve()
    print(f"Analyzing repository: {repo_path_obj} ...\n")
    
    deps = generate_requirements(str(repo_path_obj))

    print("Python Dependencies:")
    for d in deps["python"]:
        print(f" - {d}")
        
    print("\nJavaScript Dependencies:")
    for d in deps["javascript"]:
        print(f" - {d}")
        
    print(f"\nSource: {deps['source']}")
