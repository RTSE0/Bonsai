<h1 align="center">🪴Bonsai</h1>

<h3 align="center">Snip! snip! Prune your Python project into optimized LLM context.</h3>

Whenever you ask an AI to help debug or extend your code, you need to paste the right files - but figuring out which files matter is tedius, and pasting the whole repo blows past token limits too qucikly. Bonsai solves this by tracing your project's import graph and bundling only the files that matters; all into one clean markdown file. Just drag and drop afterwards-- or paste, doesn't matter, I won't judge 😉

---

## How it works

Point Bonsai at any Python entry file. It parses the AST, traces every local import recursively via BFS, and stitches the relevant files together into a context manifest — complete with a dependency tree, token estimate, and pip requirements. Non-Python files like configs, YAML, TOML, and plain text can be bundled alongside using `--include`.

---
 
## Usage

```bash
python Bonsai.py <entry_file.py> [options]
```

<sub>Yes. Just like that.</sub>

### Examples
 
```bash
# Basic usage — outputs bonsai_context.md
python Bonsai.py main.py
 
# Custom output file
python Bonsai.py main.py --output my_context.md
 
# Copy straight to clipboard
python Bonsai.py main.py --copy
 
# Include non-Python files (configs, assets)
python Bonsai.py main.py --include config.json .env.example
 
# Set a strict token ceiling (halts if exceeded)
python Bonsai.py main.py --max-tokens 20000
```

### All options
 
| Flag | Short | Description |
|------|-------|-------------|
| `--output` | `-o` | Output filename (default: `bonsai_context.md`) |
| `--copy` | `-c` | Copy output directly to clipboard |
| `--include` | `-i` | Manually include extra non-Python files |
| `--max-tokens` | `-m` | Halt if token count exceeds this limit |

---
 
## Installation
 
No installation needed. Just download `Bonsai.py` and run it.
 
**Optional:** Install `tiktoken` for precise token counting instead of the built-in estimate:
 
```bash
pip install tiktoken
```
 
---
 
## Ignoring files
 
Bonsai automatically respects your `.gitignore`. You can also create a `.bonsaiignore` file in your project root using the same syntax to exclude Bonsai-specific paths.
 
---
 
## License
 
MIT
