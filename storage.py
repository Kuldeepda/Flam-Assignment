import json
import uuid
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from filelock import FileLock
from config import get_config

CONFIG = get_config()
STORAGE_FILE = CONFIG['storage_file']
LOCK_FILE = CONFIG['lock_file']

def _get_lock():
    return FileLock(LOCK_FILE, timeout=10)

def _read_data() -> Dict[str, List[Dict[str, Any]]]:
    try:
        with open(STORAGE_FILE, 'r') as f:
            data = json.load(f)
            if "active_workers" not in data:
                data["active_workers"] = []
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"jobs": [], "dlq": [], "active_workers": []}

def _write_data(data: Dict[str, List[Dict[str, Any]]]):
    with open(STORAGE_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def init_storage():
    with _get_lock():
        try:
            with open(STORAGE_FILE, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            with open(STORAGE_FILE, 'w') as f:
                json.dump({"jobs": [], "dlq": [], "active_workers": []}, f)

def enqueue_job(command: str, max_retries: Optional[int] = None) -> str:
    cfg = get_config()
    job_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    job = {
        "id": job_id,
        "command": command,
        "state": "pending",
        "attempts": 0,
        "max_retries": max_retries if max_retries is not None else cfg['max_retries'],
        "run_at": now,
        "created_at": now,
        "updated_at": now,
    }
    
    with _get_lock():
        data = _read_data()
        data["jobs"].append(job)
        _write_data(data)
        
    return job_id

def get_next_job_for_worker() -> Optional[Dict[str, Any]]:
    with _get_lock():
        data = _read_data()
        now = datetime.utcnow()
        
        found_job = None
        job_index = -1

        # Sort by creation time to process oldest first
        pending_jobs = []
        for i, job in enumerate(data["jobs"]):
            if job["state"] == "pending" and job["run_at"] <= now.isoformat():
                pending_jobs.append((i, job))
        
        # Sort by created_at
        pending_jobs.sort(key=lambda x: x[1]["created_at"])

        if pending_jobs:
            job_index, found_job = pending_jobs[0]
            found_job["state"] = "processing"
            found_job["updated_at"] = datetime.utcnow()
            data["jobs"][job_index] = found_job
            _write_data(data)
            return found_job
        else:
            return None

def update_job_to_completed(job_id: str):
    with _get_lock():
        data = _read_data()
        job_found = False
        for job in data["jobs"]:
            if job["id"] == job_id:
                job["state"] = "completed"
                job["updated_at"] = datetime.utcnow()
                job_found = True
                break
        
        if job_found:
            _write_data(data)

def handle_failed_job(job: Dict[str, Any]):
    with _get_lock():
        data = _read_data()
        cfg = get_config()
        
        job_index = -1
        for i, j in enumerate(data["jobs"]):
            if j["id"] == job["id"]:
                job_index = i
                break
        
        if job_index == -1:
            return

        job_in_db = data["jobs"][job_index]
        job_in_db["attempts"] += 1
        
        if job_in_db["attempts"] >= job_in_db["max_retries"]:
            failed_job = data["jobs"].pop(job_index)
            failed_job["state"] = "dead"
            data["dlq"].append(failed_job)
        else:
            delay_seconds = cfg['backoff_base'] ** job_in_db['attempts']
            job_in_db["run_at"] = datetime.utcnow() + timedelta(seconds=delay_seconds)
            job_in_db["state"] = "pending"
            job_in_db["updated_at"] = datetime.utcnow()
            data["jobs"][job_index] = job_in_db
        
        _write_data(data)

def _get_active_worker_count(data: dict) -> int:
    cfg = get_config()
    timeout_seconds = cfg['worker_timeout_seconds']
    now = datetime.utcnow()
    
    active_workers = []
    
    for worker in data.get("active_workers", []):
        try:
            last_heartbeat = datetime.fromisoformat(worker["last_heartbeat"])
            if (now - last_heartbeat).total_seconds() < timeout_seconds:
                active_workers.append(worker)
        except (ValueError, TypeError):
            continue # Skip bad entries
            
    data["active_workers"] = active_workers
    return len(active_workers)

def get_status() -> Dict[str, int]:
    with _get_lock():
        data = _read_data()
        active_worker_count = _get_active_worker_count(data)
        _write_data(data) # Save data to clean up stale workers
    
    stats = {}
    for job in data["jobs"]:
        state = job["state"]
        stats[state] = stats.get(state, 0) + 1
        
    stats["dead"] = len(data["dlq"])
    stats["active_workers"] = active_worker_count
    return stats

def list_jobs(state: str) -> List[Dict[str, Any]]:
    with _get_lock():
        data = _read_data()
    
    if state == 'dead':
        return data["dlq"]
    else:
        return [job for job in data["jobs"] if job["state"] == state]

def register_worker(pid: int):
    with _get_lock():
        data = _read_data()
        now = datetime.utcnow()
        
        # Remove any old entry for this PID just in case
        data["active_workers"] = [w for w in data["active_workers"] if w["pid"] != pid]
        
        data["active_workers"].append({
            "pid": pid,
            "last_heartbeat": now
        })
        _write_data(data)
    print(f"Worker {pid} registered.")

def unregister_worker(pid: int):
    with _get_lock():
        data = _read_data()
        data["active_workers"] = [w for w in data["active_workers"] if w["pid"] != pid]
        _write_data(data)
    print(f"Worker {pid} unregistered.")

def worker_heartbeat(pid: int):
    with _get_lock():
        data = _read_data()
        worker_found = False
        for worker in data["active_workers"]:
            if worker["pid"] == pid:
                worker["last_heartbeat"] = datetime.utcnow()
                worker_found = True
                break
        
        if worker_found:
            _write_data(data)
        else:
            # Worker wasn't in list, maybe from a stale file. Register it.
            _write_data(data)
            register_worker(pid) # This will re-call and get the lock


def retry_dlq_job(job_id: str) -> bool:
    with _get_lock():
        data = _read_data()
        
        job_index = -1
        for i, job in enumerate(data["dlq"]):
            if job["id"] == job_id:
                job_index = i
                break
        
        if job_index == -1:
            return False # Job not found in DLQ
            
        # Remove from DLQ and reset for queue
        job = data["dlq"].pop(job_index)
        job["state"] = "pending"
        job["attempts"] = 0
        job["run_at"] = datetime.utcnow()
        job["updated_at"] = datetime.utcnow()
        
        # Add back to main jobs list
        data["jobs"].append(job)
        _write_data(data)
        return True

init_storage()