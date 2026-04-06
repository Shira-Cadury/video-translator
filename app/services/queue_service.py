import queue
import threading
import logging

logger = logging.getLogger(__name__)


class QueueService:
    def __init__(self):
        self.job_queue = queue.Queue()
        self._position_map = {}   
        self._lock = threading.Lock()

        self.worker_thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name="QueueWorker"
        )
        self.worker_thread.start()
        logger.info("[QUEUE] Worker thread started")

    def add_job(self, func, *args):
        job_id = args[0] if args else "unknown"

        with self._lock:
            position = self.job_queue.qsize() + 1
            self._position_map[job_id] = position

        self.job_queue.put((func, args, job_id))
        logger.info(f"[QUEUE] Job {job_id} added — position {position} in queue")

    def get_position(self, job_id: str) -> int | None:
        with self._lock:
            return self._position_map.get(job_id)

    def get_queue_size(self) -> int:
        return self.job_queue.qsize()

    def _worker(self):
        while True:
            func, args, job_id = self.job_queue.get()
            try:
                with self._lock:
                    self._position_map.pop(job_id, None)

                logger.info(f"[QUEUE] Starting job {job_id} ({func.__name__})")
                func(*args)
                logger.info(f"[QUEUE] Job {job_id} finished successfully")

            except Exception as e:
                import traceback
                logger.error(f"[QUEUE] Job {job_id} raised an unhandled exception: {e}")
                logger.error(traceback.format_exc())
            finally:
                self.job_queue.task_done()
