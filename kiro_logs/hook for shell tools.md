# New Session

Exported: 3/30/2026, 6:24:11 PM

## Steering Documents

**Workspace:**
- product.md
- tech.md
- structure.md
- design_language.md
- placate_cong.md
- git.md

---

**Assistant:**

Describe a hook using natural language or choose a sample prompt.

---

**User:**

If Kiro is trying to invoke or locate Python, uv, pytest or other tools add the location to a file which is subject to git-ignore.

---

**Assistant:**

Hook created. It fires before any shell tool use and, when the command involves Python toolchain executables (python, uv, pytest, pip, etc.), resolves their paths via `where` and appends them to `.kiro/tool-locations.txt`, ensuring that file stays gitignored.

---
