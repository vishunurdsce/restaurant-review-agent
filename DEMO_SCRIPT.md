# Restaurant Review Agent — Live Demo Script

## Before presenting

1. Open Terminal and run:

   ```sh
   cd "/Users/jayashreem/Vishunu/dsu/s7/gen-ai/aat" && ./start_demo.command
   ```

2. Keep the Terminal window open and wait for the browser to show **Assistant ready**.
3. Confirm the health card shows indexed reviews. After the Yelp index build, expect about 14,478 rows across the Yelp data and existing pizza sample; use the live count if it differs.
4. Keep the review form visible for the final step. Do not open or share the CSV file.

## 3–4 minute spoken walkthrough

### 1. Introduce the workflow

“Here’s a small agentic workflow for a restaurant feedback problem. The assistant can summarize customer feedback, show review examples by rating, calculate rating statistics, and accept new reviews through a form. The raw CSV stays in backend storage.”

### 2. Find restaurants for a preference

Ask:

> Where should I go for great Indian food in Philadelphia?

Say:

“The agent searches review evidence and returns distinct matching businesses with cuisine, location, business rating, and review count. The Yelp dataset is historical, so these are evidence-based suggestions rather than live listings.”

### 3. Ask for a review summary

Ask:

> What do customers say about the crust?

Say:

“The question is handled as a review-search and summary request. The app retrieves relevant feedback, then summarizes the themes so the user does not have to read every row. If I want the underlying examples, I can ask for them explicitly.”

Optional second summary prompt:

> What do people like most about the pizza?

### 4. Show examples and rating filtering

Ask these one at a time:

> Show me good reviews.

> Show me bad reviews.

> Show me 5 star reviews.

Say:

“Good reviews include ratings 3 through 5; bad reviews include ratings 1 and 2. An exact star request returns only that rating. The table is limited to a handful of examples and includes older reviews as well as a small number of submitted reviews.”

### 5. Show deterministic analytics

Ask:

> What is the average rating?

Say:

“This goes through the analytics route. Pandas calculates the average and distribution from the CSV data, so the answer is an exact computation rather than an LLM estimate.”

### 6. Submit one review

Use the form with a simple demo entry, for example:

- **Title:** Demo review — crisp base
- **Rating:** 4
- **Review:** “The base was crisp, the toppings tasted fresh, and the portions were generous.”
- **Date:** Leave the default date.

Click **Submit review** and wait for the saved message and health count to update. Then ask:

> What do customers say about fresh toppings?

Say:

“The review is validated, saved in the private managed store, and added to search without exposing the CSV in the UI.”

### 7. Close with monitoring and scope

Point to the health and metrics cards:

“The health panel shows readiness and indexed review count. The metrics panel shows agent requests, latency, and errors. This is a local demo with basic monitoring signals; it is not a hosted production deployment.”

## Backup questions

- “Summarize the main praise and complaints.”
- “What do reviews mention about sauce?”
- “Show me 3 star reviews.”
- “How many reviews are indexed?”
- “What can you do?”

## If something goes wrong

- If the badge is not **Assistant ready**, wait for initial indexing to finish and check the Terminal output.
- If new backend changes were made since the app was launched, restart the existing launcher once so Python reloads them, then refresh the page.
- If Gemini cannot generate a response, use the review-evidence fallback and continue with rating analytics; do not claim the provider generated the fallback summary.
- If the browser is closed, open `http://127.0.0.1:8000` while the launcher is still running.
