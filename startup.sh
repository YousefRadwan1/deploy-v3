#!/bin/bash

echo "🚀 Starting FastAPI application..."
cd /home/site/wwwroot
exec gunicorn --bind=0.0.0.0:8000 --timeout 600 --workers 4 --worker-class uvicorn.workers.UvicornWorker app:app
