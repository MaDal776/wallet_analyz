from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import AnalysisRequest, AnalysisResponse
from .services.analysis_pipeline import run_analysis

app = FastAPI(title="Wallet Analysis Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"],
)


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_wallet(payload: AnalysisRequest) -> AnalysisResponse:
    try:
        result = run_analysis(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - general safeguard
        raise HTTPException(status_code=500, detail="分析过程中出现错误") from exc

    return result
