import sys
from pathlib import Path

# Set up path to backend folder
backend_dir = Path(__file__).resolve().parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import uvicorn
from app.config import settings

if __name__ == "__main__":
    print(f"🚀 Starting SAP SuccessFactors Health Monitoring Backend on http://{settings.HOST}:{settings.PORT}")
    print(f"📚 Interactive Swagger API Docs: http://localhost:{settings.PORT}/docs")
    print(f"📦 Configured Supabase Bucket: '{settings.SUPABASE_BUCKET_NAME}', Folder: '{settings.SUPABASE_FOLDER}'")
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True, app_dir=str(backend_dir))

