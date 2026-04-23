import queue
import threading
import logging

logger = logging.getLogger(__name__)

class QueueService:
    def __init__(self, num_workers=1):
        self.job_queue = queue.Queue()
        self._lock = threading.Lock()

        self.workers = []
        for i in range(num_workers):
            worker_thread = threading.Thread(
                target=self._worker,
                daemon=True,
                name=f"QueueWorker-{i+1}"
            )
            worker_thread.start()
            self.workers.append(worker_thread)
            
        logger.info(f"[QUEUE] {num_workers} Worker thread(s) started")

    def add_job(self, func, *args):
        job_id = args[0] if args else "unknown"

        with self._lock:
            self.job_queue.put((func, args, job_id))
            position = self._calculate_position_unlocked(job_id)
            
        logger.info(f"[QUEUE] Job {job_id} added — position {position} in queue")

    def get_position(self, job_id: str) -> int | None:
        with self._lock:
            return self._calculate_position_unlocked(job_id)
            
    def _calculate_position_unlocked(self, job_id: str) -> int | None:
        with self.job_queue.mutex:
            queue_items = list(self.job_queue.queue)
            for index, item in enumerate(queue_items):
                if item[2] == job_id:
                    return index + 1 
        return None 

    def get_queue_size(self) -> int:
        return self.job_queue.qsize()

    def _worker(self):
        while True:
            func, args, job_id = self.job_queue.get()
            try:
                logger.info(f"[QUEUE] Starting job {job_id} ({func.__name__})")
                func(*args)
                logger.info(f"[QUEUE] Job {job_id} finished successfully")

            except Exception as e:
                import traceback
                logger.error(f"[QUEUE] Job {job_id} raised an unhandled exception: {e}")
                logger.error(traceback.format_exc())
            finally:
                self.job_queue.task_done()