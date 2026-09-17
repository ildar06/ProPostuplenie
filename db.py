# -*- coding: utf-8 -*-
"""Простое хранилище на SQLite: профиль пользователя и прогресс по roadmap."""

import json
import sqlite3
from contextlib import contextmanager

DB_PATH = "admission_bot.db"


def init_db():
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                profile TEXT,
                last_recs TEXT,
                roadmap TEXT
            )
            """
        )
        c.commit()


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def save_profile(user_id: int, profile: dict):
    with _conn() as c:
        c.execute(
            "INSERT INTO users (user_id, profile) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET profile=excluded.profile",
            (user_id, json.dumps(profile, ensure_ascii=False)),
        )
        c.commit()


def get_profile(user_id: int):
    with _conn() as c:
        row = c.execute("SELECT profile FROM users WHERE user_id=?", (user_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None


def save_recommendations(user_id: int, recs: list):
    with _conn() as c:
        c.execute("UPDATE users SET last_recs=? WHERE user_id=?",
                   (json.dumps(recs, ensure_ascii=False), user_id))
        c.commit()


def get_recommendations(user_id: int):
    with _conn() as c:
        row = c.execute("SELECT last_recs FROM users WHERE user_id=?", (user_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else []


def save_roadmap(user_id: int, steps: list):
    with _conn() as c:
        c.execute("UPDATE users SET roadmap=? WHERE user_id=?",
                   (json.dumps(steps, ensure_ascii=False), user_id))
        c.commit()


def get_roadmap(user_id: int):
    with _conn() as c:
        row = c.execute("SELECT roadmap FROM users WHERE user_id=?", (user_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else []


def mark_step_done(user_id: int, step_index: int, done: bool = True):
    steps = get_roadmap(user_id)
    if 0 <= step_index < len(steps):
        steps[step_index]["done"] = done
    save_roadmap(user_id, steps)
    return steps
