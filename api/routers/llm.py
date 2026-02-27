"""
LLM analysis endpoints.
Full implementation in Phase 4 (src/llm/ module).
"""
from fastapi import APIRouter, HTTPException

import api.deps  # noqa
from api.models.llm import LLMAnalyzeRequest, LLMAnalyzeResponse, LLMStatusResponse

router = APIRouter()


@router.post("/llm/analyze", response_model=LLMAnalyzeResponse)
async def analyze_stocks(request: LLMAnalyzeRequest):
    """
    Analyze a list of screened stocks with the configured LLM provider.
    Returns per-stock commentary, criteria suggestions, and overall summary.
    Synchronous — typically 30-90 seconds for 50 stocks.
    """
    try:
        from src.llm.analyzer import LLMAnalyzer
        analyzer = LLMAnalyzer()
        result = analyzer.analyze_stocks(
            stocks=request.stocks,
            criteria=request.criteria,
            user_notes=request.user_notes,
        )
        return LLMAnalyzeResponse(**result)
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="LLM module not yet installed. Run Phase 4 setup."
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/llm/status", response_model=LLMStatusResponse)
async def get_llm_status():
    """Check LLM provider configuration and connectivity."""
    try:
        from src.utils import load_config, load_credentials
        cfg = load_config()
        llm_cfg = cfg.get("llm", {})
        provider = llm_cfg.get("provider", "claude")

        if provider == "claude":
            creds = load_credentials()
            api_key = creds.get("anthropic", {}).get("api_key", "")
            configured = bool(api_key)
            reachable = None
            error = None
            if configured:
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=api_key)
                    # Lightweight check — list models endpoint
                    client.models.list(limit=1)
                    reachable = True
                except Exception as e:
                    reachable = False
                    error = str(e)
            return LLMStatusResponse(
                provider="claude",
                model=llm_cfg.get("model", "claude-sonnet-4-6"),
                configured=configured,
                reachable=reachable,
                error=error,
            )
        else:
            # Local provider
            base_url = llm_cfg.get("local_base_url", "http://localhost:11434/v1")
            model = llm_cfg.get("local_model", "llama3.2")
            try:
                import httpx
                resp = httpx.get(base_url.replace("/v1", "/api/tags"), timeout=3.0)
                reachable = resp.status_code == 200
                error = None
            except Exception as e:
                reachable = False
                error = str(e)
            return LLMStatusResponse(
                provider="local",
                model=model,
                configured=True,
                reachable=reachable,
                error=error,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
