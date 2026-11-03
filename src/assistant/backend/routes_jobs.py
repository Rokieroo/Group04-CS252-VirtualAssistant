"""Status of background jobs, polled by the client (spec 8.5)."""

import json

from fastapi import APIRouter, HTTPException

from .dependencies import DB, CurrentUser
from .models import Job
from .schemas import JobOut

router = APIRouter(tags=["Jobs"])


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: DB, user: CurrentUser):
    """Only the user who started a job sees it; system jobs and others' jobs are 404."""
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "Job not found")
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "attempts": job.attempts,
        "result": None if job.result is None else json.loads(job.result),
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
