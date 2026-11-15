"""Overlapping follow-ups must publish and remove only their own responses."""
import importlib.util
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "plugins/muse-github/skills/muse-github-setup/templates/.github/scripts/muse_ci.py"
spec = importlib.util.spec_from_file_location("muse_followup_concurrency", HELPER)
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


@pytest.mark.parametrize("order", [(101, 102), (102, 101)])
@pytest.mark.parametrize("inline", [False, True])
def test_overlapping_followups_keep_independent_response_identity(order, inline):
    bot = {"login": "github-actions[bot]", "type": "Bot"}
    states = {number: {"repository": "org/repo", "number": 5,
                      "comment_ids": [10], "review_comment_ids": [55],
                      "run_url": f"https://github.com/org/repo/actions/runs/{number}"}
              for number in order}
    comments = {number: {"id": number, "html_url": f"https://github.com/org/repo/pull/5#issuecomment-{number}",
                         "user": bot, "body": f"Response {number}." + ("" if inline else " " + states[number]["run_url"])}
                for number in order}
    if inline:
        for state in states.values():
            state["thread_root_id"] = 55

    class API:
        def __init__(self):
            self.replies, self.deleted = {}, []
        def pages(self, path):
            return list(comments.values()) if "/issues/" in path else list(self.replies.values())
        def request(self, method, path, data=None):
            if method == "DELETE":
                number = int(path.rsplit("/", 1)[1])
                self.deleted.append(number)
                del comments[number]
                return None
            assert method == "POST" and path.endswith("/comments/55/replies")
            number = 200 + len(self.replies)
            self.replies[number] = {"id": number, "user": bot, "in_reply_to_id": 55,
                                    "pull_request_url": "https://api.github.com/repos/org/repo/pulls/5",
                                    "body": data["body"]}
            return {"id": number}
        def get(self, path):
            return self.replies[int(path.rsplit("/", 1)[1])]

    api = API()
    for number in order:
        update = {key: comments[number][key] for key in ("id", "html_url")}
        response, is_inline = ci.completed_response(api, states[number], update)
        assert response["id"] == number
        ci.finish_followup(api, states[number], response, is_inline)
    assert api.deleted == (list(order) if inline else [])
    if inline:
        assert len(api.replies) == 2
        for number, reply in zip(order, api.replies.values()):
            assert f"Response {number}." in reply["body"]
            assert states[number]["run_url"] in reply["body"]
    else:
        assert set(comments) == {101, 102}
