# 03 — Cosine Task Protocol

This document defines a **strict protocol** for how Cosine AI (and humans working with it) must interact with this repository.

The goal is to keep changes:

- Grounded in shared context
- Traceable over time
- Consistent with free-tier constraints and architecture

This protocol is **mandatory** for every substantial task.

---

## 1. Pre-task checklist (MUST DO BEFORE CODING)

Before writing or modifying any code or docs:

1. **Read the following context files:**

   - `context/00_PROJECT_GOAL.md`
   - `context/01_ARCHITECTURE.md`
   - `context/02_FREE_TIER_CONSTRAINTS.md`
   - `context/03_COSINE_TASK_PROTOCOL.md` (this file)
   - Any additional context files relevant to your task (dataset, metrics, decisions, etc.)

2. **Summarize (internally) the key constraints** relevant to the task:
   - What is the user-facing goal?
   - What free-tier or HF-specific constraints apply?
   - Are there any prior decisions in `context/07_DECISIONS.md` that you must honor?

3. **Identify the scope of changes**:
   - Which components are you touching? (API, Gradio, feature_repo, infra, etc.)
   - Are you adding new dependencies?

---

## 2. Task description structure

Every task handled by Cosine AI should maintain an internal or explicit structure like:

1. **Task ID / Name**
2. **Summary**
3. **Context files consulted**
4. **Assumptions**
5. **Planned changes**
6. **Out-of-scope items** (intentionally left for later)

When writing PR descriptions, step logs, or task notes, include these elements in human-readable form.

---

## 3. Referencing context in each task

For each task, Cosine AI must explicitly state (at least in the task notes or PR description):

1. **Which context files were used**, e.g.:

   - `context/00_PROJECT_GOAL.md`
   - `context/01_ARCHITECTURE.md`
   - `context/02_FREE_TIER_CONSTRAINTS.md`
   - `context/04_DATASET_PLAN.md`
   - `context/05_METRICS_AND_EVAL.md`
   - etc.

2. **How they influenced the changes**, e.g.:

   - “I avoided adding a second container because `context/02_FREE_TIER_CONSTRAINTS.md` requires a single container on HF Spaces.”
   - “I exposed new metrics for PR-AUC and latency since `context/05_METRICS_AND_EVAL.md` emphasizes those.”

This can be recorded in:

- PR descriptions
- Comments in `context/06_STEP_LOG.md`
- Task notes in external tooling (if any)

---

## 4. Updating logs and decisions

For **every step** that makes a non-trivial change (features, infra, metrics, or behavior), you must:

1. Append an entry to `context/06_STEP_LOG.md` with:
   - Step identifier (e.g., `Step 0`, `Step 1.1 – Add Feast entities`)
   - Date
   - Author/agent
   - Summary of changes
   - Files touched (high-level)
   - Links to relevant decisions in `context/07_DECISIONS.md` (if any)

2. If you made or changed an important decision (architecture, product, metrics), add or update an entry in `context/07_DECISIONS.md`:
   - Decision ID (e.g., `D001`)
   - Date
   - Status (`proposed`, `accepted`, `deprecated`)
   - Context/problem
   - Options considered
   - Chosen option and justification
   - Consequences / follow-ups

Even if a decision seems “obvious”, document it if it affects future work.

---

## 5. Dependency and infra discipline

When introducing new dependencies or infra components:

1. **Check free-tier constraints**:
   - Does this violate `context/02_FREE_TIER_CONSTRAINTS.md`?
   - Does it require paid features or excessive resource usage?

2. **Document the reasoning**:
   - Update `context/07_DECISIONS.md` with why this dependency is needed.
   - Mention any alternatives considered (e.g., using built-in libraries).

3. **Update relevant docs**:
   - `README.md` if the change affects how to run the project.
   - `requirements*.txt` and `Dockerfile` must remain consistent.

---

## 6. Code quality expectations for Cosine AI

Cosine AI must:

- Follow the coding style and patterns already present.
- Use **structured logging** and basic exception handling in Python entrypoints (APIs, CLIs, scripts).
- Avoid:
  - Silent failures
  - Overly broad `try/except` blocks that hide errors
  - Large unstructured functions with many responsibilities
- Prefer:
  - Small, testable components
  - Adding or updating tests where reasonable
  - Updating docs alongside code changes

For FastAPI and Gradio entrypoints, always ensure:

- Logging is configured at module import time.
- Unhandled exceptions are logged at error level.

---

## 7. How to handle ambiguity

If requirements are ambiguous:

1. **Default to the simplest implementation** that:
   - Respects free-tier constraints
   - Does not block future extensibility
2. **Record the ambiguity** and chosen resolution:
   - In `context/07_DECISIONS.md` (if significant)
   - Or as a note in `context/06_STEP_LOG.md`
3. **Avoid “magic behavior”**:
   - No hidden side effects or surprising defaults.
   - Make trade-offs explicit in docs.

---

## 8. Step 0 application of this protocol

For **Step 0**, this protocol is used to:

- Justify the choice of:
  - Single-container architecture
  - Nginx reverse proxy + Prometheus inside the container
  - Local-only `docker-compose.yml` for Postgres + Redpanda + stack
- Provide a baseline template for:
  - Future Feast integration
  - Feature engineering notebooks
  - Monitoring extensions

Subsequent steps must continue to follow this protocol and keep the context files accurate, especially:

- `context/06_STEP_LOG.md`
- `context/07_DECISIONS.md`

Any agent working on this repo should treat this protocol as a **binding contract**.