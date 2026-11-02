# GenAI Chatbot

A production-grade GenAI project built incrementally for learning and deployment.

Current work is tracked in [MILESTONE_1_TRACKER.md](MILESTONE_1_TRACKER.md).

## Local development

Prerequisites: Python 3.13, Node.js supported by Vite 8, npm, and PostgreSQL (Docker support is planned).

Backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

The first slice uses a deterministic mock provider over WebSockets. PostgreSQL persistence, anonymous session ownership, and a real LLM provider are pending tracker items.
