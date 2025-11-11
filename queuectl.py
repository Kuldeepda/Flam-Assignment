#!/usr/bin/env python3
import typer
import json
import storage
import config as cfg
from worker import start_worker_loop
from typing import Optional, List
from rich.console import Console
from rich.table import Table
import multiprocessing
import time
import os

app = typer.Typer(help="queuectl: A CLI-based background job queue system.")
console = Console()

@app.command()
def enqueue(
    command: str = typer.Argument(..., help="The shell command to execute."),
    max_retries: Optional[int] = typer.Option(None, "--max-retries", help="Override max retries for this job.")
):
    try:
        job_id = storage.enqueue_job(command, max_retries)
        console.print(f"Job enqueued with ID: [bold]{job_id}[/bold]")
    except Exception as e:
        console.print(f"Error enqueuing job: {e}", style="red")
        raise typer.Exit(code=1)

@app.command()
def status():
    stats = storage.get_status()
    console.print("\n--- Job Status Summary ---", style="bold cyan")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("State", style="dim")
    table.add_column("Count")
    
    active_workers = stats.pop('active_workers', 0)
    
    total = 0
    for state, count in stats.items():
        table.add_row(state.capitalize(), str(count))
        total += count
    
    table.add_row("Total", str(total), style="bold")
    console.print(table)
    
    console.print(f"\nActive Workers: [bold green]{active_workers}[/bold green]")


@app.command(name="list")
def list_jobs(
    state: str = typer.Option("pending", "--state", help="Filter jobs by state (pending, processing, completed, dead).")
):
    valid_states = ['pending', 'processing', 'completed', 'dead']
    if state not in valid_states:
        console.print(f"Invalid state. Must be one of: {', '.join(valid_states)}", style="red")
        raise typer.Exit(code=1)

    jobs = storage.list_jobs(state)
    console.print(f"\n--- Jobs: [bold]{state.capitalize()}[/bold] ({len(jobs)}) ---", style="bold cyan")
    
    if not jobs:
        console.print("No jobs found in this state.")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID")
    table.add_column("Command")
    table.add_column("Updated At")

    if state != 'dead':
        table.add_column("Attempts")
        
    for job in jobs:
        if state == 'dead':
            table.add_row(
                job['id'],
                job['command'],
                job['updated_at']
            )
        else:
            table.add_row(
                job['id'],
                job['command'],
                job['updated_at'],
                str(job.get('attempts', 'N/A'))
            )
    
    console.print(table)


# --- Worker Sub-command ---
worker_app = typer.Typer(help="Manage worker processes.")
app.add_typer(worker_app, name="worker")

@worker_app.command()
def start(
    count: int = typer.Option(1, "--count", "-c", help="Number of worker processes to start.")
):
    console.print(f"Starting {count} worker(s)... Press CTRL+C to stop.")
    
    stop_event = multiprocessing.Event()
    processes: List[multiprocessing.Process] = []
    
    for _ in range(count):
        proc = multiprocessing.Process(target=start_worker_loop, args=(stop_event,))
        proc.start()
        processes.append(proc)
        
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\nGraceful shutdown initiated... (telling workers to stop)")
        stop_event.set()
        
        for proc in processes:
            proc.join(timeout=5)
            if proc.is_alive():
                console.print(f"Worker {proc.pid} did not exit gracefully, terminating...", style="yellow")
                proc.terminate()
        
        console.print("All workers stopped. Exiting.")

# --- Config Sub-command ---
config_app = typer.Typer(help="Manage configuration.")
app.add_typer(config_app, name="config")

@config_app.command()
def set(
    key: str = typer.Argument(..., help="e.g., max_retries or backoff_base"),
    value: str = typer.Argument(..., help="The new value to set.")
):
    config = cfg.get_config()
    
    if key not in config:
        console.print(f"Unknown config key: [bold]{key}[/bold]", style="red")
        console.print(f"Available keys: {', '.join(config.keys())}")
        raise typer.Exit(code=1)
        
    try:
        original_type = type(config[key])
        config[key] = original_type(value)
    except ValueError:
        console.print(f"Invalid value type for {key}. Expected {original_type.__name__}.", style="red")
        raise typer.Exit(code=1)
        
    cfg.save_config(config)
    console.print(f"Config updated: [bold]{key}[/bold] = {config[key]}")


# --- DLQ Sub-command (NEW) ---
dlq_app = typer.Typer(help="Manage the Dead Letter Queue (DLQ).")
app.add_typer(dlq_app, name="dlq")

@dlq_app.command(name="list")
def dlq_list():
    """List all jobs in the Dead Letter Queue."""
    # This is just an alias for list --state dead
    list_jobs(state="dead")

@dlq_app.command(name="retry")
def dlq_retry(
    job_id: str = typer.Argument(..., help="The ID of the job to retry.")
):
    """Move a job from the DLQ back to the pending queue."""
    try:
        if storage.retry_dlq_job(job_id):
            console.print(f"Job [bold]{job_id}[/bold] moved from DLQ to pending queue.", style="green")
        else:
            console.print(f"Error: Job [bold]{job_id}[/bold] not found in DLQ.", style="red")
    except Exception as e:
        console.print(f"An error occurred: {e}", style="red")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    storage.init_storage()
    app()