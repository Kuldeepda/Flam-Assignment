# `queuectl` - A CLI-based Background Job Queue

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

## Setup & Installation (Windows)

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/Kuldeepda/Flam-Assignment
    cd queuectl
    ```

2.  **Create a virtual environment:**

    ```bash
    py -m venv venv
    ```

3.  **Activate the virtual environment:**

    ```bash
    .\venv\Scripts\activate
    ```

4.  **Install dependencies:**

    ```bash
    pip install "typer[all]" rich filelock
    ```

5.  **Initialize the storage:**
    (This happens automatically the first time you run any command)
    ```bash
    py queuectl.py status
    ```

## Usage Examples (Windows)

Your main executable is `py queuectl.py`.

### 1. Enqueue a Job

Add a new job to the queue.

```bash
# Add a simple job
py queuectl.py enqueue "echo 'Hello from the queue'"

# Add a job that will fail
py queuectl.py enqueue "thiscommandwillfail"

# Add a job and override its retries
py queuectl.py enqueue "timeout 5" --max-retries 5
```

### 2. Start Workers

Run worker processes to execute pending jobs.

```bash
# Start a single worker
py queuectl.py worker start

# Start 4 workers in parallel
py queuectl.py worker start --count 4
```

Press `CTRL+C` for a graceful shutdown.

### 3. Check System Status

Get a summary of all jobs by state.

```bash
py queuectl.py status

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
py queuectl.py list

# List all completed jobs
py queuectl.py list --state completed

# List all permanently failed jobs
py queuectl.py list --state dead
```

### 5. Configure Settings

Change system behavior, like retry counts.

```bash
# Set max retries to 5
py queuectl.py config set max_retries 5

# Set backoff base to 3 (delay = 3^attempts)
py queuectl.py config set backoff_base 3
```

## Architecture Overview

### Job Lifecycle

1.  **Enqueue:** A job is added via `py queuectl.py enqueue`. It's locked, appended to the `jobs` list in `queue.json`, and saved.
2.  **Processing:** A worker process calls `storage.get_next_job_for_worker()`. This function _atomically_ (using a file lock) reads `queue.json`, finds the first available job, updates its state to `processing`, and saves the file. This prevents any other worker from grabbing the same job.
3.  **Execution:** The worker executes the job's command using `subprocess.run()` with `shell=True`.
4.  **Success:** If the command exits with code `0`, the job's state is updated to `completed` (again, under a lock).
5.  **Failure:** If the command exits with a non-zero code or isn't found, `storage.handle_failed_job()` is called.
    - **Retry:** If `attempts < max_retries`, the `attempts` count is increased, the `run_at` timestamp is updated, and the state is set back to `pending`.
    - **Dead:** If `attempts >= max_retries`, the job is removed from the `jobs` list and added to the `dlq` list.

### Persistence

- Persistence is handled by a single **JSON file (`queue.json`)**.
- This file contains two top-level keys: `jobs` (for all active jobs) and `dlq` (for dead jobs).
- This approach is simple and human-readable.

### Worker Concurrency

- The `py queuectl.py worker start --count N` command uses Python's `multiprocessing` module to spawn `N` independent worker processes.
- **Race conditions are prevented using a lock file (`queue.lock`)** via the `filelock` library.
- Before any process reads or writes to `queue.json`, it must acquire this lock. This ensures that only one process can modify the file at a time, preventing data corruption or duplicate job processing.
- Graceful shutdown is handled by catching `KeyboardInterrupt` (CTRL+C) and signaling all child processes to stop.

## Testing Instructions (Windows)

### Shortcut
 For windows user
 ```cmd
    bash validate.sh
 ```
 For linux user 
  ```cmd
    chmod +x validate.sh
 ```
The most reliable way to test on Windows is to use two Command Prompt windows.

### Window 1: CLI Commands

Open your first Command Prompt and navigate to the project folder.

1.  **Clear old files** (It's okay if this gives a "File Not Found" error):

    ```cmd
    del queue.json queue.lock config.json
    ```

2.  **Set the configuration:**

    ```cmd
    py queuectl.py config set max_retries 2
    py queuectl.py config set backoff_base 1
    ```

3.  **Enqueue the test jobs:**

    ```cmd
    py queuectl.py enqueue "echo 'Job 1: Success'"
    py queuectl.py enqueue "thiscommandwillfail"
    ```

4.  **Check the initial status:**
    ```cmd
    py queuectl.py status
    ```
    _You should see 2 pending jobs._

### Window 2: Worker

Open a **second** Command Prompt and navigate to the same project folder.

1.  **Activate the virtual environment:**
    ```cmd
    .\venv\Scripts\activate
    ```
2.  **Start the worker:**
    ```cmd
    py queuectl.py worker start
    ```
    _You will see the worker start, process "Job 1: Success," and then try (and fail) to run "thiscommandwillfail" twice._
3.  Wait about 10 seconds, then press **CTRL+C** in this window to stop the worker.

### Back to Window 1: Check Results

1.  **Check the final status:**

    ```cmd
    py queuectl.py status
    ```

    _You should see 0 pending, 1 completed, and 1 dead._

2.  **Verify the `completed` list:**

    ```cmd
    py queuectl.py list --state completed
    ```

    _You should see "Job 1: Success"._

3.  **Verify the `dead` list:**
    ```cmd
    py queuectl.py list --state dead
    ```
    _You should see "thiscommandwillfail"._

## Assumptions & Trade-offs

### JSON vs. SQLite
The primary architectural decision was to use a **JSON file** for persistence.

- **Pro:** The `queue.json` file is human-readable, easy to inspect, and requires no external database.
- **Trade-off:** This approach has a **significant performance bottleneck**.  
  Every operation (**enqueue**, **get job**, **update job**, **heartbeat**) requires a **global file lock**, which prevents parallel execution.  
  As the number of workers increases, they will spend most of their time waiting for the lock.  
  A database like **SQLite** would handle this much more efficiently.

### Job Output
Job output (**stdout/stderr**) is printed to the console of the worker that ran it,  
but it is **not captured or stored** in the job’s data file.
