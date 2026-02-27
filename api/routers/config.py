"""
Config endpoints: read and write settings.yaml sections.
After any write, invalidates the src.utils config cache so the new values
are picked up immediately by all subsequent src.* module calls.
"""
from pathlib import Path
from typing import Any, Dict

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import api.deps  # noqa

router = APIRouter()


def _get_config_path() -> Path:
    from src.utils import get_config_dir
    return get_config_dir() / "settings.yaml"


def _read_config() -> Dict[str, Any]:
    path = _get_config_path()
    with open(path) as f:
        return yaml.safe_load(f)


def _write_config(cfg: Dict[str, Any]) -> None:
    """Write config atomically and invalidate the utils cache."""
    import src.utils as _utils
    path = _get_config_path()
    tmp = path.with_suffix(".yaml.tmp")
    with open(tmp, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    tmp.rename(path)
    _utils._config_cache.clear()


def _deep_merge(base: Dict, updates: Dict) -> Dict:
    """Merge updates into base, only touching non-None values."""
    result = dict(base)
    for key, value in updates.items():
        if value is None:
            continue  # Skip None — preserve existing value
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# Generic section GET/PUT
# ---------------------------------------------------------------------------
VALID_SECTIONS = {
    "technical": "technical_defaults",
    "fundamental": "fundamental_defaults",
    "backtest": "backtest",
    "screener": "screener",
    "llm": "llm",
    "email": "email",
    "data_collection": "data_collection",
}


@router.get("/config/{section}")
async def get_config_section(section: str):
    """Read a config section from settings.yaml."""
    if section not in VALID_SECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown section '{section}'. Valid: {list(VALID_SECTIONS.keys())}"
        )
    try:
        cfg = _read_config()
        key = VALID_SECTIONS[section]
        return {"section": section, "config": cfg.get(key, {})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config/{section}")
async def update_config_section(section: str, updates: Dict[str, Any]):
    """Update a config section. Only provided (non-null) keys are changed."""
    if section not in VALID_SECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown section '{section}'. Valid: {list(VALID_SECTIONS.keys())}"
        )
    try:
        cfg = _read_config()
        key = VALID_SECTIONS[section]
        existing = cfg.get(key, {})
        cfg[key] = _deep_merge(existing, updates)
        _write_config(cfg)
        return {"status": "ok", "section": section, "config": cfg[key]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Fund config — special case because it's nested under funds.<name>
# ---------------------------------------------------------------------------
@router.get("/config/funds/{fund_name}")
async def get_fund_config(fund_name: str):
    """Read configuration for a specific fund."""
    try:
        cfg = _read_config()
        funds = cfg.get("funds", {})
        if fund_name not in funds:
            raise HTTPException(status_code=404, detail=f"Fund '{fund_name}' not found")
        return {"fund": fund_name, "config": funds[fund_name]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config/funds/{fund_name}")
async def update_fund_config(fund_name: str, updates: Dict[str, Any]):
    """Update configuration for a specific fund."""
    try:
        cfg = _read_config()
        funds = cfg.get("funds", {})
        if fund_name not in funds:
            raise HTTPException(status_code=404, detail=f"Fund '{fund_name}' not found")
        funds[fund_name] = _deep_merge(funds[fund_name], updates)
        cfg["funds"] = funds
        _write_config(cfg)
        return {"status": "ok", "fund": fund_name, "config": funds[fund_name]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/all")
async def get_all_config():
    """Return full settings.yaml (without credentials)."""
    try:
        cfg = _read_config()
        return {"config": cfg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Watchlist management
# ---------------------------------------------------------------------------
@router.get("/config/watchlist")
async def get_watchlist():
    """Return current watchlist."""
    try:
        cfg = _read_config()
        return {"watchlist": cfg.get("watchlist", {})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class WatchlistUpdate(BaseModel):
    core: list = None
    sector_etfs: list = None
    radar: list = None


@router.put("/config/watchlist")
async def update_watchlist(updates: WatchlistUpdate):
    """Update one or more watchlist groups."""
    try:
        cfg = _read_config()
        wl = cfg.get("watchlist", {})
        if updates.core is not None:
            wl["core"] = [t.upper() for t in updates.core]
        if updates.sector_etfs is not None:
            wl["sector_etfs"] = [t.upper() for t in updates.sector_etfs]
        if updates.radar is not None:
            wl["radar"] = [t.upper() for t in updates.radar]
        cfg["watchlist"] = wl
        _write_config(cfg)
        return {"status": "ok", "watchlist": wl}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
