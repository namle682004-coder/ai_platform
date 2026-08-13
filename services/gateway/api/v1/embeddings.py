from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from common.models.schemas import EmbeddingRequest, EmbeddingResponse, EmbeddingData, UsageInfo

router = APIRouter(prefix="/v1", tags=["Embeddings"])


@router.post("/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(
    request: EmbeddingRequest,
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer API key required")

    inputs = [request.input] if isinstance(request.input, str) else request.input
    mock_vector = [0.0123] * 1536

    data_items = [
        EmbeddingData(object="embedding", index=idx, embedding=mock_vector)
        for idx in range(len(inputs))
    ]

    return EmbeddingResponse(
        object="list",
        data=data_items,
        model=request.model,
        usage=UsageInfo(prompt_tokens=len(inputs) * 8, completion_tokens=0, total_tokens=len(inputs) * 8)
    )
