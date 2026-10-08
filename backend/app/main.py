import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import modules, deepdive, insights
from app.db.supabase_client import supabase_storage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sf_health.main")

app = FastAPI(
    title="SAP SuccessFactors Health Monitoring Backend",
    description="FastAPI service connecting Supabase Storage & Data to the React Health Monitoring UI.",
    version="1.0.0"
)

# Configure CORS for React UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permits localhost:5173, preview servers, and BTP routes
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root and Health check endpoints
@app.get("/")
def root():
    return {
        "service": "SAP SuccessFactors Health Monitoring API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "supabase_storage_bucket": settings.SUPABASE_BUCKET_NAME,
        "supabase_hierarchy": f"{settings.SUPABASE_BUCKET_NAME}/{supabase_storage.get_latest_root()}/<module>/<metric>"
    }

@app.get("/health")
def health_check():
    supabase_info = supabase_storage.check_connection()
    return {
        "status": "HEALTHY",
        "version": "1.0.4",
        "environment": settings.ENVIRONMENT,
        "supabase": supabase_info
    }

# Register Routers
app.include_router(modules.router, prefix="/api/v1/modules", tags=["Modules"])
app.include_router(deepdive.router, prefix="/api/v1/metrics", tags=["Metrics & Deep Dive"])
app.include_router(insights.router, prefix="/api/v1/insights", tags=["Supabase Insights & Storage"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
