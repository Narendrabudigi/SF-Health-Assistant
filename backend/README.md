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
