#!/bin/bash

# ============================================================
# Azure Web App Startup Script
# Downloads firecrawl_rag_db from Google Drive if not present
# ============================================================

echo "🚀 Starting deployment setup..."

DB_DIR="/home/site/firecrawl_rag_db"
APP_DIR="/home/site/wwwroot"

# ---- تحميل الـ DB من Google Drive لو مش موجودة ----
if [ ! -f "$DB_DIR/chroma.sqlite3" ]; then
    echo "📥 Vector database not found at $DB_DIR. Downloading from Google Drive..."

    pip install gdown --quiet

    mkdir -p "$DB_DIR"

    gdown --folder "https://drive.google.com/drive/folders/1-wtq2wAT-V8uMH3dlg8qh0VVnTF3Mq45" \
          --output "$DB_DIR" \
          --remaining-ok

    if [ -f "$DB_DIR/chroma.sqlite3" ]; then
        echo "✅ Database downloaded successfully!"
    else
        echo "⚠️  WARNING: chroma.sqlite3 still not found after download attempt."
        echo "⚠️  Listing $DB_DIR contents for debugging:"
        ls -la "$DB_DIR" || echo "Directory does not even exist."
    fi
else
    echo "✅ Database already exists at $DB_DIR. Skipping download."
fi

# ---- تشغيل الـ app عبر gunicorn (متوافق مع Azure Linux) ----
echo "🟢 Starting FastAPI application..."
cd "$APP_DIR"
exec gunicorn --bind=0.0.0.0:8000 --timeout 600 --workers 4 --worker-class uvicorn.workers.UvicornWorker app:app
