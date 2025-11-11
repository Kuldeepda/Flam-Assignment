import time
import subprocess
import shlex
import storage
import os
from config import get_config

def run_job(job: dict):
    print(f"Worker: Starting job {job['id']}: {job['command']}")
    try:
        # Use shell=True to allow Windows to find built-in commands like 'echo'
        result = subprocess.run(
            job['command'], 
            capture_output=True, 
            text=True, 
            timeout=60, 
            shell=True
        )
        
        if result.returncode == 0:
            print(f"Worker: Job {job['id']} completed successfully.")
            storage.update_job_to_completed(job['id'])
        else:
            print(f"Worker: Job {job['id']} failed with code {result.returncode}.")
            print(f"Worker: Stderr: {result.stderr}")
            storage.handle_failed_job(job)
            
    except FileNotFoundError:
        print(f"Worker: Job {job['id']} failed. Command not found: {job['command']}")
        storage.handle_failed_job(job)
    except subprocess.TimeoutExpired:
        print(f"Worker: Job {job['id']} timed out.")
        storage.handle_failed_job(job)
    except Exception as e:
        print(f"Worker: Job {job['id']} failed with unexpected error: {e}")
        storage.handle_failed_job(job)


def start_worker_loop(stop_event):
    pid = os.getpid()
    cfg = get_config()
    heartbeat_interval = cfg['worker_heartbeat_seconds']
    last_heartbeat = time.time()
    
    try:
        storage.register_worker(pid)
        print(f"Worker process {pid} started...")
        
        while not stop_event.is_set():
            now = time.time()
            if (now - last_heartbeat) > heartbeat_interval:
                storage.worker_heartbeat(pid)
                last_heartbeat = now
            
            job = storage.get_next_job_for_worker()
            
            if job:
                run_job(job)
            else:
                try:
                    # Sleep, but check for stop_event frequently
                    stop_event.wait(timeout=1.0)
                except KeyboardInterrupt:
                    break # Exit loop on interrupt
    
    finally:
        # This will run on graceful shutdown (CTRL+C)
        storage.unregister_worker(pid)
        print(f"Worker process {pid} shutting down...")