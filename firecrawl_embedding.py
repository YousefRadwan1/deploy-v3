import os
from dotenv import load_dotenv
from firecrawl import Firecrawl
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from tqdm import tqdm
import json
from urllib.parse import urlparse

load_dotenv()

# ====================== CONFIG ======================
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")

URLS = [
    "https://www.unicef.org/parenting/child-development/your-babys-developmental-milestones-2-months",
    "https://www.unicef.org/parenting/child-development/your-babys-developmental-milestones-4-months",
    "https://www.unicef.org/parenting/child-development/your-babys-developmental-milestones-6-months",
    "https://www.unicef.org/parenting/child-development/your-babys-developmental-milestones-9-months",
    "https://www.unicef.org/parenting/child-development/your-toddlers-developmental-milestones-1-year",
    "https://www.unicef.org/parenting/child-development/your-toddlers-developmental-milestones-18-months",
    "https://www.unicef.org/parenting/child-development/your-toddlers-developmental-milestones-2-years",
    "https://www.who.int/news-room/fact-sheets/detail/infant-and-young-child-feeding?utm_source=chatgpt.com",
    "https://www.cdc.gov/infant-toddler-nutrition/foods-and-drinks/tastes-and-textures.html",
    "https://www.cdc.gov/infant-toddler-nutrition/foods-and-drinks/foods-and-drinks-to-encourage.html?utm_source=chatgpt.com",
    "https://www.nhs.uk/baby/weaning-and-feeding/what-to-feed-young-children/?utm_source=chatgpt.com",
    "https://www.moh.gov.sa/en/healthawareness/educationalcontent/babyhealth/pages/complementary-food-for-infants.aspx?utm_source=chatgpt.com",
    "https://caringforkids.cps.ca/handouts/healthy-living/feeding_your_baby_in_the_first_year?utm_source=chatgpt.com",
]

SCRAPE_PARAMS = {
    "formats": ["markdown", "html"],
    "only_main_content": True,
    "timeout": 30000,
}

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
MARKDOWN_SAVE_DIR = "../scraped_markdown"
PERSIST_DIRECTORY = "../firecrawl_rag_db"   
FORCE_RESCRAPE = False                     
EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
# ===================================================

def sanitize_filename(url: str) -> str:
    parsed = urlparse(url)
    filename = parsed.netloc + parsed.path
    filename = filename.strip("/").replace("/", "_").replace(":", "")
    return filename[:150] + ".md"

def markdown_exists(url: str) -> bool:
    return os.path.exists(os.path.join(MARKDOWN_SAVE_DIR, sanitize_filename(url)))

def save_markdown(url: str, markdown: str, metadata: dict):
    os.makedirs(MARKDOWN_SAVE_DIR, exist_ok=True)
    filename = sanitize_filename(url)
    filepath = os.path.join(MARKDOWN_SAVE_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {metadata.get('title', url)}\n\n")
        f.write(f"**Source:** {url}\n\n")
        f.write(markdown)
    meta_path = os.path.join(MARKDOWN_SAVE_DIR, filename.replace(".md", ".json"))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({**metadata, "url": url}, f, indent=2, ensure_ascii=False)
    return filepath

def scrape_pages(urls: list[str]):
    app = Firecrawl(api_key=FIRECRAWL_API_KEY)
    documents = []
    print(f"🚀 Starting scrape of {len(urls)} pages...\n")
    for url in tqdm(urls, desc="Scraping pages", unit="page"):
        if not FORCE_RESCRAPE and markdown_exists(url):
            tqdm.write(f"⏭️  Skipping (already scraped): {url}")
            filepath = os.path.join(MARKDOWN_SAVE_DIR, sanitize_filename(url))
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            try:
                result = app.scrape(url, **SCRAPE_PARAMS)
                content = result.markdown or result.html or ""
                if not content.strip():
                    tqdm.write(f"⚠️  Empty content for {url}")
                    continue
                metadata = {
                    "source": url,
                    "title": getattr(result, "title", ""),
                    "description": getattr(result, "description", ""),
                    "language": getattr(result, "language", "en"),
                }
                filepath = save_markdown(url, content, metadata)
                tqdm.write(f"💾 Saved: {filepath}")
            except Exception as e:
                tqdm.write(f"❌ Failed {url}: {e}")
                continue
        doc = Document(page_content=content, metadata={"source": url, "title": getattr(result, "title", "") if 'result' in locals() else ""})
        documents.append(doc)
    return documents

def build_vector_store(documents):
    persist_dir = os.path.abspath(PERSIST_DIRECTORY)
    print(f"🛠️  Creating vector store at: {persist_dir}...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    splits = text_splitter.split_documents(documents)
    embeddings = HuggingFaceEndpointEmbeddings(
        model=EMBEDDING_MODEL,
        huggingfacehub_api_token=HUGGINGFACEHUB_API_TOKEN,
    )
    vectorstore = Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
        persist_directory=persist_dir,
        collection_name="firecrawl_scrape_hf"
    )
    print("✅ New vector store created successfully!")
    return vectorstore

if __name__ == "__main__":
    if not FIRECRAWL_API_KEY or not HUGGINGFACEHUB_API_TOKEN:
        print("❌ Missing API keys in .env file!")
        exit(1)
    
    docs = scrape_pages(URLS)
    if docs:
        build_vector_store(docs)