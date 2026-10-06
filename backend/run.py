import uvicorn
from app.config import settings

if __name__ == "__main__":
    print(f"🚀 Starting SAP SuccessFactors Health Monitoring Backend on http://{settings.HOST}:{settings.PORT}")
    print(f"📚 Interactive Swagger API Docs: http://localhost:{settings.PORT}/docs")
    print(f"📦 Configured Supabase Bucket: '{settings.SUPABASE_BUCKET_NAME}', Folder: '{settings.SUPABASE_FOLDER}'")
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
