from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
import config
import re

TEMPLATE = """Answer using only these restaurant reviews. If the reviews do not support an answer, say so.
For restaurant recommendations, use the business name, city/state, food categories, business rating, and review count present in the evidence. Match the user's stated cuisine, budget, occasion, or other preferences when evidence supports it. Compare only restaurants present in the evidence, explain the match briefly, and mention that Yelp ratings/reviews are historical rather than live information.
For general questions, summarize shared themes in 2–4 sentences instead of listing reviews. Give review examples only when explicitly requested.
Reviews:
{reviews}
Question: {question}
Do not invent facts."""


def build_chain():
    model = ChatGoogleGenerativeAI(model=config.CHAT_MODEL)
    return ChatPromptTemplate.from_template(TEMPLATE) | model


def extract_text(content):
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if isinstance(block, dict))


def sources_payload(docs):
    return [{"content": doc.page_content, "metadata": doc.metadata} for doc in docs]


def fallback_restaurant_recommendations(docs):
    if not docs:
        return "I couldn’t find restaurants in the available reviews that match that request."
    rows = [
        f"• {doc.metadata.get('name', 'Restaurant')} — {doc.metadata.get('city', '')}, {doc.metadata.get('state', '')}; "
        f"{doc.metadata.get('categories', 'categories unavailable')}; "
        f"{doc.metadata.get('stars_business', 'rating unavailable')} stars from "
        f"{doc.metadata.get('review_count', 'an unknown number of')} Yelp reviews."
        for doc in docs
    ]
    return "Based on historical Yelp reviews, here are matching restaurants:\n" + "\n".join(rows)


def diverse_reviews(docs, limit):
    """Keep relevant matches while spreading results across files and ratings."""
    groups = {}
    for doc in docs:
        source = str(doc.metadata.get("source_file", "unknown"))
        rating = str(doc.metadata.get("Rating", "unknown"))
        groups.setdefault(source, {}).setdefault(rating, []).append(doc)
    selected = []
    submitted_count = 0
    seen_businesses = set()
    while len(selected) < limit and groups:
        for source in list(groups):
            if source == "submitted_reviews.csv" and submitted_count >= 2:
                del groups[source]
                continue
            ratings = groups[source]
            rating = next(iter(ratings))
            doc = ratings[rating].pop(0)
            business = doc.metadata.get("name")
            business_key = (
                source,
                str(business).casefold(),
                str(doc.metadata.get("city", "")).casefold(),
                str(doc.metadata.get("state", "")).casefold(),
            ) if business else None
            if business_key and business_key in seen_businesses:
                if not ratings[rating]:
                    del ratings[rating]
                if not ratings:
                    del groups[source]
                continue
            if business_key:
                seen_businesses.add(business_key)
            selected.append(doc)
            submitted_count += source == "submitted_reviews.csv"
            if not ratings[rating]:
                del ratings[rating]
            else:
                ratings[rating] = ratings.pop(rating)
            if not ratings:
                del groups[source]
            if len(selected) == limit:
                break
    return selected


REVIEW_TOPICS = {
    "crust and texture": ("crust", "dough", "crispy", "chewy", "texture"),
    "toppings and ingredients": ("topping", "ingredient", "cheese", "pepperoni", "vegetable"),
    "flavor and seasoning": ("flavor", "taste", "seasoning", "herb", "spicy"),
    "sauce": ("sauce", "tomato", "marinara"),
    "service and waiting time": ("service", "staff", "wait", "server", "delivery"),
    "price and value": ("price", "value", "expensive", "cheap", "cost"),
    "freshness": ("fresh", "freshness", "stale"),
    "portion size": ("portion", "size", "large", "small", "slice"),
}


def fallback_review_summary(question, docs):
    """Produce a short, review-grounded digest from retrieved feedback."""
    if not docs:
        return "I couldn’t find reviews that support an answer to that question."
    question = question.lower()
    positive_ask = any(word in question for word in ("like", "praise", "best", "favorite", "favourite"))
    negative_ask = any(word in question for word in ("complaint", "dislike", "problem", "worst", "critic"))
    def rating(doc):
        try:
            return float(doc.metadata.get("Rating", 0) or 0)
        except (TypeError, ValueError):
            return 0

    positive = [doc for doc in docs if rating(doc) >= 4]
    negative = [doc for doc in docs if rating(doc) <= 2]

    def top_topics(rows):
        text = " ".join(str(doc.metadata.get("Review", doc.page_content)).lower() for doc in rows)
        counts = [(label, sum(text.count(term) for term in terms)) for label, terms in REVIEW_TOPICS.items()]
        return [label for label, count in sorted(counts, key=lambda item: item[1], reverse=True) if count][:2]

    if positive_ask:
        topics = top_topics(positive or docs)
        return f"Positive reviews most often praise {', '.join(topics)}. This summary is based on {len(positive or docs)} relevant reviews."
    if negative_ask:
        topics = top_topics(negative or docs)
        return f"Critical reviews most often mention {', '.join(topics)}. This summary is based on {len(negative or docs)} relevant reviews."
    positive_topics, negative_topics = top_topics(positive), top_topics(negative)
    parts = []
    if positive_topics:
        parts.append(f"Positive reviews often praise {', '.join(positive_topics)}")
    if negative_topics:
        parts.append(f"Lower-rated reviews more often criticize {', '.join(negative_topics)}")
    if not parts:
        parts.append(f"I found {len(docs)} relevant reviews, with mixed feedback across the set")
    return ". ".join(parts) + f". Based on {len(docs)} relevant reviews."


def answer(question, retriever, chain):
    docs = diverse_reviews(retriever.invoke(question), config.SUMMARY_CONTEXT_COUNT)
    if not docs:
        return {"answer": "I couldn’t find reviews that support an answer to that question.", "sources": []}
    response = chain.invoke({
        "reviews": "\n\n".join(doc.page_content for doc in docs),
        "question": question,
    })
    return {"answer": extract_text(response.content), "sources": sources_payload(docs)}


def stream_answer(question, retriever, chain, show_examples=False, docs=None):
    docs = docs if docs is not None else retriever.invoke(question)
    context = diverse_reviews(docs, config.SUMMARY_CONTEXT_COUNT)
    recommendation = bool(re.search(
        r"\b(recommend(?:ation)?|where should i (?:eat|go)|where can i eat|where to eat|find me .*restaurants?|restaurants? near|suggest .*restaurants?|which restaurants?|best restaurants?)\b",
        question, re.I,
    ))
    yield {"type": "route", "tool": "restaurant_search" if recommendation else "review_search", "label": "Finding matching restaurants" if recommendation else ("Searching review examples" if show_examples else "Summarizing review feedback")}
    if show_examples or recommendation:
        yield {"type": "sources", "sources": sources_payload(diverse_reviews(docs, config.DISPLAY_REVIEW_COUNT))}
    try:
        for chunk in chain.stream({
            "reviews": "\n\n".join(doc.page_content for doc in context),
            "question": question,
        }):
            text = extract_text(chunk.content)
            if text:
                yield {"type": "token", "text": text}
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Gemini streaming failed; using review-grounded fallback")
        if recommendation:
            yield {"type": "token", "text": fallback_restaurant_recommendations(diverse_reviews(docs, config.DISPLAY_REVIEW_COUNT))}
        else:
            yield {"type": "token", "text": "Here’s a summary of the matching reviews: " + fallback_review_summary(question, context) if not show_examples else "Here are the requested review examples."}
    yield {"type": "done"}
