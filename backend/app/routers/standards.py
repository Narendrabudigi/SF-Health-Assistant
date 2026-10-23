from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi import Query
from fastapi.responses import StreamingResponse
from io import BytesIO

from app.config import settings
from app.db.custom_standards import (
    MAX_WORKBOOK_BYTES,
    custom_standards_template,
    load_custom_standards,
    parse_custom_standards,
    standards_response,
    upload_custom_standards as store_custom_standards,
)

router = APIRouter(prefix="/api/v1/standards", tags=["Custom Standards"])


async def _read_workbook(file: UploadFile) -> bytes:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Upload the custom standards as an .xlsx workbook.")
    content = await file.read(MAX_WORKBOOK_BYTES + 1)
    if len(content) > MAX_WORKBOOK_BYTES:
        raise HTTPException(status_code=413, detail="The custom standards workbook must be 15 MB or smaller.")
    return content


@router.get("/custom")
def get_custom_standards(refresh: bool = Query(False)):
    """Fetch the current custom standards map from the configured workbook in Supabase Storage."""
    return load_custom_standards(force_refresh=refresh)


@router.get("/custom/template")
def download_custom_standards_template():
    """Download a blank custom standards workbook with a separate examples sheet."""
    return StreamingResponse(
        BytesIO(custom_standards_template()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="SF Health Monitoring Custom Standards Template.xlsx"'
        },
    )


@router.post("/custom/preview")
async def preview_custom_standards(file: UploadFile = File(...)):
    content = await _read_workbook(file)
    return standards_response(parse_custom_standards(content))


@router.put("/custom")
async def replace_custom_standards(file: UploadFile = File(...)):
    """Replace the configured workbook object, preserving its bucket and path."""
    content = await _read_workbook(file)
    result = store_custom_standards(content)
    result["message"] = (
        f"Replaced {settings.SUPABASE_CUSTOM_STANDARDS_PATH} in "
        f"{settings.SUPABASE_CUSTOM_STANDARDS_BUCKET_NAME}."
    )
    return result
