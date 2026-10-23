from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import orchestrator_runner

router = APIRouter(prefix="/api/pipeline", tags=["Orchestrator Pipeline"])


class RunRequest(BaseModel):
    standards: str = Field(default="all", description="all, industry, or custom standards")
    run_date: str | None = Field(default=None, description="Optional run date in YYYY-MM-DD format")
    force: bool = False


@router.post("/run", status_code=202)
def run_pipeline(request: RunRequest):
    try:
        return orchestrator_runner.start(request.standards, request.run_date, request.force)
    except RuntimeError as err:
        raise HTTPException(status_code=409, detail=str(err)) from None
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from None
    except FileNotFoundError as err:
        raise HTTPException(status_code=503, detail=str(err)) from None


@router.get("/status")
def pipeline_status(tail: int = 50):
    return orchestrator_runner.status(tail)


@router.post("/stop")
def stop_pipeline():
    try:
        return orchestrator_runner.stop()
    except RuntimeError as err:
        raise HTTPException(status_code=409, detail=str(err)) from None
