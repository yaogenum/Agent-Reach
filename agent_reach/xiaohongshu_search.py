# -*- coding: utf-8 -*-
"""Multi-path XiaoHongShu search helpers."""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
import typing as t

from agent_reach.channels.xiaohongshu import format_xhs_result
from agent_reach.utils.process import utf8_subprocess_env

_USER_ID_KEYS = (
    "user_id",
    "userId",
    "uid",
    "id",
    "sec_user_id",
)
_USER_URL_KEYS = (
    "user_url",
    "url",
    "profile_url",
    "home_page",
    "author_url",
)
_NOTE_ID_KEYS = (
    "id",
    "note_id",
    "noteId",
)
_NOTE_URL_KEYS = (
    "url",
    "note_url",
    "share_url",
)


def search_xiaohongshu(
    query: str,
    *,
    limit: int = 10,
    timeout: int = 30,
    include_username_lookup: bool = True,
    command: str = "opencli",
) -> list[dict]:
    """Run multi-path XiaoHongShu retrieval.

    Path A: ``opencli xiaohongshu search``
    Path B: ``opencli xiaohongshu user`` using the query itself.

    The result set is de-duplicated and merged with a ``sources`` field.
    """
    query = (query or "").strip()
    if not query or limit <= 0:
        return []

    paths = ["search"]
    if include_username_lookup and " " not in query:
        paths.append("user")

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(paths)) as executor:
        future_results = {}

        future_results[
            executor.submit(
                _run_xiaohongshu_json,
                ["search", query, "-f", "json"],
                timeout=timeout,
                command=command,
            )
        ] = "search"

        if "user" in paths:
            future_results[
                executor.submit(
                    _run_xiaohongshu_json,
                    ["user", query, "-f", "json"],
                    timeout=timeout,
                    command=command,
                )
            ] = "user"

        result_by_source: dict[str, list[dict]] = {
            "search": [],
            "user": [],
        }

        for future in concurrent.futures.as_completed(future_results):
            source = future_results[future]
            try:
                payload = future.result()
            except Exception:
                continue
            result_by_source[source] = _normalize_notes(payload)

    merged: list[dict] = []
    seen: set[str] = set()
    for source in paths:
        for note in result_by_source[source]:
            clean = format_xhs_result(note)
            if not isinstance(clean, dict):
                continue
            note_key = _note_key(clean, note)
            if not note_key:
                continue
            if note_key in seen:
                _append_source(merged, note_key, source)
                continue
            seen.add(note_key)
            clean = dict(clean)
            clean["sources"] = [source]
            merged.append(clean)
            if len(merged) >= limit:
                return merged[:limit]

    return merged


def _append_source(merged: list[dict], note_key: str, source: str) -> None:
    for item in reversed(merged):
        if _note_key(item, item) == note_key:
            existing = item.setdefault("sources", [])
            if source not in existing:
                existing.append(source)
            break


def _run_xiaohongshu_json(
    args: list[str],
    *,
    timeout: int,
    command: str,
) -> t.Any:
    try:
        proc = subprocess.run(
            [command, "xiaohongshu", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=utf8_subprocess_env(),
            check=False,
        )
    except FileNotFoundError:
        return []

    text = (proc.stdout or proc.stderr or "").strip()
    if not text:
        return []
    if "EMPTY_RESULT" in text:
        return []
    if proc.returncode != 0 and text.startswith("{" ) is False and "items" not in text:
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    return data


def _normalize_notes(data: t.Any) -> list[dict]:
    notes: list[t.Any] = []
    if isinstance(data, list):
        notes = [item for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        # xiaohongshu-mcp style: {"items": [...]}
        if "items" in data and isinstance(data["items"], list):
            notes = [item for item in data["items"] if isinstance(item, dict)]
        elif "data" in data and isinstance(data["data"], dict):
            wrapped = data["data"]
            if "items" in wrapped and isinstance(wrapped["items"], list):
                notes = [item for item in wrapped["items"] if isinstance(item, dict)]
            elif "notes" in wrapped and isinstance(wrapped["notes"], list):
                notes = [item for item in wrapped["notes"] if isinstance(item, dict)]
        elif "note_card" in data and isinstance(data["note_card"], dict):
            notes = [data["note_card"]]
        elif "note" in data and isinstance(data["note"], dict):
            notes = [data["note"]]
    return [n for n in notes if isinstance(n, dict)]


def _note_key(cleaned: dict, raw: dict | None = None) -> str | None:
    source = raw if raw is not None and isinstance(raw, dict) else cleaned
    for key in _NOTE_ID_KEYS:
        value = source.get(key)
        if value:
            return f"{key}:{value}"
    for key in _NOTE_URL_KEYS:
        value = source.get(key)
        if value:
            return f"{key}:{value}"
    title = source.get("title") or source.get("desc") or source.get("content")
    if isinstance(title, str) and title:
        return f"title:{title[:80]}"
    return None
