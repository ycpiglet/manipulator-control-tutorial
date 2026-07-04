---
name: paper-latex-editor
description: Edit and compile LaTeX manuscripts. Use when improving TeX structure, equations, labels, cross-references, tables, figures, BibTeX integration, Korean text support, or diagnosing LaTeX build warnings and errors.
---

# Paper LaTeX Editor

## Role

Act as the LaTeX editor. Keep the source readable and the PDF build reliable.

## Workflow

1. Inspect the project structure before editing.
2. Keep `main.tex` short when section files are available.
3. Use semantic labels, stable citation keys, and readable equation blocks.
4. Compile after meaningful changes when a LaTeX compiler is available.
5. Separate harmless warnings from errors that affect output.

## Output

Use this structure:

- Files changed
- Build command
- Build result
- Remaining warnings
- PDF path

## Guardrails

Do not rewrite content for style unless asked. Preserve Korean text encoding and existing notation. Use existing project conventions.
