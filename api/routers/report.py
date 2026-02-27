"""
Report endpoints: generate HTML report, serve latest.
"""
from pathlib import Path
from typing import Dict
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException

import api.deps  # noqa

router = APIRouter()
_jobs: Dict[str, Dict] = {}


def _run_report_generation(job_id: str):
    try:
        from src.reporting.report_generator import ReportGenerator
        gen = ReportGenerator()
        html = gen.generate_report()
        saved_path = gen.save_report(html)
        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = {"path": str(saved_path), "filename": Path(saved_path).name}
    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)


@router.post("/report/generate")
async def generate_report(background_tasks: BackgroundTasks):
    """Trigger HTML report generation (background job)."""
    job_id = str(uuid4())
    _jobs[job_id] = {"status": "running", "result": None, "error": None}
    background_tasks.add_task(_run_report_generation, job_id)
    return {"job_id": job_id, "status": "running", "message": "Report generation started"}


@router.get("/report/status/{job_id}")
async def get_report_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return {"job_id": job_id, "status": "not_found"}
    return {"job_id": job_id, **job}


@router.get("/report/latest")
async def get_latest_report():
    """Return metadata for the most recently generated report."""
    try:
        from src.utils import get_data_dir
        reports_dir = get_data_dir() / "reports"
        if not reports_dir.exists():
            raise HTTPException(status_code=404, detail="No reports directory found")

        html_files = sorted(reports_dir.glob("report_*.html"), reverse=True)
        if not html_files:
            raise HTTPException(status_code=404, detail="No reports found")

        latest = html_files[0]
        import os
        mtime = os.path.getmtime(latest)
        from datetime import datetime
        generated_at = datetime.fromtimestamp(mtime).isoformat()

        return {
            "filename": latest.name,
            "generated_at": generated_at,
            "html_url": f"/reports/{latest.name}",
            "size_kb": round(latest.stat().st_size / 1024, 1),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/list")
async def list_reports():
    """List all available HTML reports."""
    try:
        from src.utils import get_data_dir
        reports_dir = get_data_dir() / "reports"
        if not reports_dir.exists():
            return {"reports": []}

        import os
        from datetime import datetime
        html_files = sorted(reports_dir.glob("report_*.html"), reverse=True)
        reports = []
        for f in html_files[:20]:  # Last 20 reports
            mtime = os.path.getmtime(f)
            reports.append({
                "filename": f.name,
                "generated_at": datetime.fromtimestamp(mtime).isoformat(),
                "html_url": f"/reports/{f.name}",
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
        return {"reports": reports}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
