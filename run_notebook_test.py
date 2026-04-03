"""Execute notebook cells directly as Python to test end-to-end without kernel IPC issues."""
import json
import os
import sys
import traceback
from pathlib import Path

# Ensure project root is cwd and on sys.path
os.chdir(Path(__file__).parent)
if str(Path(".").resolve()) not in sys.path:
    sys.path.insert(0, str(Path(".").resolve()))

with open("demo/demo_notebook.ipynb", encoding="utf-8") as f:
    nb = json.load(f)

code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]

ns = {}
errors = []

for i, cell in enumerate(code_cells):
    source = "".join(cell.get("source", []))
    if not source.strip():
        continue
    print(f"\n{'='*60}")
    print(f"Cell {i+1}:")
    print(source[:200] + ("..." if len(source) > 200 else ""))
    print("-" * 40)
    try:
        exec(compile(source, f"<cell {i+1}>", "exec"), ns)
        print(f"[OK]")
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()
        errors.append((i+1, e))

print(f"\n{'='*60}")
if errors:
    print(f"FAILED — {len(errors)} cell(s) raised errors:")
    for cell_num, err in errors:
        print(f"  Cell {cell_num}: {type(err).__name__}: {err}")
    sys.exit(1)
else:
    print(f"All {len(code_cells)} code cells executed successfully.")
    sys.exit(0)
