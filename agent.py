"""Small, inspectable agent router with retrieval and review analytics tools."""
import re
import time

import pandas as pd
from langchain_core.documents import Document
import config
from chat import answer, diverse_reviews, fallback_restaurant_recommendations, fallback_review_summary, sources_payload, stream_answer

ANALYTICS_INTENT = re.compile(
    r"\b(average rating|avg rating|mean rating|overall rating|rating distribution|"
    r"rating counts|most common rating|total number of reviews|review count|"
    r"how many restaurants|number of restaurants|restaurant count)\b|"
    r"^\s*(how many|count|number of) reviews(?: are indexed| are there| in total)?\s*[?.!]*$",
    re.IGNORECASE,
)
CAPABILITIES_INTENT = re.compile(
    r"\b(what can you do|what can u do|how can you help|what are you able to do)\b",
    re.IGNORECASE,
)
EXAMPLE_INTENT = re.compile(
    r"\b(show|give|list|find|quote|cite|display)\b.{0,40}\b(reviews?|examples?|quotes?|sources?)\b|"
    r"\b(which|what) reviews?\b|\bactual reviews?\b|"
    r"\b(good|bad|positive|negative|[1-5](?:\s*-\s*|\s*)?star) reviews?\b",
    re.IGNORECASE,
)
RECOMMENDATION_INTENT = re.compile(
    r"\b(recommend(?:ation)?|where should i (?:eat|go)|where can i eat|where to eat|"
    r"find me .*restaurants?|restaurants? near|suggest .*restaurants?|which restaurants?|best restaurants?)\b",
    re.IGNORECASE,
)


def wants_review_examples(question):
    return bool(EXAMPLE_INTENT.search(question))


def wants_restaurant_recommendations(question):
    return bool(RECOMMENDATION_INTENT.search(question))


def filter_to_mentioned_city(docs, question):
    matches = {
        str(doc.metadata.get("city", "")).strip().casefold()
        for doc in docs
        if doc.metadata.get("city")
        and re.search(rf"\b{re.escape(str(doc.metadata['city']).strip())}\b", question, re.IGNORECASE)
    }
    return [doc for doc in docs if str(doc.metadata.get("city", "")).strip().casefold() in matches] if matches else docs


def review_rating_filter(question):
    explicit = re.search(r"\b([1-5])\s*(?:-\s*)?star\b|\b([1-5])★|\brating\s*(?:of\s*)?([1-5])\b", question, re.I)
    if explicit:
        return [int(value) for value in explicit.groups() if value]
    if re.search(r"\b(good|positive) reviews?\b", question, re.I):
        return [3, 4, 5] if re.search(r"\bgood\b", question, re.I) else [4, 5]
    if re.search(r"\b(bad|negative) reviews?\b", question, re.I):
        return [1, 2]
    return None


def requested_review_examples(retriever, question):
    ratings = review_rating_filter(question)
    if not ratings:
        return retriever.invoke(question)
    store = retriever.vectorstore
    docs = []
    for rating in ratings:
        rows = store.get(where={"Rating": rating}, include=["documents", "metadatas"])
        docs.extend(
            Document(page_content=content, metadata=metadata or {}, id=doc_id)
            for doc_id, content, metadata in zip(rows["ids"], rows["documents"], rows["metadatas"])
            if content is not None
        )
    return docs


