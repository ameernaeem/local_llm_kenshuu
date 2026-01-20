import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
RAG_URL = os.getenv("RAG_URL", "http://rag:8000")
TOP_K = int(os.getenv("RAG_TOP_K", "5"))

app = FastAPI()


def _strip_hop_by_hop_headers(headers: dict) -> dict:
    drop = {
        "host",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-length",
        "content-encoding",
    }
    return {k: v for k, v in headers.items() if k.lower() not in drop}


async def _rag_context(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return ""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{RAG_URL}/search", json={"query": q, "top_k": TOP_K})
            r.raise_for_status()
            data = r.json()

        chunks = []
        for it in data.get("results", []):
            t = (it.get("text") or "").strip()
            if t:
                chunks.append(t)

        if not chunks:
            return ""
        return "Retrieved context:\n" + "\n\n".join(chunks[:TOP_K])
    except Exception:
        return ""


async def _proxy_buffered(method: str, url: str, headers: dict, json_payload=None, raw_body: bytes = b""):
    async with httpx.AsyncClient(timeout=180.0) as client:
        if json_payload is not None:
            r = await client.request(method, url, json=json_payload, headers=headers)
        else:
            r = await client.request(method, url, content=raw_body, headers=headers)

    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
    )


def _proxy_streaming(method: str, url: str, headers: dict, json_payload=None, raw_body: bytes = b""):
    async def gen():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                if json_payload is not None:
                    async with client.stream(method, url, json=json_payload, headers=headers) as r:
                        async for chunk in r.aiter_bytes():
                            if chunk:
                                yield chunk
                else:
                    async with client.stream(method, url, content=raw_body, headers=headers) as r:
                        async for chunk in r.aiter_bytes():
                            if chunk:
                                yield chunk
        except (httpx.StreamClosed, httpx.ReadError, httpx.RemoteProtocolError):
            return
        except Exception:
            return

    return StreamingResponse(gen(), media_type="application/json")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    method = request.method
    url = f"{OLLAMA_URL}/{path}"

    headers_in = dict(request.headers)
    headers = _strip_hop_by_hop_headers(headers_in)

    content_type = headers_in.get("content-type", "")
    raw_body = await request.body()

    if method != "POST" or ("application/json" not in content_type) or (path not in ("api/chat", "api/generate")):
        return await _proxy_buffered(method, url, headers=headers, json_payload=None, raw_body=raw_body)

    try:
        payload = await request.json()
    except Exception:
        return Response("Invalid JSON", status_code=400)

    is_stream = bool(payload.get("stream", False))

    if path == "api/chat":
        msgs = payload.get("messages") or []
        user_text = ""
        for m in reversed(msgs):
            if m.get("role") == "user":
                user_text = m.get("content", "") or ""
                break

        ctx = await _rag_context(user_text)
        if ctx:
            msgs.insert(0, {"role": "system", "content": ctx})
            payload["messages"] = msgs

    else:
        prompt = payload.get("prompt", "") or ""
        ctx = await _rag_context(prompt)
        if ctx:
            payload["prompt"] = ctx + "\n\n" + prompt

    if not is_stream:
        return await _proxy_buffered(method, url, headers=headers, json_payload=payload)

    return _proxy_streaming(method, url, headers=headers, json_payload=payload)

