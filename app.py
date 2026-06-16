__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_chroma import Chroma
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()

# ====================== CONFIG ======================
HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# على Azure: app في /home/site/wwwroot  والـ DB في /home/site/firecrawl_rag_db
# محلياً:   app في code/               والـ DB في ../firecrawl_rag_db
# PERSIST_DIRECTORY env var تتحكم فيها من Azure App Settings
PERSIST_DIRECTORY = os.getenv(
    "PERSIST_DIRECTORY",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
)

EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
LLM_MODEL = "llama-3.3-70b-versatile"
# ===================================================

vectorstore = None
chat_history = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    global vectorstore
    persist_dir = os.path.abspath(PERSIST_DIRECTORY)
    if not os.path.exists(persist_dir):
        print(f"❌ Error: Database not found at {persist_dir}.")
    else:
        print("🔄 Loading existing Chroma database...")
        embeddings = HuggingFaceEndpointEmbeddings(
            model=EMBEDDING_MODEL,
            huggingfacehub_api_token=HUGGINGFACEHUB_API_TOKEN,
        )
        vectorstore = Chroma(
            persist_directory=persist_dir,
            embedding_function=embeddings,
            collection_name="firecrawl_scrape_hf"
        )
        print("✅ Database loaded successfully and ready for conversational queries.")
    yield
    print("🛑 Shutting down...")

app = FastAPI(title="UNICEF Milestone RAG Assistant", lifespan=lifespan)

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    answer: str


@app.get("/health")
async def health_check():
    """
    استخدمها عشان تتأكد إن كل حاجة شغالة بدون ما تقرأ الـ logs:
    GET https://YOUR_APP.azurewebsites.net/health
    """
    import sqlite3 as _sqlite3

    persist_dir = os.path.abspath(PERSIST_DIRECTORY)
    db_file_exists = os.path.exists(os.path.join(persist_dir, "chroma.sqlite3"))

    status = {
        "app_status": "ok",
        "sqlite3_version": _sqlite3.sqlite_version,
        "persist_directory": persist_dir,
        "db_folder_exists": os.path.exists(persist_dir),
        "db_file_exists": db_file_exists,
        "vectorstore_loaded": vectorstore is not None,
        "huggingface_token_set": bool(HUGGINGFACEHUB_API_TOKEN),
        "groq_key_set": bool(GROQ_API_KEY),
    }

    # اختبار فعلي للـ retrieval لو الـ vectorstore متحمّل
    if vectorstore is not None:
        try:
            test_results = vectorstore.similarity_search("test", k=1)
            status["retrieval_test"] = "ok"
            status["documents_found"] = len(test_results) > 0
        except Exception as e:
            status["retrieval_test"] = f"failed: {str(e)}"

    return status


def get_conversational_rag_answer(question: str) -> str:
    global chat_history
    if vectorstore is None:
        return "❌ Error: The vector database is not loaded."

    llm = ChatGroq(
        model=LLM_MODEL,
        groq_api_key=GROQ_API_KEY,
        temperature=0.25,
    )

    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a warm, supportive, and evidence-based pediatric nutrition assistant helping parents understand infant and toddler feeding.

Your goal is to provide clear, natural, and reassuring guidance while staying strictly grounded in trusted health information from WHO, UNICEF, CDC, NHS, Saudi MOH, and Canadian Paediatric Society resources contained in the database.

CRITICAL RULES:

1. ONLY USE PROVIDED CONTEXT
* Answer using ONLY the provided Context Blocks.
* Do NOT invent medical, developmental, or feeding advice.
* Do NOT guess, assume, or hallucinate details.
* If information is incomplete, uncertain, or not found in the context, clearly say so.

2. HANDLE UNKNOWN QUESTIONS SAFELY
   If the answer is not available in the Context Blocks, respond naturally and politely, for example:
   "I'm sorry, I don't have that specific information in my baby nutrition database. For personalized medical guidance, it's best to check with your pediatrician."

3. PRIORITIZE EVIDENCE
* Prefer WHO and UNICEF guidance first.
* Then CDC, NHS, Canadian Paediatric Society, and Ministry of Health sources.
* If recommendations slightly differ, explain this briefly without sounding alarming.

4. BE CONVERSATIONAL
* Be warm, calm, and supportive.
* Write naturally like a helpful pediatric assistant.
* Avoid sounding robotic or overly clinical.

5. KEEP ANSWERS CONCISE
* Default to short and practical responses.
* Use bullet points for lists or feeding tips.

6. ASK FOR AGE WHEN IMPORTANT
   If the child's age is missing and age matters for answering safely, politely ask for the baby's age first.

7. NEVER GIVE DIAGNOSES
* Do not diagnose conditions.
* Do not provide emergency medical advice.
* Recommend a pediatrician when symptoms or health concerns are mentioned.

