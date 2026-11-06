import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import date as DateValue

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

import config
from agent import requested_review_examples, stream_agent, wants_review_examples
from chat import build_chain, diverse_reviews, fallback_review_summary, sources_payload
from csv_data import append_submitted_review
from ingest import build_store

state = {}
logger = logging.getLogger(__name__)
metrics = {"requests": 0, "errors": 0, "total_latency_ms": 0, "last_latency_ms": None}
metrics_lock = threading.Lock()
data_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.UPLOAD_DIR.mkdir(exist_ok=True)
    vector_store = build_store()
    state["retriever"] = vector_store.as_retriever(search_kwargs={"k": config.TOP_K})
    state["chain"] = build_chain() if config.llm_configured() else None
    yield
    state.clear()


app = FastAPI(title="Pizza Review Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["null", "http://127.0.0.1:8000", "http://localhost:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question", mode="before")
    @classmethod
    def trim_question(cls, value):
        return value.strip() if isinstance(value, str) else value


class ReviewSubmission(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    rating: int = Field(ge=1, le=5)
    review: str = Field(min_length=5, max_length=2000)
    date: DateValue = Field(default_factory=DateValue.today)

    @field_validator("title", "review", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


def _sse(event):
    return f"data: {json.dumps(event, default=str)}\n\n"


@app.get("/health")
def health():
    retriever = state.get("retriever")
    count = retriever.vectorstore._collection.count() if retriever else 0
    return {
        "status": "ok" if retriever is not None and count else ("starting" if retriever is None else "degraded"),
        "documents": count,
        "embedding_model": config.EMBEDDING_MODEL,
        "chat_model": config.CHAT_MODEL,
        "llm_configured": config.llm_configured(),
        "agent_tools": ["restaurant_search", "review_search", "review_analytics"],
    }


@app.get("/metrics")
def get_metrics():
    with metrics_lock:
        snapshot = dict(metrics)
    snapshot["average_latency_ms"] = (
        round(snapshot["total_latency_ms"] / snapshot["requests"], 1)
        if snapshot["requests"] else 0
    )
    return snapshot


@app.post("/reviews", status_code=201)
def submit_review(review: ReviewSubmission):
    with data_lock:
        try:
            append_submitted_review({
                "Title": review.title,
                "Date": review.date.isoformat(),
                "Rating": review.rating,
                "Review": review.review,
            })
            vector_store = build_store()
            state["retriever"] = vector_store.as_retriever(search_kwargs={"k": config.TOP_K})
        except Exception as error:
            logger.exception("Review submission or index refresh failed")
            raise HTTPException(
                status_code=503,
                detail="The review was saved, but search could not refresh. Please try again shortly.",
            ) from error
    return {"status": "saved_and_indexed", "documents": vector_store._collection.count()}


@app.post("/chat")
def chat(request: ChatRequest):
    if not state.get("retriever"):
        raise HTTPException(status_code=503, detail="Agent is still starting.")

    def events():
        started = time.perf_counter()
        failed = False
        sources_sent = False
        try:
            for event in stream_agent(request.question, state["retriever"], state["chain"]):
                if event["type"] == "error":
                    failed = True
                if event["type"] == "sources":
                    sources_sent = True
                yield _sse(event)
        except Exception:
            logger.exception("Agent request failed")
            try:
                if not sources_sent:
                    if wants_review_examples(request.question):
                        docs = requested_review_examples(state["retriever"], request.question)
                        selected = diverse_reviews(docs, config.DISPLAY_REVIEW_COUNT)
                        yield _sse({"type": "sources", "sources": sources_payload(selected)})
                        yield _sse({"type": "token", "text": "Here are the requested review examples."})
                    else:
                        docs = state["retriever"].invoke(request.question)
                        docs = diverse_reviews(docs, config.SUMMARY_CONTEXT_COUNT)
                        yield _sse({"type": "token", "text": "Here’s a summary of the matching reviews: " + fallback_review_summary(request.question, docs)})
                elif not wants_review_examples(request.question):
                    yield _sse({"type": "token", "text": fallback_review_summary(request.question, state["retriever"].invoke(request.question))})
                yield _sse({"type": "done"})
            except Exception:
                failed = True
                logger.exception("Review evidence fallback failed")
                yield _sse({"type": "error", "message": "I couldn’t search the reviews. Please try again."})
        finally:
            elapsed = round((time.perf_counter() - started) * 1000)
            with metrics_lock:
                metrics["requests"] += 1
                metrics["errors"] += int(failed)
                metrics["total_latency_ms"] += elapsed
                metrics["last_latency_ms"] = elapsed

    return StreamingResponse(events(), media_type="text/event-stream")


app.mount("/", StaticFiles(directory=str(config.BASE_DIR / "static"), html=True), name="static")
