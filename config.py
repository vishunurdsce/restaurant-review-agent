from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
SUBMITTED_REVIEWS_PATH = UPLOAD_DIR / "submitted_reviews.csv"
DB_DIR = BASE_DIR / "chroma_db"
MANIFEST_PATH = DB_DIR / "source_manifest.json"
COLLECTION_NAME = "csv_documents"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
CHAT_MODEL = "gemini-flash-latest"
TOP_K = 60
DISPLAY_REVIEW_COUNT = 7
SUMMARY_CONTEXT_COUNT = 24


def llm_configured():
    return any(
        value and not value.startswith("replace_with_")
        for value in (os.getenv("GOOGLE_API_KEY"), os.getenv("GEMINI_API_KEY"))
    )
