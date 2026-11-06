# Restaurant Review Agent

A small tool-using RAG agent over the included pizza sample and Yelp restaurant review dataset. It can find restaurants by cuisine, city, and review themes; return matching businesses with their location, category, business rating, and review count; answer review questions; and calculate rating statistics. Recommendations use historical records, not live availability or ratings. Users submit reviews through a structured form; the app stores records in its private managed CSV and refreshes the Chroma index. The CSV itself is never exposed in the user interface.

## Start the local demo (macOS)

In Terminal, copy and run this single line:

```sh
cd "/Users/jayashreem/Vishunu/dsu/s7/gen-ai/aat" && ./start_demo.command
```

It creates a Python virtual environment, installs requirements, starts the API, waits for the health check, and opens the app at http://127.0.0.1:8000. You can also double-click `start_demo.command` in Finder. Do not paste the contents of the `.command` file or the whole README into Terminal; paste only the one command above. Do not open `static/index.html` as the main app because that bypasses the API server.

The launcher uses Python 3.11 to avoid the PyTorch wheel error caused by the machine's newer default Python. The first launch installs the dependencies, downloads the local embedding model, and indexes the bundled sample CSV, so allow a few minutes. Review search and rating analytics work without an API key; without `GOOGLE_API_KEY`, review search displays the retrieved source rows directly. To enable Gemini-generated synthesis, put a Google AI Studio key in `.env` before launching.

## Demo workflow

1. Ask “Where should I go for great Indian food in Philadelphia?” to show preference-based restaurant search and business details.
2. Ask “What do customers say about the crust?” to show review retrieval.
3. Ask “What is the average rating?” to show analytics.
4. Submit a new review through the form. The app validates it, stores it in the managed CSV, and refreshes embeddings; then ask a question about the new review.
5. Show the health, document count, request count, errors, and latency panels.

## API

- `GET /health` — readiness and indexed document count
- `GET /metrics` — request, error, and latency counters
- `POST /reviews` — validate a form submission, append it to the managed review store, and refresh the index
- `POST /chat` — streamed agent answer

## Docker

Build with `docker build -t pizza-review-agent .`, then run:

`docker run --rm -p 8000:8000 --env-file .env -v pizza-agent-data:/app/chroma_db -v pizza-agent-uploads:/app/uploads pizza-review-agent`

## Maintainability and limits

The user interacts with a review form, never the underlying CSV. CSV persistence is isolated in `csv_data.py`; indexing stays in `ingest.py`; routing/tools live in `agent.py`; HTTP, streaming, and metrics live in `api.py`. Submitted reviews and generated indexes stay in backend storage and are ignored by Git. Yelp review dates span 2005–2018; answers cannot confirm current business status, hours, or ratings. The intent router is deliberately small and deterministic. This project does not retrain the LLM: changed rows refresh embeddings and retrieval only. For a multi-user hosted deployment, replace the local CSV files with a database/object store and add authentication before exposing edit endpoints publicly.
