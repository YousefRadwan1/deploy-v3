# 👶 UNICEF Milestone RAG Assistant — Azure Deployment Guide

## هيكل المشروع

```
repo/                          ← root الـ GitHub repo
├── app.py                     ← FastAPI app
├── requirements.txt
├── startup.sh                 ← Azure startup script (يحمّل الـ DB من Drive)
├── firecrawl_embedding.py     ← ingest script (local use only)
├── .gitignore
└── .github/
    └── workflows/
        └── azure-deploy.yml   ← GitHub Actions CI/CD
```

> ⚠️ **الـ `firecrawl_rag_db/` لا ترفعها على GitHub** — هتتحمل تلقائياً من Google Drive عند أول تشغيل على Azure.

---

## خطوات الـ Deploy على Azure

### 1️⃣ إنشاء Azure Web App

1. اذهب إلى [portal.azure.com](https://portal.azure.com)
2. أنشئ **Web App** بالإعدادات دي:
   - **Runtime**: Python 3.11
   - **OS**: Linux
   - **Region**: أي region قريبة
   - **Plan**: B2 أو أعلى (عشان الـ ML models محتاجة RAM)

---

### 2️⃣ إعداد الـ Environment Variables على Azure

في الـ Web App → **Configuration** → **Application Settings**، أضف:

| Key | Value |
|-----|-------|
| `HUGGINGFACEHUB_API_TOKEN` | `hf_xxxx...` |
| `GROQ_API_KEY` | `gsk_xxxx...` |
| `PERSIST_DIRECTORY` | `/home/site/firecrawl_rag_db` |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |

---

### 3️⃣ إعداد الـ Startup Command على Azure

في الـ Web App → **Configuration** → **General Settings**:

```
bash /home/site/wwwroot/startup.sh
```

> الـ `startup.sh` هيعمل الآتي تلقائياً:
> 1. يتحقق لو الـ DB موجودة
> 2. لو مش موجودة → يحملها من Google Drive
> 3. يثبّت الـ requirements
> 4. يشغّل uvicorn

---

### 4️⃣ ربط GitHub بـ Azure (CI/CD)

#### أ) إعداد GitHub Secrets
في الـ GitHub repo → **Settings** → **Secrets and variables** → **Actions**:

| Secret | طريقة الحصول عليه |
|--------|-------------------|
| `AZURE_WEBAPP_NAME` | اسم الـ Web App على Azure |
| `AZURE_WEBAPP_PUBLISH_PROFILE` | من Azure → Web App → **Get publish profile** (حمّل الملف والصق محتواه) |

#### ب) الـ Deploy التلقائي
بعد الإعداد، أي `git push` على `main` هيعمل deploy تلقائي عبر GitHub Actions.

---

### 5️⃣ أول Deploy يدوي (لو عايز تتحقق)

```bash
git init
git add .
git commit -m "Initial deploy"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

---

## ملاحظات مهمة

- **أول تشغيل**: هياخد وقت (5-10 دقايق) عشان يحمّل الـ DB من Google Drive
- **بعد كده**: الـ DB بتتحفظ في `/home/site/` وما بتتحملش تاني
- **الـ Google Drive folder** لازم يكون **Public** أو accessible بدون login
- لو Azure restarts، الـ `/home/site/` بتتحفظ (persistent storage)

---

## التحقق من الـ Deploy

بعد الـ deploy، افتح:
```
https://YOUR_APP_NAME.azurewebsites.net/
```

ولو عايز تشوف الـ logs:
```
https://YOUR_APP_NAME.scm.azurewebsites.net/api/logstream
```
