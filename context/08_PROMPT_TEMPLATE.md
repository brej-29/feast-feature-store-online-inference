# 08 — Prompt Template for Cosine Tasks

This template is designed for future Cosine AI tasks on this repository.  
It ensures that all work remains grounded in the context and adheres to project constraints.

Copy, adjust, and fill in the sections as needed.

---

## Prompt Template

```text
TASK: &lt;short, imperative description&gt;

CONTEXT FILES TO READ (BEFORE CODING):
- context/00_PROJECT_GOAL.md
- context/01_ARCHITECTURE.md
- context/02_FREE_TIER_CONSTRAINTS.md
- context/03_COSINE_TASK_PROTOCOL.md
- &lt;any others relevant, e.g. 04_DATASET_PLAN, 05_METRICS_AND_EVAL, 07_DECISIONS&gt;

GOAL:
- &lt;what success looks like for this task&gt;

CONSTRAINTS:
- Must remain compatible with free-tier setup (HF Spaces + Neon/Supabase + CloudKarafka).
- Must not introduce docker-compose or multi-container assumptions for HF deployment.
- Must keep logging and exception handling in Python entrypoints.
- &lt;any additional constraints&gt;

INPUTS:
- &lt;links to files, snippets, APIs, or prior steps&gt;

DESIRED OUTPUTS:
- &lt;files to be created or modified&gt;
- &lt;behaviors/endpoints to expose&gt;
- &lt;tests and docs to update&gt;

IMPLEMENTATION NOTES:
- Use existing patterns from:
  - `services/api/app/main.py` for FastAPI style, logging, and metrics.
  - `app.py` for Gradio integration patterns.
- Respect context decisions in:
  - `context/07_DECISIONS.md`
- Update logs:
  - Append to `context/06_STEP_LOG.md` for this step.
  - Add new decisions to `context/07_DECISIONS.md` if necessary.

CHECKLIST BEFORE SUBMITTING:
1) Context files read and honored.
2) Code compiles/lints locally (where possible).
3) New/updated tests added and passing (if applicable).
4) Docs updated (README/context) if behavior or usage changed.
5) Step and decisions logged in:
   - `context/06_STEP_LOG.md`
   - `context/07_DECISIONS.md` (if new decisions made)
```

---

## Usage Guidance

When creating a new Cosine AI task:

1. Start from this template.
2. Customize the **TASK**, **GOAL**, **CONSTRAINTS**, and **DESIRED OUTPUTS**.
3. Explicitly list the context files that must be read.
4. Ensure the final answer references which context files were used and how.