def review_analytics():
    # Keep analytics aligned with every CSV source the retrieval pipeline indexes.
    frames = [pd.read_csv(path) for path in
              [*config.BASE_DIR.glob("*.csv"), *config.UPLOAD_DIR.glob("*.csv")]
              if path.exists()]
    if not frames:
        return {"rows": 0, "restaurants": 0, "average_rating": None, "rating_counts": {}}
    frame = pd.concat(frames, ignore_index=True)
    rating_columns = [c for c in ("Rating", "stars_review") if c in frame.columns]
    ratings = pd.concat(
        [pd.to_numeric(frame[column], errors="coerce") for column in rating_columns],
        ignore_index=True,
    ).dropna()
    yelp_review_count = (
        int(pd.to_numeric(frame["stars_review"], errors="coerce").notna().sum())
        if "stars_review" in frame.columns else 0
    )
    restaurant_count = 0
    if "name" in frame.columns:
        restaurant_count = int(frame.loc[frame["name"].notna(), "name"].nunique())
    return {
        "rows": int(len(ratings)),
        "restaurants": restaurant_count,
        "yelp_review_rows": yelp_review_count,
        "average_rating": round(float(ratings.mean()), 2) if not ratings.empty else None,
        "rating_counts": {str(int(k)): int(v) for k, v in ratings.value_counts().sort_index().items()},
    }


def _analytics_result(question=""):
    stats = review_analytics()
    avg = stats["average_rating"]
    if "restaurant" in question.lower():
        answer_text = (
            f"The Yelp dataset contains {stats['restaurants']} distinct restaurants across "
            f"{stats['yelp_review_rows']} rated review rows. The combined datasets contain "
            f"{stats['rows']} valid review ratings in total."
        )
    else:
        answer_text = f"The included datasets contain {stats['rows']} review rows with valid ratings."
    if avg is not None:
        answer_text += f" The average rating is {avg}/5. Rating counts: {stats['rating_counts']}."
    return {"answer": answer_text, "sources": [], "tool": "review_analytics"}


def run_agent(question, retriever, chain):
    started = time.perf_counter()
    if ANALYTICS_INTENT.search(question):
        result = _analytics_result(question)
        route = "review_analytics"
    else:
        result = answer(question, retriever, chain)
        route = "restaurant_search" if wants_restaurant_recommendations(question) else "review_search"
    result.update({"tool": route, "latency_ms": round((time.perf_counter() - started) * 1000)})
    return result


def stream_agent(question, retriever, chain):
    if CAPABILITIES_INTENT.search(question):
        yield {"type": "route", "tool": "help", "label": "Explaining assistant capabilities"}
        yield {"type": "token", "text": "I can find restaurants by cuisine, city, and review-based preferences; summarize customer feedback; show review examples; and calculate rating statistics. I answer from these datasets and can’t verify current business details or unrelated facts."}
        yield {"type": "done"}
        return
    if ANALYTICS_INTENT.search(question):
        started = time.perf_counter()
        result = _analytics_result(question)
        yield {"type": "route", "tool": result["tool"], "label": "Calculating review statistics"}
        yield {"type": "token", "text": result["answer"]}
        yield {"type": "metrics", "latency_ms": round((time.perf_counter() - started) * 1000)}
        yield {"type": "done"}
        return
    started = time.perf_counter()
    show_examples = wants_review_examples(question)
    recommend = wants_restaurant_recommendations(question)
    docs = requested_review_examples(retriever, question) if show_examples else retriever.invoke(question)
    if recommend:
        docs = filter_to_mentioned_city(docs, question)
    if chain is None:
        yield {"type": "route", "tool": "restaurant_search" if recommend else "review_search", "label": "Finding matching restaurants" if recommend else ("Searching review evidence" if show_examples else "Summarizing review feedback")}
        if show_examples or recommend:
            docs = diverse_reviews(docs, config.DISPLAY_REVIEW_COUNT)
            yield {"type": "sources", "sources": sources_payload(docs)}
            if recommend:
                text = fallback_restaurant_recommendations(docs)
            else:
                text = "Here are relevant review examples." if docs else "No matching review rows were found."
        else:
            docs = diverse_reviews(docs, config.SUMMARY_CONTEXT_COUNT)
            text = fallback_review_summary(question, docs)
        yield {"type": "token", "text": text}
        yield {"type": "metrics", "latency_ms": round((time.perf_counter() - started) * 1000)}
        yield {"type": "done"}
        return
    for event in stream_answer(question, retriever, chain, show_examples, docs):
        yield event
    yield {"type": "metrics", "latency_ms": round((time.perf_counter() - started) * 1000)}
