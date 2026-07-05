# -*- coding: utf-8 -*-

import json
from subprocess import CompletedProcess

from agent_reach import xiaohongshu_search
from agent_reach.xiaohongshu_search import search_xiaohongshu


class TestXiaohongshuSearchAggregator:
    def test_search_xiaohongshu_merges_search_and_user_results(self, monkeypatch):
        search_payload = {
            "items": [
                {"id": "n1", "title": "AI Note 1", "user": {"nickname": "我猫讲AI"}},
                {"id": "n2", "title": "AI Note 2", "user": {"nickname": "他猫讲AI"}},
            ]
        }
        user_payload = [
            {"id": "n2", "title": "AI Note 2", "user": {"nickname": "他猫讲AI"}},
            {"id": "n3", "title": "AI Note 3", "user": {"nickname": "我猫讲AI"}},
        ]

        def fake_run(cmd, *args, **kwargs):
            if cmd[2] == "search":
                return CompletedProcess(cmd, 0, stdout=json.dumps(search_payload))
            if cmd[2] == "user":
                return CompletedProcess(cmd, 0, stdout=json.dumps(user_payload))
            return CompletedProcess(cmd, 1, stdout="")

        monkeypatch.setattr(xiaohongshu_search.subprocess, "run", fake_run)

        result = search_xiaohongshu("我猫讲AI", limit=3)

        assert [item["id"] for item in result] == ["n1", "n2", "n3"]
        assert result[0]["sources"] == ["search"]
        assert result[1]["sources"] == ["search", "user"]

    def test_search_xiaohongshu_returns_empty_when_all_empty(self, monkeypatch):
        def fake_run(cmd, *args, **kwargs):
            return CompletedProcess(cmd, 0, stdout="EMPTY_RESULT")

        monkeypatch.setattr(xiaohongshu_search.subprocess, "run", fake_run)
        assert search_xiaohongshu("我猫讲AI", include_username_lookup=True) == []

    def test_search_xiaohongshu_handles_command_missing(self, monkeypatch):
        def fake_run(cmd, *args, **kwargs):
            raise FileNotFoundError("opencli")

        monkeypatch.setattr(xiaohongshu_search.subprocess, "run", fake_run)
        assert search_xiaohongshu("我猫讲AI") == []
