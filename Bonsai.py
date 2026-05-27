import ast
import argparse
import sys
import fnmatch
from pathlib import Path

def estimate_tokens(text: str) -> int:
    # Attempt to calculate precise tokens using tiktoken with standard fallback.
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except ImportError:
        # Standard structural fallback: 1 token ~= 4 characters
        return len(text) // 4

def copy_to_clipboard(text: str) -> bool:
    # Attempts to copy text to the system clipboard across platforms.
    try:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32

            kernel32.GlobalAlloc.restype = ctypes.c_void_p
            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

            if user32.OpenClipboard(0):
                user32.EmptyClipboard()
                text_bytes = text.encode('utf-16-le') + b'\x00\x00'
                h_cd = kernel32.GlobalAlloc(0x0002, len(text_bytes))
                if h_cd:
                    p_cd = kernel32.GlobalLock(h_cd)
                    if p_cd:
                        ctypes.memmove(p_cd,text_bytes,len(text_bytes))
                        kernel32.GlobalUnlock(h_cd)
                        user32.SetClipboardData(13, h_cd) # 13 = CF_UNICODETEXT
            user32.CloseClipboard()
            return True
    except Exception:
        pass

    try:
        # Cross-platform fallback utilizing subprocess
        import subprocess
        if sys.platform == "darwin":
            process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            return True
        elif sys.platform == "linux":
            process = subprocess.Popen(['xclip', '-selection', 'clipboard'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            return True
        elif sys.platform == "win32":
            # Windows command line fallback using built-in clip tool
            process = subprocess.Popen(['clip'], stdin=subprocess.PIPE, shell=True)
            process.communicate(text.encode('utf-8'))
            return True
    except Exception:
        pass
    return False

class ImportSniffer(ast.NodeVisitor):
    """Targeted AST visitor that ignores general code and isolates imports."""
    def __init__(self):
        self.imports = []
    
    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append((alias.name, 0))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.append((node.module, node.level))
        self.generic_visit(node)
    
def resolve_module(module_name: str, current_file: Path, project_root: Path, level: int = 0) -> Path | None:
    """Resolves local modules to actual filesystem file paths."""
    parts = module_name.replace(".", "/")

    if level > 0:
        base = current_file.parent
        for _ in range(level - 1):
            base = base.parent
        candidates = [base / f"{parts}.py", base / parts / "__init__.py"]
    else:
        candidates = [
            project_root / f"{parts}.py",
            project_root / parts / "__init__.py",
            current_file.parent / f"{parts}.py",
            current_file.parent / parts / "__init__.py",
        ]
    
    for cand in candidates:
        if cand.exists() and cand.is_file():
            return cand.resolve()
    return None

def load_ignore_patterns(project_root: Path) -> list[str]:
    """Compiles ignore lists from standard defaults, .gitignore, and .bonsaiignore."""
    patterns = [".git", "__pycache__", "*.pyc", ".DS_Store", "bonsai_context.md", "venv", ".venv"]
    # FIXED: Added missing dot to .bonsaiignore
    for ignore_file in [".bonsaiignore", ".gitignore"]:
        p = project_root / ignore_file
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    return patterns

def is_ignored(path: Path, project_root: Path, patterns: list[str]) -> bool:
    """Matches a file path against configured directory and glob exclude rules."""
    try:
        rel_str = str(path.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        rel_str = str(path).replace("\\", "/")
    for pattern in patterns:
        if pattern.endswith("/"):
            clean_pattern = pattern.strip("/")
            if fnmatch.fnmatch(rel_str, clean_pattern) or f"/{clean_pattern}/" in f"/{rel_str}/" or rel_str.startswith(f"{clean_pattern}/"):
                return True
        else:
            if fnmatch.fnmatch(rel_str, pattern) or fnmatch.fnmatch(path.name, pattern) or f"/{pattern}/" in f"/{rel_str}/":
                return True
    return False

def crawl_dependencies(entry: Path, project_root: Path, ignore_patterns: list[str]) -> tuple[list[Path], set[str]]:
    """BFS traversal ensuring precise dependency ordering while tracking external requirement bundles."""
    visited = set()
    queue = [entry.resolve()]
    ordered_files = []
    external_deps = set()

    std_libs = set(sys.builtin_module_names) | {
        "abc", "argparse", "ast", "asyncio", "base64", "collections", "contextlib",
        "copy", "csv", "datetime", "enum", "fnmatch", "functools", "glob", "hashlib",
        "html", "http", "importlib", "inspect", "io", "itertools", "json", "logging",
        "math", "multiprocessing", "os", "pathlib", "pickle", "pprint", "queue", "random",
        "re", "select", "shutil", "signal", "socket", "sqlite3", "ssl", "string", "subprocess",
        "sys", "threading", "time", "traceback", "types", "typing", "unittest", "urllib",
        "uuid", "warnings", "weakref", "xml", "zipfile"
    }

    while queue:
        current = queue.pop(0)
        if current in visited or is_ignored(current, project_root, ignore_patterns):
            continue
        visited.add(current)
        ordered_files.append(current)

        try:
            source = current.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue
        
        sniffer = ImportSniffer()
        sniffer.visit(tree)

        for mod_name, level in sniffer.imports:
            resolved = resolve_module(mod_name, current, project_root, level)
            if resolved:
                if resolved not in visited and not is_ignored(resolved, project_root, ignore_patterns):
                    queue.append(resolved)
            else:
                if level == 0:
                    top_mod = mod_name.split(".")[0]
                    if top_mod not in std_libs and not (project_root / f"{top_mod}.py").exists():
                        external_deps.add(top_mod)

    return ordered_files, external_deps

def build_clean_ascii_tree(files: list[Path], project_root: Path) -> str:
    """Constructs a deterministic visual tree from target file selections."""
    trie = {}
    for f in files:
        try:
            rel_parts = f.relative_to(project_root).parts
        except ValueError:
            rel_parts = f.parts
        
        current_node = trie
        for part in rel_parts:
            current_node = current_node.setdefault(part, {})

    def recurse_tree(node, indent = ""):
        lines = []
        items = sorted(node.keys())
        for i, item in enumerate(items):
            is_last = (i == len(items)-1)
            connector = "└── " if is_last else "├── "
            lines.append(f"{indent}{connector}{item}")
            next_indent = indent + ("    " if is_last else "│   ")
            lines.extend(recurse_tree(node[item], next_indent))
        return lines
    return f"{project_root.name}/\n" + "\n".join(recurse_tree(trie))

def main():
    parser = argparse.ArgumentParser(description="Bonsai - Prune your repository into optimized AI context")
    parser.add_argument("entry", help="The primary Python file execution entry point.")
    parser.add_argument("--output", "-o", default="bonsai_context.md", help="Output file name.")
    parser.add_argument("--include", "-i", nargs="*", default=[], help="Explicit non-Python configuration/asset paths to bundle.")
    # FIXED: Added the missing argparse definition so args.copy evaluates properly
    parser.add_argument("--copy", "-c", action="store_true", help="Automatically copy content payload directly to system clipboard.")
    parser.add_argument("--max-tokens","-m", type = int, default = None, help="Set a strict token ceiling for the context payload.")
    args = parser.parse_args()

    entry = Path(args.entry).resolve()
    if not entry.exists() or entry.suffix != ".py":
        print(f"Error: Valid Python entry file '{args.entry}' not found.")
        sys.exit(1)
    
    project_root = entry.parent
    ignore_patterns = load_ignore_patterns(project_root)

    # Process code dependency path
    files, external_deps = crawl_dependencies(entry, project_root, ignore_patterns)

    # Process manual asset/config configurations
    for inc_item in args.include:
        inc_path = Path(inc_item).resolve()
        if inc_path.exists() and inc_path.is_file() and inc_path not in files:
            files.append(inc_path)

    # Generate assets
    tree_view = build_clean_ascii_tree(files, project_root)

    sections = []
    for f in files:
        rel = f.relative_to(project_root) if project_root in f.parents else f
        ext = f.suffix.lstrip('.').lower()

        syntax = ext if ext in ["python", "json", "yaml", "yml", "toml", "md", "txt", "ini", "sh"] else "text"
        if syntax == "yml": syntax = "yaml"
        if syntax == "py": syntax = "python"

        try:
            file_content = f.read_text(encoding='utf-8').rstrip()
        except Exception:
            file_content = "[Binary or unreadable file asset]"
        
        sections.append(f"### File: `{rel}`\n```{syntax}\n{file_content}\n```")

    bundled_code = "\n\n---\n\n".join(sections)
    token_est = estimate_tokens(bundled_code)

    if args.max_tokens and token_est > args.max_tokens:
        print(f"\nERROR: Context cost (~{token_est:,} tokens) exceeds your strict limit of {args.max_tokens:,} tokens!")
        print("Operation halted. Try ignoring heavy directories or reducing explicit --include files.")
        sys.exit(1)
    pip_list = ", ".join(sorted(external_deps)) if external_deps else "None detected"
    payload = (
        f"# Bonsai Context Manifest\n\n"
        f"> **Entry Point:** '{entry.name}' | **Parsed Files:** {len(files)} | **Est. Context Cost:** ~{token_est:,} tokens\n"
        f"> **External Package Blueprint:** {pip_list}\n\n"
        f"## Repository Architecture\n```\n{tree_view}\n```\n\n"
        f"---\n\n"
        f"## Source Code Payload\n\n{bundled_code}"
    )

    Path(args.output).write_text(payload, encoding="utf-8")
    print(f"Bonsai complete. Shrunk context down to {len(files)} targeted files (~{token_est:,} tokens). Saved to {args.output}")

    # Clipboard action
    if args.copy:
        if copy_to_clipboard(payload):
            print("Success: Context manifest copied directly to system clipboard!")
        else:
            print("WARNING: Clipboard copy failed. Please copy or drag the md file to chatbot manually.")
    
    if token_est > 60000:
        print(f"\n Budget Note: This payload is relatively large (~{token_est:,} tokens). Ensure your destination model supports long context windows.")

if __name__ == "__main__":
    main()