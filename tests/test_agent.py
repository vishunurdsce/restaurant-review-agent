import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.documents import Document

import agent
import config
from chat import fallback_restaurant_recommendations


class FakeRetriever:
    def __init__(self, docs):
        self.docs = docs

    def invoke(self, question):
        return self.docs


def restaurant(name, city, categories, rating=4.0, reviews=50, text="Good food"):
    return Document(
        page_content=f"name: {name}\ncity: {city}\ncategories: {categories}\nReview: {text}",
        metadata={
            "source_file": "yelp_restaurant_reviews.csv",
            "name": name,
            "city": city,
            "state": "PA",
            "categories": categories,
            "stars_business": rating,
            "review_count": reviews,
            "stars_review": 5,
            "Review": text,
        },
    )


class AgentQuestionTests(unittest.TestCase):
    def setUp(self):
        self.docs = [
            restaurant("Zaika", "Philadelphia", "Indian, Restaurants", text="Excellent lamb curry and naan"),
            restaurant("Rasavat", "Philadelphia", "Indian, Restaurants", rating=5, text="Fresh regional Indian food"),
            restaurant("Sushi Place", "Philadelphia", "Japanese, Sushi Bars", text="Great sushi"),
            restaurant("Tandoor", "Newtown", "Indian, Restaurants", text="Good curry"),
        ]

    def test_preference_question_returns_distinct_businesses_in_requested_city(self):
        question = "Where should I go for Indian food in Philadelphia?"
        self.assertTrue(agent.wants_restaurant_recommendations(question))
        events = list(agent.stream_agent(question, FakeRetriever(self.docs), None))
        self.assertEqual(next(e["tool"] for e in events if e["type"] == "route"), "restaurant_search")
        sources = next(e["sources"] for e in events if e["type"] == "sources")
        self.assertEqual({s["metadata"]["city"] for s in sources}, {"Philadelphia"})
        self.assertEqual(len({s["metadata"]["name"] for s in sources}), len(sources))
        answer = next(e["text"] for e in events if e["type"] == "token")
        self.assertIn("Zaika", answer)
        self.assertIn("Indian", answer)

    def test_theme_question_summarizes_retrieved_reviews(self):
        events = list(agent.stream_agent("What do people like about the crust?", FakeRetriever(self.docs), None))
        self.assertEqual(next(e["tool"] for e in events if e["type"] == "route"), "review_search")
        self.assertTrue(any(e["type"] == "token" for e in events))

    def test_rating_filter_variants(self):
        self.assertEqual(agent.review_rating_filter("Show me 5 star reviews"), [5])
        self.assertEqual(agent.review_rating_filter("Find good reviews"), [3, 4, 5])
        self.assertEqual(agent.review_rating_filter("Show bad reviews"), [1, 2])

    def test_count_and_rating_questions_route_to_deterministic_analytics(self):
        for question in ("What is the average rating?", "How many reviews are there?", "How many restaurants?"):
            self.assertTrue(agent.ANALYTICS_INTENT.search(question), question)

    def test_capabilities_question_describes_restaurant_discovery(self):
        events = list(agent.stream_agent("What can you do?", FakeRetriever(self.docs), None))
        self.assertEqual(next(e["tool"] for e in events if e["type"] == "route"), "help")
        self.assertIn("cuisine", next(e["text"] for e in events if e["type"] == "token"))

    def test_no_match_fallback_does_not_invent_restaurant(self):
        self.assertIn("couldn’t find", fallback_restaurant_recommendations([]))


class AnalyticsTests(unittest.TestCase):
    def test_combines_review_ratings_and_counts_distinct_businesses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "yelp.csv").write_text(
                "name,stars_review,stars_business\nCafe,5,4.5\nCafe,3,4.5\n", encoding="utf-8"
            )
            upload = root / "uploads"
            upload.mkdir()
            (upload / "submitted_reviews.csv").write_text(
                "Rating\n4\n", encoding="utf-8"
            )
            with patch.object(config, "BASE_DIR", root), patch.object(config, "UPLOAD_DIR", upload):
                result = agent.review_analytics()
        self.assertEqual(result["rows"], 3)
        self.assertEqual(result["restaurants"], 1)
        self.assertEqual(result["yelp_review_rows"], 2)
        self.assertEqual(result["average_rating"], 4.0)
        self.assertEqual(result["rating_counts"], {"3": 1, "4": 1, "5": 1})


if __name__ == "__main__":
    unittest.main()
