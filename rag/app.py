from pathlib import Path
from fastapi import FastAPI, HTTPException
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
import torch

app = FastAPI(title="RAG Vector Search")

BASE = Path("/vectordb")
stores = {}

@app.on_event("startup")
def load_all() -> None:
    if not BASE.exists():
        print("[RAG] vectordb path not found:", BASE)
        return

    embed = HuggingFaceEmbeddings(
        model_name="intfloat/multilingual-e5-base",
        model_kwargs={"device": "cuda" if torch.cuda.is_available() else "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    for d in BASE.iterdir():
        if not d.is_dir():
            continue
        if (d / "index.faiss").exists():
            try:
                stores[d.name] = FAISS.load_local(
                    str(d),
                    embed,
                    allow_dangerous_deserialization=True
                )
                print(f"[RAG] loaded {d.name}")
            except Exception as e:
                print(f"[RAG] failed loading {d.name}: {e}")
        else:
            print(f"[RAG] skip {d.name} (index.faiss missing)")

@app.get("/health")
def health():
    return {"ok": True, "domains": list(stores.keys())}

@app.post("/search")
def search(req: dict):
    q = (req.get("query") or "").strip()
    domain = (req.get("domain") or "default").strip()
    top_k = int(req.get("top_k") or 5)

    store = stores.get(domain)
    if store is None:
        raise HTTPException(404, f"domain '{domain}' not found. available={list(stores.keys())}")

    docs = store.similarity_search(q, k=top_k)

    return {
        "domain": domain,
        "query": q,
        "results": [{"text": d.page_content, "meta": d.metadata} for d in docs],
    }

