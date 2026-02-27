"""
Portfolio endpoints: paper portfolio positions and P&L.
"""
from fastapi import APIRouter, HTTPException

import api.deps  # noqa

router = APIRouter()


@router.get("/portfolio/all")
async def get_all_portfolios():
    """Summary for all 3 paper portfolio funds."""
    try:
        from src.collector.paper_portfolio import PaperPortfolioManager
        mgr = PaperPortfolioManager()
        summaries = mgr.get_all_summaries()
        return {"funds": summaries}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio/{fund_name}")
async def get_portfolio(fund_name: str):
    """Full portfolio state for a specific fund: positions + summary + recent trades."""
    try:
        from src.collector.paper_portfolio import PaperPortfolio
        portfolio = PaperPortfolio(fund_name)
        summary = portfolio.get_portfolio_summary()
        positions_df = portfolio.get_positions()
        trades_df = portfolio.trades

        positions = positions_df.to_dict("records") if not positions_df.empty else []

        # Last 50 trades
        trades = []
        if trades_df is not None and not trades_df.empty:
            trades = trades_df.tail(50).to_dict("records")

        # Clean NaN values for JSON serialization
        import math
        def clean(obj):
            if isinstance(obj, float) and math.isnan(obj):
                return None
            return obj

        positions = [{k: clean(v) for k, v in p.items()} for p in positions]
        trades = [{k: clean(v) for k, v in t.items()} for t in trades]

        return {
            "fund": fund_name,
            "summary": summary,
            "positions": positions,
            "trades": trades,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio/{fund_name}/equity-curve")
async def get_equity_curve(fund_name: str):
    """Daily value history for a fund's paper portfolio."""
    try:
        from src.collector.paper_portfolio import PaperPortfolio
        portfolio = PaperPortfolio(fund_name)
        df = portfolio.get_daily_values()
        if df is None or df.empty:
            return {"fund": fund_name, "equity_curve": []}
        return {"fund": fund_name, "equity_curve": df.to_dict("records")}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
