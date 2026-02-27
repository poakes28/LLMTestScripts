"""Pydantic models for LLM analysis endpoints."""
from typing import Any, List, Optional
from pydantic import BaseModel


class LLMAnalyzeRequest(BaseModel):
    stocks: List[dict]              # list of screener result dicts
    criteria: dict                  # criteria used in the screen
    user_notes: str = ""


class StockCommentary(BaseModel):
    ticker: str
    rating: str                     # "Strong Buy" | "Buy" | "Hold" | "Avoid"
    summary: str
    key_positives: List[str] = []
    key_risks: List[str] = []
    confidence: str                 # "High" | "Medium" | "Low"


class CriteriaSuggestion(BaseModel):
    criterion: str
    current_value: Any
    suggested_value: Any
    rationale: str


class LLMAnalyzeResponse(BaseModel):
    stock_commentaries: List[StockCommentary]
    criteria_suggestions: List[CriteriaSuggestion]
    overall_summary: str
    model_used: str
    provider_used: str
    tokens_used: Optional[int] = None


class LLMStatusResponse(BaseModel):
    provider: str
    model: str
    configured: bool
    reachable: Optional[bool] = None
    error: Optional[str] = None
