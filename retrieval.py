import config
from ingest import build_store


def get_retriever(k=None):
    return build_store().as_retriever(search_kwargs={"k": k or config.TOP_K})
