---
name: localization-translation-manager
description: Manage translation, localization, bilingual documentation, terminology, glossary consistency, and locale-specific review. Use when translating Korean-English material, preparing localized docs, or checking terminology drift.
---

# Localization Translation Manager

## Workflow

1. Identify the source language, target language, audience, domain, and tone.
2. Preserve meaning before style; preserve technical terms consistently before smoothing prose.
3. Build or update a terminology list for recurring terms, acronyms, UI labels, equations, and paper-specific phrasing.
4. Flag text that should not be translated: code, commands, file paths, identifiers, citations, equations, and product names.
5. Review the localized output as a native user would read it, not as a sentence-by-sentence mirror.

## Quality Checks

- Terminology is consistent across headings, captions, UI text, and references.
- Units, dates, number formatting, punctuation, and honorific tone fit the target locale.
- Translated examples still make sense culturally and technically.
- Korean technical prose avoids overly literal English sentence structure.
- English technical prose avoids inflated or AI-like phrasing.

## For Academic/Engineering Text

Keep equations and symbols unchanged unless notation itself is being revised. Translate explanatory prose around them with enough context that a beginner can follow the concept.

## Output

Return the translated text or review notes, terminology decisions, unresolved ambiguities, and recommended glossary additions.
