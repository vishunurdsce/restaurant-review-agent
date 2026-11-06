"""Backend-only persistence for submitted review records."""
import csv
import os
import tempfile

import config


class CSVDataError(ValueError):
    pass


def _write_rows(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as target:
            writer = csv.DictWriter(target, fieldnames=columns, extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _validate_review(review):
    columns = ["Title", "Date", "Rating", "Review"]
    if not isinstance(review, dict) or set(review) != set(columns):
        raise CSVDataError("Review is missing a required field.")
    return {column: "" if review[column] is None else str(review[column]) for column in columns}


def append_submitted_review(review):
    """Append a structured form submission to the app-managed review CSV."""
    path = config.SUBMITTED_REVIEWS_PATH
    columns = ["Title", "Date", "Rating", "Review"]
    rows = []
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != columns:
                raise CSVDataError("The managed review store has an unexpected schema.")
            rows = list(reader)
    rows.append(_validate_review(review))
    _write_rows(path, rows, columns)
    return len(rows)
