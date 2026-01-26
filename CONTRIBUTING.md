# Contributing Guide

This project is designed around:

- **Free-tier compatible deployment** (HF Spaces + Neon/Supabase + CloudKarafka).
- A **single-container** architecture for Hugging Face Spaces.
- A **context-first** workflow so that multiple agents (humans and Cosine AI) can collaborate safely.

Please read this guide before making changes.

---

## 1. Read the context first

Before any substantial work, read at least:

- `context/00_PROJECT_GOAL.md`
- `context/01_ARCHITECTURE.md`
- `context/02_FREE_TIER_CONSTRAINTS.md`
- `context/03_COSINE_TASK_PROTOCOL.md`

Depending on your task, you may also need:

- `context/04_DATASET_PLAN.md`
- `context/05_METRICS_AND_EVAL.md`
- `context/06_STEP_LOG.md`
- `context/07_DECISIONS.md`

This ensures your changes are aligned with the project direction and past decisions.

---

## 2. Working with Cosine AI tasks

When using Cosine AI (Genie) to assist with changes:

1. **Create a clear task description**:
   - Use the template in `context/08_PROMPT_TEMPLATE.md`.
2. **Specify which context files Cosine AI must read** before coding.
3. **Constrain the scope**:
   - List exactly which components/files should be modified.
4. **Require logs/decisions updates**:
   - Ask explicitly for:
     - An entry in `context/06_STEP_LOG.md`.
     - An entry or update in `context/07_DECISIONS.md` if applicable.

After the AI provides changes:

- Review the diffs as you would any PR.
- Run tests and linters locally.
- Ensure documentation remains truthful.

---

## 3. Local development

### 3.1. Setup

```bash
python -m venv .venv
source .venv/bin/activate            # On Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Use the `Makefile` shortcuts:

```bash
make setup    # Install all dependencies into .venv
make lint     # Run Ruff
make format   # Run Black
make test     # Run pytest
```

### 3.2. Running services locally

Run FastAPI:

```bash
uvicorn services.api.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Run Gradio in another terminal:

```bash
python app.py
```

Alternatively, run the Docker stack (local only):

```bash
docker compose up --build
```

Then visit:

- Gradio UI: http://localhost:7860/
- API: http://localhost:7860/api/predict
- Prometheus UI: http://localhost:7860/prom/ (if Prometheus is running)

---

## 4. Coding standards

- Follow existing patterns in:
  - `services/api/app/main.py` for FastAPI, logging, and metrics.
  - `app.py` for Gradio integration and logging.
- Use structured logging where reasonable:
  - Include key fields like `path`, `status_code`, `latency`, etc.
- Exception handling:
  - Do not swallow exceptions silently.
  - Log unhandled exceptions and re-raise or return a clear error response.
- Keep functions focused and testable.

Formatting and linting:

- Run `make format` before committing.
- Run `make lint` and `make test` to ensure a clean state.

---

## 5. Updating context and decisions

Whenever you make a non-trivial change:

1. Update `context/06_STEP_LOG.md`:
   - Add a new step entry with:
     - Date
     - Summary of changes
     - Files touched
     - Context consulted
2. If you make or change a significant decision:
   - Add an entry to `context/07_DECISIONS.md` or update an existing one.

This keeps the project understandable as it evolves.

---

## 6. Free-tier and deployment considerations

Before adding new dependencies or architecture:

- Check `context/02_FREE_TIER_CONSTRAINTS.md`.
- Ask:
  - Does this require a paid tier?
  - Does this need another container or external service?
  - Does it add significant CPU/RAM footprint?

If the answer to any of these is “yes” or “maybe”:

- Document the trade-offs in `context/07_DECISIONS.md`.
- Prefer simpler alternatives that keep the project runnable on:
  - A small local machine
  - A single HF Spaces container

---

## 7. Submitting changes

1. Ensure code is formatted and linted.
2. Ensure tests pass.
3. Ensure docs (README/context) are updated.
4. Provide a short summary referencing:
   - Context files you consulted.
   - Decisions you made or relied on.

Thank you for helping build a robust, transparent, and free-tier friendly feature store stack.