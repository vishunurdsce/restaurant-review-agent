# Restaurant Review Agent — Viva Prep

## 30-second project introduction

“I built a restaurant discovery and review assistant over 14,351 Yelp review rows covering 2,526 businesses, alongside a small pizza review sample. Users can ask for restaurants by cuisine, location, or preferences, inspect evidence from reviews, request examples by rating, and check rating analytics. New reviews are submitted through a validated form; the CSV stays on the backend and the search index refreshes after submission.”

## Problem and users

- **Problem:** Manually scanning many customer reviews makes it hard to spot recurring praise and complaints or answer questions quickly.
- **Users:** Restaurant staff, managers, or analysts reviewing customer feedback.
- **Business value:** Faster feedback search, a quick view of rating trends, and an easy way to add new feedback.

## What the demo does

1. **Restaurant discovery and review Q&A:** Embeds the Yelp and pizza CSV rows with BAAI/bge-small-en-v1.5, stores/retrieves them through Chroma, and uses Gemini Flash to answer from relevant evidence. Recommendations include business names, locations, categories, business ratings, and review counts. The no-key fallback displays retrieved business evidence directly.
2. **Rating filters:** “Good reviews” means ratings 3–5; “bad reviews” means 1–2. An exact request such as “show me 5 star reviews” filters to that rating and shows up to 7 rows.
3. **Rating analytics:** Questions about average rating, rating distribution, or review count use a deterministic analytics route calculated from the CSVs with pandas.
4. **Review submission:** A form validates title, rating, date, and review text. The backend appends the record to its managed CSV and refreshes the changed index data.
5. **Health and metrics:** `/health` reports readiness and indexed-document count. `/metrics` reports request count, errors, and latency.

## Architecture at a glance

```text
Browser form/chat
      │ HTTP + streamed responses
      ▼
FastAPI (api.py)
      ├── review question ──► embeddings ──► Chroma retrieval ──► Gemini summary
      ├── rating question ──► pandas analytics over CSV data
      └── submitted review ─► validation ─► private CSV ─► index refresh

Health and request metrics are exposed by FastAPI endpoints.
```

## Likely viva questions and concise answers

**What makes this an agentic workflow?**  
“It accepts a natural-language task and routes it to the appropriate capability: semantic review search and answer generation, or a rating analytics operation. The result is streamed back, with review evidence available when requested.”

**Is it a multi-agent system?**  
“No. This version is one assistant with restaurant search, review search, and deterministic analytics routes. Multi-agent coordination was optional in the guidance; I chose a smaller workflow that solves the review-analysis problem.”

**Why use RAG?**  
“The model needs to answer from this specific, changing review dataset. Retrieval brings relevant rows into the prompt, so answers can be grounded in the current data instead of relying only on the model’s general training.”

**What does the embedding model do?**  
“It converts review text and the user’s question into vectors so Chroma can retrieve semantically related reviews, even when the wording differs.”

**Why use a separate analytics route?**  
“Average ratings and rating counts are exact calculations. Pandas gives a direct, reproducible result instead of asking a language model to do arithmetic.”

**Can users edit the CSV?**  
“No. They use the review form. CSV persistence and indexing stay on the backend; the UI never exposes the CSV file.”

**How does a new review become searchable?**  
“The API validates the form data, appends it to the managed review CSV, updates the changed file’s vectors, and replaces the app’s retriever with the refreshed store.”

**What happens if Gemini is unavailable?**  
“The app still uses retrieved reviews to produce a brief local summary, or displays the requested review examples. It should not present an AI-provider failure message as the answer.”

**What are the Yelp data limits?**  
"These records are historical, dated 2005–2018. They support review-based discovery but cannot confirm current business status, hours, availability, or ratings."

**How do you monitor the app?**  
“`/health` exposes readiness and the indexed count. `/metrics` exposes request/error counts and average and last latency. Those are basic operational signals for this demo.”

**Is it deployed to the cloud?**  
“No. The current demo runs locally and has Docker instructions. A hosted production deployment and its monitoring setup are future work.”

**What are the limitations?**  
“It answers from the included review datasets, not arbitrary outside facts. Yelp records are historical, so they are not live business information. The local CSV and vector store are appropriate for a small demo; a hosted multi-user version should use a database, authentication, and production monitoring.”

**What would you improve next?**  
“Deploy it with persistent managed storage, authentication, and alerts; add evaluation questions to check answer grounding and retrieval quality; and consider multi-agent coordination only if the workflow grows enough to justify it.”

## Honest scope to state

- This is a working **single-agent, tool-routed** demo; do not call it a multi-agent system.
- Health and metrics are implemented, but this project is **not currently deployed as a hosted production service**.
- The assistant is scoped to the review dataset. It should say when the reviews do not support an answer.
- The source CSV is backend data; users submit reviews through the UI rather than editing the CSV.