Context Blocks:
{context}"""),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}")
    ])

    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    rag_chain = (
        {
            "context": retriever | format_docs,
            "chat_history": lambda x: chat_history,
            "question": RunnablePassthrough()
        }
        | qa_prompt
        | llm
        | StrOutputParser()
    )

    response = rag_chain.invoke(question)

    chat_history.append(HumanMessage(content=question))
    chat_history.append(AIMessage(content=response))

    if len(chat_history) > 12:
        chat_history = chat_history[-12:]

    return response


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    try:
        answer = get_conversational_rag_answer(payload.message)
        return ChatResponse(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_class=HTMLResponse)
async def get_ui():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Child Milestone Assistant</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-50 font-sans h-screen flex flex-col">
        <header class="bg-white border-b border-slate-200 py-4 px-6 flex items-center justify-between shadow-sm">
            <div class="flex items-center space-x-3">
                <div class="w-10 h-10 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold text-lg shadow-inner">👶</div>
                <div>
                    <h1 class="text-lg font-bold text-slate-800">Milestone RAG Assistant</h1>
                    <p class="text-xs text-green-600 flex items-center">
                        <span class="w-2 h-2 rounded-full bg-green-500 inline-block mr-1"></span> Conversational Mode Active
                    </p>
                </div>
            </div>
        </header>
        <main class="flex-1 overflow-y-auto p-6 space-y-4 max-w-4xl w-full mx-auto" id="chat-container">
            <div class="flex items-start space-x-3">
                <div class="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-sm">🤖</div>
                <div class="bg-white border border-slate-200 text-slate-800 p-4 rounded-2xl rounded-tl-none shadow-sm max-w-xl">
                    Hi there! 👋 I'm here to help you navigate your child's developmental milestones based on verified UNICEF documentation.
                    <br><br>
                    How old is your little one, or what milestones are you curious about today?
                </div>
            </div>
        </main>
        <footer class="bg-white border-t border-slate-200 p-4 shadow-md">
            <div class="max-w-4xl mx-auto flex items-center space-x-3">
                <input type="text" id="user-input" placeholder="Say hello, ask a question, or follow up on the last answer..."
                       class="flex-1 border border-slate-300 rounded-full px-5 py-3 text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all bg-slate-50">
                <button id="send-btn" class="bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-full px-6 py-3 shadow transition-colors flex items-center justify-center">
                    Send
                </button>
            </div>
        </footer>
        <script>
            const chatContainer = document.getElementById('chat-container');
            const userInput = document.getElementById('user-input');
            const sendBtn = document.getElementById('send-btn');

            function appendMessage(sender, text, isBot = false) {
                const messageRow = document.createElement('div');
                messageRow.className = `flex items-start space-x-3 ${!isBot ? 'justify-end space-x-reverse' : ''}`;
                const avatar = document.createElement('div');
                avatar.className = `w-8 h-8 rounded-full flex items-center justify-center text-sm ${isBot ? 'bg-blue-100' : 'bg-slate-800 text-white font-bold'}`;
                avatar.innerText = isBot ? '🤖' : 'U';
                const bubble = document.createElement('div');
                bubble.className = `p-4 rounded-2xl max-w-xl shadow-sm whitespace-pre-wrap ${
                    isBot ? 'bg-white border border-slate-200 text-slate-800 rounded-tl-none' : 'bg-blue-600 text-white rounded-tr-none'
                }`;
                bubble.innerText = text;
                messageRow.appendChild(avatar);
                messageRow.appendChild(bubble);
                chatContainer.appendChild(messageRow);
                chatContainer.scrollTop = chatContainer.scrollHeight;
                return messageRow;
            }

            function appendTypingIndicator() {
                const indicatorRow = document.createElement('div');
                indicatorRow.className = 'flex items-start space-x-3';
                indicatorRow.id = 'typing-indicator';
                indicatorRow.innerHTML = `
                    <div class="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-sm">🤖</div>
                    <div class="bg-white border border-slate-200 p-4 rounded-2xl rounded-tl-none shadow-sm text-slate-400 italic text-sm flex items-center space-x-1">
                        <span>Typing</span>
                        <span class="animate-bounce inline-block">.</span>
                        <span class="animate-bounce inline-block">.</span>
                        <span class="animate-bounce inline-block">.</span>
                    </div>`;
                chatContainer.appendChild(indicatorRow);
                chatContainer.scrollTop = chatContainer.scrollHeight;
                return indicatorRow;
            }

            async function handleSendMessage() {
                const query = userInput.value.trim();
                if (!query) return;
                appendMessage('User', query, false);
                userInput.value = '';
                const indicator = appendTypingIndicator();
                try {
                    const response = await fetch('/api/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: query })
                    });
                    const data = await response.json();
                    indicator.remove();
                    if (response.ok) {
                        appendMessage('Bot', data.answer, true);
                    } else {
                        appendMessage('Bot', `❌ Error: ${data.detail || 'Failed to generate answer'}`, true);
                    }
                } catch (error) {
                    indicator.remove();
                    appendMessage('Bot', `❌ Error connecting to server: ${error.message}`, true);
                }
            }

            sendBtn.addEventListener('click', handleSendMessage);
            userInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleSendMessage(); });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)
