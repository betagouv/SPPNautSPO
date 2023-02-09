#!/bin/bash

# Generate schema if not exist (else failed but it is ignored)
PYTHONPATH=. procrastinate --app=workers.procrastinate_app schema --apply

# Start worker(s)
echo "Launching workers..."
PYTHONPATH=. procrastinate --app=workers.procrastinate_app worker &
echo "Workers launched"

# Start server
echo "Launching server..."
gunicorn --bind :8080 --workers 3 --timeout 300 core.wsgi:application $1 &
echo "Server launched..."

# Catch SIGTERM or EXIT signal and send SIGTERM to sub process
# https://stackoverflow.com/questions/360201/how-do-i-kill-background-processes-jobs-when-my-shell-script-exits
trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?
