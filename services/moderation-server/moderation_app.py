
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

moderation_app = FastAPI(
    title="AIP Moderation Server (Llama Guard 4)",
    version="1.0.0",
    description="Llama Guard 4 Content Moderation Microservice",
)


class ModerationRequest(BaseModel):
    input: str | list[str] = Field(..., json_schema_extra={"example": "Kiem tra noi dung nay"})
    model: str = Field("moderation-multimodal", json_schema_extra={"example": "moderation-multimodal"})


class CategoryScores(BaseModel):
    hate: float = 0.001
    harassment: float = 0.002
    self_harm: float = 0.0001
    sexual: float = 0.001
    violence: float = 0.003
    pii_leakage: float = 0.0005


class ModerationResult(BaseModel):
    flagged: bool = False
    categories: dict = {
        "hate": False,
        "harassment": False,
        "self_harm": False,
        "sexual": False,
        "violence": False,
        "pii_leakage": False,
    }
    category_scores: CategoryScores = CategoryScores()


class ModerationResponse(BaseModel):
    id: str = "modr-01HXEXAMPLE"
    model: str
    results: list[ModerationResult]


@moderation_app.post("/v1/moderations", response_model=ModerationResponse)
async def moderate_content(
    request: ModerationRequest,
    authorization: str | None = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer API key required")

    inputs = [request.input] if isinstance(request.input, str) else request.input
    results = [ModerationResult() for _ in inputs]
    return ModerationResponse(model=request.model, results=results)


@moderation_app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "moderation-server", "backend": "Llama Guard 4 + Rules"}
