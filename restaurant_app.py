"""Lean Vercel entrypoint. The full Chroma app remains available locally in api.py."""
import csv, json, os, re, time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parent
FILES = ("realistic_restaurant_reviews.csv", "yelp_restaurant_reviews.csv")
MODEL = "gemini-flash-latest"
DATA = None
METRICS = {"requests": 0, "errors": 0, "total_latency_ms": 0, "last_latency_ms": None}
WORDS = re.compile(r"[a-z0-9]+", re.I)
STOP = set("a an and are at be can could do does find food for from give good great i in is it me of on or please restaurant restaurants review reviews show some tell that the there to what which where who with would you".split())
RECOMMEND = re.compile(r"\b(recommend|where should i (?:eat|go)|where can i eat|where to eat|restaurants? near|suggest|which restaurants?|best restaurants?)\b", re.I)
EXAMPLES = re.compile(r"\b(show|give|list|quote|cite|display)\b.{0,40}\b(reviews?|examples?|quotes?)\b|\b(which|what) reviews?\b|\bactual reviews?\b", re.I)
ANALYTICS = re.compile(r"\b(average|avg|mean|distribution|count|number of|how many|rating counts?)\b", re.I)


def rows():
    global DATA
    if DATA is None:
        DATA = []
        for name in FILES:
            with (ROOT / name).open(newline="", encoding="utf-8-sig") as file:
                for row in csv.DictReader(file):
                    row["source_file"] = name
                    DATA.append(row)
    return DATA


def key():
    value = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    return value if value and not value.startswith("replace_with_") else None


def search(question, limit=12, businesses=False):
    terms = {w.casefold() for w in WORDS.findall(question) if w.casefold() not in STOP}
    found = []
    for row in rows():
        if businesses and not row.get("name"):
            continue
        text = " ".join(str(v) for k, v in row.items() if k != "source_file").casefold()
        score = sum(term in text for term in terms)
        if score:
            found.append((score, row))
    found.sort(key=lambda x: (x[0], float(x[1].get("stars_business") or 0)), reverse=True)
    result, seen = [], set()
    for _, row in found:
        identity = (row.get("name", "").casefold(), row.get("city", "").casefold(), row.get("state", "").casefold())
        if businesses and identity in seen:
            continue
        seen.add(identity)
        result.append(row)
        if len(result) >= limit:
            break
    return result


def analytics(question):
    ratings = []
    names = set()
    for row in rows():
        try:
            ratings.append(float(row.get("Rating") or row.get("stars_review")))
        except (TypeError, ValueError):
            pass
        if row.get("name", "").strip():
            names.add(row["name"].strip().casefold())
    counts = {}
    for rating in ratings:
        label = str(int(rating)) if rating.is_integer() else str(rating)
        counts[label] = counts.get(label, 0) + 1
    answer = f"The datasets contain {len(ratings)} rated reviews."
    if ratings:
        answer += f" Average rating: {sum(ratings) / len(ratings):.2f}/5. Rating counts: {counts}."
    if "restaurant" in question.casefold():
        answer = f"The Yelp data contains {len(names)} distinct restaurants. " + answer
    return answer


def source(row):
    review = row.get("Review") or row.get("text") or ""
    return {"content": review, "metadata": {"Rating": row.get("Rating") or row.get("stars_review"), "Title": row.get("Title") or row.get("name") or "Review", "Review": review, "Date": row.get("Date") or row.get("date")}}


def answer(question, items, recommend):
    if not items:
        return "I couldn’t find matching information in the included restaurant reviews."
    if not key():
        if recommend:
            return "Based on historical Yelp reviews:\n" + "\n".join(f"• {r.get('name')} — {r.get('city')}, {r.get('state')}; {r.get('categories')}; {r.get('stars_business')} stars from {r.get('review_count')} reviews." for r in items)
        return "Relevant review excerpts:\n" + "\n".join("• " + str(r.get("Review") or r.get("text") or "") for r in items[:3])
    evidence = []
    for r in items[:10]:
        if recommend:
            evidence.append(f"{r.get('name')}; {r.get('city')}, {r.get('state')}; {r.get('categories')}; rating {r.get('stars_business')}; reviews {r.get('review_count')}; {r.get('text', '')}")
        else:
            evidence.append(f"Rating {r.get('Rating') or r.get('stars_review')}: {r.get('Review') or r.get('text')}")
    prompt = "Answer using only this restaurant evidence; do not invent facts. Match the requested preferences. Say Yelp data is historical.\n" + "\n".join(evidence) + "\nQuestion: " + question
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(MODEL, safe='')}:generateContent?key={quote(key(), safe='')}"
    request = Request(url, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 500, "temperature": 0.2}}).encode(), headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=45) as response:
            payload = json.loads(response.read())
        return "".join(part.get("text", "") for part in payload["candidates"][0]["content"]["parts"])
    except (URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError):
        return "\n".join(str(r.get("text") or r.get("Review") or "") for r in items[:3])


class Chat(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    @field_validator("question", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

app = FastAPI(title="Restaurant Review Agent")

@app.get("/health")
def health():
    return {"status": "ok", "documents": len(rows()), "embedding_model": "keyword overlap (Vercel lightweight mode)", "chat_model": MODEL, "llm_configured": key() is not None, "review_submissions_enabled": False, "agent_tools": ["restaurant_search", "review_search", "review_analytics"]}

@app.get("/metrics")
def metrics():
    result = dict(METRICS)
    result["average_latency_ms"] = round(result["total_latency_ms"] / result["requests"], 1) if result["requests"] else 0
    return result

@app.post("/reviews")
def no_review_storage():
    raise HTTPException(501, "Review submission is disabled in this serverless demo because local storage is temporary.")

@app.post("/chat")
def chat(request: Chat):
    def stream():
        started = time.perf_counter()
        failed = False
        try:
            q = request.question
            recommend, examples = bool(RECOMMEND.search(q)), bool(EXAMPLES.search(q))
            if ANALYTICS.search(q):
                yield "data: " + json.dumps({"type": "route", "tool": "review_analytics", "label": "Calculating review statistics"}) + "\n\n"
                text = analytics(q)
            else:
                yield "data: " + json.dumps({"type": "route", "tool": "restaurant_search" if recommend else "review_search", "label": "Finding matching restaurants" if recommend else "Searching review evidence"}) + "\n\n"
                items = search(q, 7 if recommend or examples else 12, recommend)
                if recommend or examples:
                    yield "data: " + json.dumps({"type": "sources", "sources": [source(r) for r in items]}, ensure_ascii=False) + "\n\n"
                text = answer(q, items, recommend)
            yield "data: " + json.dumps({"type": "token", "text": text}, ensure_ascii=False) + "\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
        except Exception:
            failed = True
            yield "data: " + json.dumps({"type": "error", "message": "Could not search the reviews. Please try again."}) + "\n\n"
        finally:
            elapsed = round((time.perf_counter() - started) * 1000)
            METRICS["requests"] += 1
            METRICS["errors"] += int(failed)
            METRICS["total_latency_ms"] += elapsed
            METRICS["last_latency_ms"] = elapsed
    return StreamingResponse(stream(), media_type="text/event-stream")

app.mount("/", StaticFiles(directory=str(ROOT / "static"), html=True), name="static")
