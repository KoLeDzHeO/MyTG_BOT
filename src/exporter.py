import json
import logging
import time
from telegram.ext import JobQueue, ContextTypes

from .config import config
from . import db

_DEBOUNCE_SECONDS = 3
_JOB_NAME = "export_full_json"
_last_warn = 0


async def schedule_export(job_queue: JobQueue | None) -> None:
    """Schedule full export with debounce."""
    if not job_queue:
        logging.warning("export schedule skipped: no job queue")
        return
    jobs = job_queue.get_jobs_by_name(_JOB_NAME)
    if jobs:
        jobs[0].schedule_removal()
    job_queue.run_once(_export_full_json_job, _DEBOUNCE_SECONDS, name=_JOB_NAME)


async def _export_full_json_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    global _last_warn
    if not config.MEGA_URL:
        now = time.time()
        if now - _last_warn > 600:
            logging.warning("mega export skipped: MEGA_URL not set")
            _last_warn = now
        return
    try:
        records = await db.fetch_all_movies_for_export()
        with open("movies.json", "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False)
        logging.info("exported %d movies", len(records))
    except Exception:
        logging.exception("export_full_json failed")
