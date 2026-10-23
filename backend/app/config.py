import os
import json
import os
from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from pathlib import Path

BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(BACKEND_ENV_FILE)

class Settings(BaseSettings):
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Parse CORS origins
    cors_raw: str = os.getenv("CORS_ORIGINS", '["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]')
    
    @property
    def CORS_ORIGINS(self) -> List[str]:
        try:
            return json.loads(self.cors_raw)
        except Exception:
            return ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

    # Supabase Credentials
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip()
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "").strip()
    
    # Storage bucket configuration for ML insights
    SUPABASE_BUCKET_NAME: str = os.getenv("SUPABASE_BUCKET_NAME", "Insights and Reports").strip()
    SUPABASE_FOLDER: str = os.getenv("SUPABASE_FOLDER", "").strip()

    # Separate orchestrator runtime. Relative paths resolve from the backend directory.
    ORCHESTRATOR_DIR: str = os.getenv("ORCHESTRATOR_DIR", "../sf-genai-orchestrator 1").strip()
    ORCHESTRATOR_PYTHON: str = os.getenv(
        "ORCHESTRATOR_PYTHON", "orchestrator/.venv/Scripts/python.exe"
    ).strip()

    # Raw source dataset storage and its optional module/metric-to-file manifest.
    SUPABASE_DATASET_BUCKET_NAME: str = os.getenv(
        "SUPABASE_DATASET_BUCKET_NAME", "SF_Health_Raw_Data"
    ).strip()
    SUPABASE_DATASET_MANIFEST_PATH: str = os.getenv(
        "SUPABASE_DATASET_MANIFEST_PATH", "dataset_manifest.json"
    ).strip().strip("/")

    # Custom standards are stored with the raw datasets and use separate ML/LLM tables.
    SUPABASE_CUSTOM_STANDARDS_BUCKET_NAME: str = os.getenv(
        "SUPABASE_CUSTOM_STANDARDS_BUCKET_NAME",
        os.getenv("SUPABASE_DATASET_BUCKET_NAME", "SF_Health_Raw_Data"),
    ).strip()
    SUPABASE_CUSTOM_STANDARDS_PATH: str = os.getenv(
        "SUPABASE_CUSTOM_STANDARDS_PATH", "SF Health Monitoring Custom Standards.xlsx"
    ).strip().lstrip("/")
    SUPABASE_CUSTOM_INSIGHTS_TABLE: str = os.getenv(
        "SUPABASE_CUSTOM_INSIGHTS_TABLE", "ML_Notebook_Custom_Insights"
    ).strip()
    SUPABASE_CUSTOM_REPORTS_TABLE: str = os.getenv(
        "SUPABASE_CUSTOM_REPORTS_TABLE", "LLM_Reports_Custom"
    ).strip()

    @property
    def RESOLVED_SUPABASE_URL(self) -> str:
        url = self.SUPABASE_URL.strip()
        if "supabase.com/dashboard/project/" in url:
            project_ref = url.split("supabase.com/dashboard/project/")[-1].strip().split("/")[0].split("?")[0]
            return f"https://{project_ref}.supabase.co"
        return url

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
