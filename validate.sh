#!/bin/bash
echo "--- QueueCTL Validation Script ---"

echo "Clearing storage and config..."
rm -f queue.json queue.lock config.json

py queuectl.py config set max_retries 2
py queuectl.py config set backoff_base 1

echo ""
echo "--- 1. Enqueueing Jobs ---"
py queuectl.py enqueue "echo 'Job 1: Success'"
py queuectl.py enqueue "thiscommandwillfail"

echo ""
echo "--- 2. Initial Status ---"
py queuectl.py status
py queuectl.py list --state pending

echo ""
echo "--- 3. Starting Worker (in background) ---"
# Start the worker using the 'py' launcher
py queuectl.py worker start --count 1 &
WORK_PID=$!

echo "Worker started with PID $WORK_PID. Waiting 10 seconds for jobs to process..."
sleep 10

echo ""
echo "--- 4. Stopping Worker ---"
kill -INT $WORK_PID
wait $WORK_PID
echo "Worker stopped."

echo ""
echo "--- 5. Final Status Check ---"
py queuectl.py status

echo ""
echo "--- 6. Checking Completed Jobs ---"
py queuectl.py list --state completed

echo ""
echo "--- 7. Checking Dead Letter Queue ---"
py queuectl.py list --state dead

echo ""
echo "--- Validation Complete ---"