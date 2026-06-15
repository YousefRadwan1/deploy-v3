#!/bin/bash

# ============================================================
# Azure Web App Startup Script
# Downloads firecrawl_rag_db from Google Drive if not present
# ============================================================

set -e

echo "🚀 Starting deployment setup..."

# الـ DB المفروض تكون في /home/site/firecrawl_rag_db
# والـ app في    /home/site/wwwroot/
# نفس structure: PERSIST_DIRECTORY = "../firecrawl_rag_db"
DB_DIR="/home/site/firecrawl_rag_db"
APP_DIR="/home/site/wwwroot"

# ---- تحميل الـ DB من Google Drive لو مش موجودة ----
if [ ! -d "$DB_DIR" ] || [ ! -f "$DB_DIR/chroma.sqlite3" ]; then
    echo "📥 Vector database not found. Downloading from Google Drive..."

    pip install gdown --quiet

    mkdir -p "$DB_DIR"

    # تحميل الـ folder كاملة (folder ID من الـ link)
    gdown --folder "https://drive.google.com/drive/folders/1-wtq2wAT-V8uMH3dlg8qh0VVnTF3Mq45" \
          --output /home/site/ \
          --remaining-ok

    echo "✅ Database downloaded successfully!"
else
    echo "✅ Database already exists. Skipping download."
fi

# ---- تثبيت الـ requirements ----
echo "📦 Installing Python dependencies..."
pip install -r "$APP_DIR/requirements.txt" --quiet

# ---- تشغيل الـ app ----
echo "🟢 Starting FastAPI application..."
cd "$APP_DIR"
exec uvicorn app:app --host 0.0.0.0 --port 8000
