web: cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: cd backend && celery -A app.tasks.celery_app worker -l info -Q cpu_queue,gpu_queue --concurrency=2