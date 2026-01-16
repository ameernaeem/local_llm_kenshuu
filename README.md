# llm_basic_kenshuu (Local LLM Training)

## What this provides
- Ollama (local inference)
- Open WebUI (chat UI)
- RAG server (FAISS) + optional proxy integration

## Quick start
1) Put your GGUF model into `./models/`
2) Put your FAISS store into `./vectordb/default/`:
   - `vectordb/default/index.faiss`
   - `vectordb/default/index.pkl`
3) Start:
```bash
docker compose up -d --build

