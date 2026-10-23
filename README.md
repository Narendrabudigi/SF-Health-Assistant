# SF Health Monitoring

This repository contains a React/Vite frontend and a FastAPI backend. The Python package lives under `backend/app`, so backend commands must either run from `backend` or add `backend` to Python's import path.

## Run the backend from the repository root

Install dependencies once:

```powershell
python -m pip install -r backend/requirements.txt
```

Then use the included launcher, which sets the backend import path:

```powershell
python run.py
```

Or start Uvicorn directly from the repository root with `--app-dir backend`:

```powershell
python -m uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

The original command `uvicorn app.main:app ...` fails from the repository root because there is no root-level `app` package. The equivalent command from inside the backend directory is:

```powershell
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

See [backend/README.md](backend/README.md) for Supabase configuration and API details. The API docs are at `http://localhost:8000/docs` after the server starts.

The orchestrator setup and UI integration are documented in [backend/README.md](backend/README.md#4-run-the-ml-and-llm-orchestrator-from-the-app).
