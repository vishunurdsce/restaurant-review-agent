from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
import pandas as pd
import hashlib
import json

import config


def _hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _csv_files():
    config.UPLOAD_DIR.mkdir(exist_ok=True)
    return sorted([*config.BASE_DIR.glob("*.csv"), *config.UPLOAD_DIR.glob("*.csv")])


def _load_documents(csv_files):
    documents, ids = [], []
    for path in csv_files:
        frame = pd.read_csv(path)
        for row_number, row in frame.iterrows():
            content = "\n".join(f"{column}: {value}" for column, value in row.items())
            metadata = {"source_file": path.name}
            for column, value in row.items():
                if pd.notna(value):
                    value = value.item() if hasattr(value, "item") else value
                    metadata[column] = value
            doc_id = f"{path.name}:{row_number}"
            documents.append(Document(page_content=content, metadata=metadata, id=doc_id))
            ids.append(doc_id)
    return documents, ids


def build_store(force=False):
    csv_files = _csv_files()
    if not csv_files:
        raise FileNotFoundError("No CSV files found.")
    manifest = {
        "embedding_model": config.EMBEDDING_MODEL,
        "files": {path.name: _hash_file(path) for path in csv_files},
    }
    stored = None
    if config.MANIFEST_PATH.exists():
        try:
            stored = json.loads(config.MANIFEST_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            stored = None
    embeddings = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)
    store = Chroma(
        collection_name=config.COLLECTION_NAME,
        persist_directory=str(config.DB_DIR),
        embedding_function=embeddings,
    )
    if force or stored is None:
        # A missing or unreadable manifest gives us no safe way to identify
        # stale rows, so clear this collection once and rebuild it.
        existing_ids = store.get().get("ids", [])
        if existing_ids:
            store.delete(ids=existing_ids)
        changed_files = {path.name for path in csv_files}
        removed_files = set()
    else:
        existing_ids = set(store.get().get("ids", []))
        changed_files = {
            path.name for path in csv_files
            if stored.get("files", {}).get(path.name) != manifest["files"][path.name]
        }
        for path in csv_files:
            if path.name not in changed_files:
                expected_ids = {f"{path.name}:{row}" for row in range(len(pd.read_csv(path)))}
                if not expected_ids.issubset(existing_ids):
                    changed_files.add(path.name)
        removed_files = set(stored.get("files", {})) - set(manifest["files"])

    for filename in changed_files | removed_files:
        store.delete(where={"source_file": filename})
    for path in csv_files:
        if path.name in changed_files:
            docs, ids = _load_documents([path])
            batch_size = store._client.get_max_batch_size()
            for start in range(0, len(docs), batch_size):
                store.add_documents(
                    documents=docs[start:start + batch_size],
                    ids=ids[start:start + batch_size],
                )
    if changed_files or removed_files or force or stored is None:
        config.MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    return store


if __name__ == "__main__":
    store = build_store(force=True)
    print(f"Indexed {store._collection.count()} review rows")
