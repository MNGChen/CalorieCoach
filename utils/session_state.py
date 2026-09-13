"""Clear user-owned UI state when a workspace changes, including widget drafts."""
from collections.abc import MutableMapping
from typing import Any


def switch_workspace(state: MutableMapping[str, Any], username: str | None) -> None:
    # Preserve only application navigation; every other value belongs to the user.
    for key in list(state):
        if not key.startswith("_streamlit"):
            del state[key]
    if username:
        state["active_username"] = username


def ensure_workspace(state: MutableMapping[str, Any]) -> None:
    username = state.get("active_username")
    if state.get("_workspace_owner") != username:
        switch_workspace(state, username)
        state["_workspace_owner"] = username
