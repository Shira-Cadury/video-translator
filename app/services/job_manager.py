import uuid
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class JobManager:
    def __init__(self):
        self.jobs = {}
        
    def create_job(self):
        job_id = str(uuid.uuid4())
        
        self.jobs[job_id] = {
            "status": "pending",
            "progress": 0,
            "created_at": datetime.now().isoformat(),
            "result": None
        } 
        
        logger.info(f"[JOB CREATED] {job_id}")
        return job_id
    
    
    def cancel_job(self, job_id):
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = "cancelled"
            logger.info(f"[JOB CANCELLED] {job_id}")
    
    def update_progress(self, job_id, progress):
        if job_id in self.jobs:
            self.jobs[job_id]["progress"] = progress
    
    
    def update_status(self, job_id, status):
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = status
            
            
    def save_result(self, job_id, result):
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = "completed"
            self.jobs[job_id]["result"] = result
            
            
    def get_job(self, job_id):
        return self.jobs.get(job_id)                   