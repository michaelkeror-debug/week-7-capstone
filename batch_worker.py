"""Lever 2: batch queue for non-urgent summarisation jobs.

Jobs (e.g. theme summaries of feedback) go into a SQLite queue and are sent
to the model BATCH_SIZE at a time in ONE call, so the system prompt is paid
once per batch instead of once per job. Patient triage itself is never
batched: it is latency-sensitive and safety-critical.

Set USE_LLM=1 (plus LLM_API_KEY, optional LLM_BASE_URL/LLM_MODEL) to call a
real model; otherwise a stub returns one summary per job.
"""
import json
import os
import sqlite3
from pathlib import Path

DB = Path(os.getenv("JOBS_DB", "jobs.sqlite"))
BATCH_SIZE = 8
USE_LLM = os.getenv("USE_LLM") == "1"
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS jobs ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "text TEXT NOT NULL,"
    "status TEXT NOT NULL DEFAULT 'pending',"
    "result TEXT)"
)

metrics = {"model_calls": 0, "jobs_done": 0, "jobs_failed": 0}


def init(db=DB):
    conn = sqlite3.connect(db)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def enqueue(conn, text: str):
    conn.execute("INSERT INTO jobs(text) VALUES (?)", (text,))
    conn.commit()


def fetch_batch(conn, n=BATCH_SIZE):
    return conn.execute(
        "SELECT id, text FROM jobs WHERE status='pending' ORDER BY id LIMIT ?",
        (n,)).fetchall()


def summarise_batch(texts: list) -> list:
    """One model call for the whole batch; returns one summary per text."""
    metrics["model_calls"] += 1
    if not USE_LLM:
        return [f"Theme stub ({len(t.split())} words)" for t in texts]

    from openai import OpenAI
    client = OpenAI(base_url=os.getenv("LLM_BASE_URL") or None,
                    api_key=os.getenv("LLM_API_KEY"))
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content":
                "Summarise the theme of each numbered item in one short line. "
                'Reply only with JSON: {"summaries": ["...", ...]} in the '
                "same order, one entry per item."},
            {"role": "user", "content": numbered},
        ],
    )
    try:
        return json.loads(resp.choices[0].message.content)["summaries"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def process_once(conn, batch_size=BATCH_SIZE):
    batch = fetch_batch(conn, batch_size)
    if not batch:
        return 0
    ids = [b[0] for b in batch]
    results = summarise_batch([b[1] for b in batch])

    # Quality guard: a batched call can drop or merge items. If the count
    # doesn't match, mark the whole batch failed rather than misalign results.
    if len(results) != len(ids):
        conn.executemany("UPDATE jobs SET status='failed' WHERE id=?",
                         [(i,) for i in ids])
        metrics["jobs_failed"] += len(ids)
    else:
        conn.executemany("UPDATE jobs SET status='done', result=? WHERE id=?",
                         list(zip(results, ids)))
        metrics["jobs_done"] += len(ids)
    conn.commit()
    return len(ids)


def process_all(conn, batch_size=BATCH_SIZE):
    total = 0
    while (n := process_once(conn, batch_size)):
        total += n
    return total


if __name__ == "__main__":
    c = init()
    for sample in ["fever hydration", "stock delay FAQ", "delivery window"]:
        enqueue(c, sample)
    print("processed", process_all(c), "model_calls", metrics["model_calls"])
