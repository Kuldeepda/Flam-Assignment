# `queuectl` - A CLI-based Background Job Queue

`queuectl` is a minimal, production-grade background job queue system built in Python. It manages background jobs with worker processes, handles automatic retries with exponential backoff, and maintains a Dead Letter Queue (DLQ) for permanently failed jobs.

This project was built as part of the Backend Developer Internship Assignment.

**Demo:** [Link to your CLI demo video on Google Drive/YouTube]

## Features

- **Enqueue Jobs:** Add shell commands to a persistent queue.
- **Multiple Workers:** Run multiple worker processes in parallel to consume jobs.
- **Persistent Storage:** Uses a **JSON file** (`queue.json`) for persistence.
- **Concurrency Safe:** Safely processes jobs across multiple workers using a lock file to prevent race conditions.
- **Retry & Backoff:** Automatically retries failed jobs using configurable exponential backoff.
- **Dead Letter Queue (DLQ):** Moves jobs to a DLQ after all retry attempts are exhausted.
- **CLI Interface:** All functionality is exposed through a clean, easy-to-use CLI.

## Technology Stack

- **Language:** Python 3
- **CLI:** [Typer](https://typer.tiangolo.com/)
- **Persistence:** JSON
- **Concurrency:** `multiprocessing` module and `filelock` library

## Setup & Installation

1.  **Clone the repository:**

    ```bash
    git clone [YOUR_REPO_LINK]
    cd queuectl
    ```

2.  **Create a virtual environment (Recommended):**

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies:**

    ```bash
    pip install "typer[all]" rich filelock
    ```

4.  **Make the CLI executable:**

    ```bash
    chmod +x queuectl.py
    ```

5.  **Initialize the storage:**
    (This happens automatically the first time you run any command)
    ```bash
    ./queuectl.py status
    ```

## Usage Examples

Your main executable is `./queuectl.py`.

### 1. Enqueue a Job

Add a new job to the queue.

```bash
# Add a simple job
./queuectl.py enqueue "echo 'Hello from the queue'"

# Add a job that will fail
./queuectl.py enqueue "false"

# Add a job and override its retries
./queuectl.py enqueue "sleep 5" --max-retries 5
```

### 2. Start Workers

Run worker processes to execute pending jobs.

```bash
# Start a single worker
./queuectl.py worker start

# Start 4 workers in parallel
./queuectl.py worker start --count 4
```

Press `CTRL+C` for a graceful shutdown.

### 3. Check System Status

Get a summary of all jobs by state.

```bash
./queuectl.py status

# Example Output:
# --- Job Status Summary ---
# ┌───────────┬───────┐
# │ State     │ Count │
# ├───────────┼───────┤
# │ pending   │ 5     │
# │ completed │ 12    │
# │ dead      │ 2     │
# │ Total     │ 19    │
# └───────────┴───────┘
#
# Active Workers: N/A
```

### 4. List Jobs

List all jobs in a specific state.

```bash
# List all pending jobs (default)
./queuectl.py list

# List all completed jobs
./queuectl.py list --state completed

# List all permanently failed jobs
./queuectl.py list --state dead
```

### 5. Configure Settings

Change system behavior, like retry counts.

```bash
# See current config (by opening config.json)
cat config.json

# Set max retries to 5
./queuectl.py config set max-retries 5

# Set backoff base to 3 (delay = 3^attempts)
./queuectl.py config set backoff_base 3
```

## Architecture Overview

### Job Lifecycle

1.  **Enqueue:** A job is added via `queuectl enqueue`. It's locked, appended to the `jobs` list in `queue.json`, and saved.
2.  **Processing:** A worker process calls `storage.get_next_job_for_worker()`. This function _atomically_ (using a file lock) reads `queue.json`, finds the first available job, updates its state to `processing`, and saves the file. This prevents any other worker from grabbing the same job.
3.  **Execution:** The worker executes the job's command using `subprocess.run()`.
4.  **Success:** If the command exits with code `0`, the job's state is updated to `completed` (again, under a lock).
5.  **Failure:** If the command exits with a non-zero code or isn't found, `storage.handle_failed_job()` is called.
    - **Retry:** If `attempts < max_retries`, the `attempts` count is increased, the `run_at` timestamp is updated, and the state is set back to `pending`.
    - **Dead:** If `attempts >= max_retries`, the job is removed from the `jobs` list and added to the `dlq` list.

### Persistence

- Persistence is handled by a single **JSON file (`queue.json`)**.
- This file contains two top-level keys: `jobs` (for all active jobs) and `dlq` (for dead jobs).
- This approach is simple and human-readable.

### Worker Concurrency

- The `queuectl worker start --count N` command uses Python's `multiprocessing` module to spawn `N` independent worker processes.
- **Race conditions are prevented using a lock file (`queue.lock`)** via the `filelock` library.
- Before any process reads or writes to `queue.json`, it must acquire this lock. This ensures that only one process can modify the file at a time, preventing data corruption or duplicate job processing.
- Graceful shutdown is handled by catching `KeyboardInterrupt` (CTRL+C) and signaling all child processes to stop.

## Testing Instructions

A simple validation script is provided to test the core end-to-end flow.

1.  Make the script executable:
    ```bash
    chmod +x validate.sh
    ```
2.  Run the script:
    ```bash
    ./validate.sh
    ```

This script will:

1.  Clear the storage.
2.  Enqueue one job that succeeds and two that fail.
3.  Start a worker in the background and let it run for 10 seconds.
4.  Stop the worker gracefully.
5.  Check the `status`, `completed`, and `dead` lists to verify the jobs ended in the correct state.

## Assumptions & Trade-offs

- **Trade-off (JSON vs. SQLite):** This implementation uses a JSON file, as requested.
  - **Pro:** The storage is human-readable and requires no external database server.
  - **Con:** This approach is **much slower** and **scales poorly**. Every single operation (enqueue, get job, update job) must lock the _entire_ file, read all data, make one small change, and write all data back.
  - **Bottleneck:** The file lock becomes a global bottleneck. With many workers, most will be idle waiting for the lock. A database like SQLite handles this much more efficiently with transactions and row-level locking.
- **Assumption:** Worker tracking (`queuectl status` for active workers) is not implemented, as it would require a more complex process management system.
- **Simplification:** Job output (stdout/stderr) is printed by the worker but not stored.
"# Flam-Assignment" 
