import os
import json
from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

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
