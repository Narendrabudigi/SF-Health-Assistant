# SAP SuccessFactors Health Monitoring - FastAPI Backend

This backend acts as the data service layer between **Supabase** (PostgreSQL + Storage Buckets) and the **React Health Monitoring UI**.

---

## 1. Quick Start

### Step 1: Install Python Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### Step 2: Configure Supabase
Copy `.env.example` to `.env` (or edit `backend/.env`):
```env
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_KEY=<your-anon-or-service-role-key>

# Storage bucket where ML insights JSON are stored
SUPABASE_BUCKET_NAME=ml-insights
SUPABASE_FOLDER=insights
```

### Step 3: Start the Backend Server
```bash
python run.py
# Or:
uvicorn app.main:app --reload --port 8000
```
- API root: `http://localhost:8000`
- Swagger UI Documentation: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

---

## 2. Supabase Storage Bucket Setup

1. In your **Supabase Dashboard**, navigate to **Storage**.
2. Click **New bucket**, name it `ml-insights` (Public or Private).
3. Create a folder inside named `insights/`.
4. Store your ML insight JSON files using the metric code naming convention, for example:
   - `insights/ec_data_accuracy.json`
   - `insights/rcm_time_to_fill.json`
   - `insights/onb_day1_readiness.json`

*(Tip: You can call `POST http://localhost:8000/api/v1/insights/seed-samples` to automatically seed test files into your bucket).*

---

## 3. Endpoints Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Check API & Supabase connection status |
| `GET` | `/api/v1/modules` | Home dashboard module tiles & status |
| `GET` | `/api/v1/modules/{id}` | Detailed module benchmarks & metrics |
| `GET` | `/api/v1/metrics/{code}/deep-dive` | Reads ML insight from Supabase Storage bucket |
| `GET` | `/api/v1/insights/status` | Verify bucket connection & files count |
| `POST` | `/api/v1/insights/seed-samples` | Seed sample insights into your bucket |

## 4. Run the ML and LLM orchestrator from the app

The existing orchestrator package is in `sf-genai-orchestrator 1` at the repository root. It uses a separate Python environment at `backend/orchestrator/.venv` so its ML libraries do not enlarge the FastAPI environment.
From the repository root on Windows:

```powershell
cd backend/orchestrator
py -m venv .venv
.venv\Scripts\activate
cd "..\..\sf-genai-orchestrator 1"
pip install -e ".[notebooks]"
python -m sf_orchestrator.pipeline --dry-run
```

Set `ORCHESTRATOR_DIR=../sf-genai-orchestrator 1` and `ORCHESTRATOR_PYTHON=orchestrator/.venv/Scripts/python.exe` in `backend/.env` (the defaults shown in `backend/.env.example`). On Linux, use `orchestrator/.venv/bin/python` for `ORCHESTRATOR_PYTHON`.

The orchestrator reads `sf-genai-orchestrator 1/.env`. Set its `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `INSIGHTS_TABLE=ML_Notebook_Insights`, `REPORTS_TABLE=LLM_Reports`, `GEMINI_API_KEY`, `GROQ_API_KEY`, and `LLM_CHAIN` there. The Supabase tables in `sf-genai-orchestrator 1/sql/llm_reports.sql` and `dashboard.sql` must be created in the Supabase SQL editor; the custom reports SQL is only needed when custom standards are configured. Keep all service-role and LLM keys server-side.

Custom mode reads `SF Health Monitoring Custom Standards.xlsx` from the `SF_Health_Raw_Data` bucket, runs the notebooks in `notebooks_custom`, and uses `ML_Notebook_Custom_Insights` / `LLM_Reports_Custom`. Keep `CUSTOM_INSIGHTS_TABLE` and `CUSTOM_REPORTS_TABLE` in the orchestrator `.env` aligned with `SUPABASE_CUSTOM_INSIGHTS_TABLE` and `SUPABASE_CUSTOM_REPORTS_TABLE` in `backend/.env`. The upload dialog validates and replaces that same workbook object with upsert; Refresh then runs only the selected standards mode.

The Refresh control starts `all` standards in the background. The frontend polls these endpoints and reloads the module data from Supabase after a successful run:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/pipeline/run` | Start the orchestrator (`standards`, optional `run_date`, optional `force`) |
| `GET` | `/api/pipeline/status` | Read run state and recent process output |
| `POST` | `/api/pipeline/stop` | Stop the active run and its child processes |

The run state is held in backend process memory, so run one FastAPI worker as described in the orchestrator PDF. The orchestrator itself writes reports to Supabase; the backend then reads those records for the UI.
