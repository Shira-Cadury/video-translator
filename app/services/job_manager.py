import uuid
import threading
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class JobManager:
    def __init__(self):
        self.jobs = {}
        self._lock = threading.Lock()   

    def create_job(self):
        self.cleanup_old_jobs(max_jobs=200)
        job_id = str(uuid.uuid4())
        with self._lock:
            self.jobs[job_id] = {
                "status": "pending",
                "progress": 0,
                "created_at": datetime.now().isoformat(),
                "result": None
            }
        logger.info(f"[JOB CREATED] {job_id}")
        return job_id

    def cancel_job(self, job_id):
        with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = "cancelled"
                logger.info(f"[JOB CANCELLED] {job_id}")

    def update_progress(self, job_id, progress):
        with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id]["progress"] = progress

    def update_status(self, job_id, status):
        with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = status

    def save_result(self, job_id, result):
        with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = "completed"
                self.jobs[job_id]["result"] = result

    def fail_job(self, job_id, result):
        with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = "failed"
                self.jobs[job_id]["result"] = result
                logger.error(f"[JOB FAILED] {job_id}")

    def get_job(self, job_id):
        with self._lock:
            return self.jobs.get(job_id)

    def cleanup_old_jobs(self, max_jobs: int = 200):
        with self._lock:
            if len(self.jobs) <= max_jobs:
                return
            finished = [
                jid for jid, j in self.jobs.items()
                if j["status"] in ("completed", "failed", "cancelled")
            ]
            finished.sort(key=lambda jid: self.jobs[jid]["created_at"])
            to_remove = finished[:len(self.jobs) - max_jobs]
            for jid in to_remove:
                del self.jobs[jid]
            if to_remove:
                logger.info(f"[JOB MANAGER] Cleaned up {len(to_remove)} old jobs")
