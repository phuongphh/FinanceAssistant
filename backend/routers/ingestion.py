import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.expense import ExpenseCreate, ExpenseResponse
from backend.services import expense_service
from backend.services.ocr_service import parse_receipt_image

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.post("/ocr")
async def ocr_receipt(
    file: UploadFile = File(...),
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type: {file.content_type}. Allowed: {ALLOWED_IMAGE_TYPES}",
        )

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="Image too large (max 10MB)")

    result = await parse_receipt_image(image_bytes, file.content_type)

    if result.get("error") == "not_a_receipt":
        return {"data": None, "error": {"code": "NOT_A_RECEIPT", "message": "Image is not a receipt"}}

    return {"data": result, "error": None}


class ManualExpenseInput(BaseModel):
    text: str
    user_id: uuid.UUID


@router.post("/manual", response_model=ExpenseResponse, status_code=201)
async def manual_ingestion(
    data: ManualExpenseInput,
    db: AsyncSession = Depends(get_db),
):
    """Parse free-text expense input and save. For now, expects structured data."""
    from backend.services.llm_service import call_llm

    prompt = f"""Parse chi tiêu từ text sau và trả về JSON:
"{data.text}"

Trả về JSON với format:
{{"amount": <số>, "merchant": "<tên>", "note": "<ghi chú>", "category": "<food_drink|transport|shopping|health|entertainment|utilities|investment|savings|other>"}}

Nếu amount có "k" hoặc "K" ở cuối, nhân với 1000. Ví dụ: 150k = 150000.
Chỉ trả về JSON, không giải thích."""

    try:
        result_text = await call_llm(prompt, task_type="parse_manual", db=db, use_cache=False)
        import json
        # Strip markdown fences
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            result_text = "\n".join(lines)
        parsed = json.loads(result_text)
    except Exception:
        raise HTTPException(status_code=422, detail="Could not parse expense from text")

    expense_data = ExpenseCreate(
        amount=float(parsed.get("amount", 0)),
        merchant=parsed.get("merchant"),
        note=parsed.get("note"),
        category=parsed.get("category", "needs_review"),
        source="manual",
        expense_date=date.today(),
    )

    expense = await expense_service.create_expense(db, data.user_id, expense_data)
    return expense


@router.post("/gmail/sync")
async def trigger_gmail_sync(
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        from backend.services.gmail_service import sync_new_receipts
        expenses = await sync_new_receipts(db, user_id)
        return {
            "data": {"synced_count": len(expenses), "expenses": [str(e.id) for e in expenses]},
            "error": None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gmail sync failed: {e}")
