#!/usr/bin/env python3
"""Local reminder for source MCP calls; not a read-only credential boundary."""
import re

import _common as c

READ_TOOLS = {
    "figma": {"get_design_context", "get_metadata", "get_screenshot", "get_variable_defs", "get_figjam", "whoami", "get_code_connect_map"},
    "notion": {"search", "fetch", "notion_search", "notion_fetch", "get_page", "get_block", "list_blocks", "get_database",
               "api_get_self", "api_get_user", "api_get_users", "api_retrieve_a_page", "api_retrieve_a_block",
               "api_get_block_children", "api_post_search", "api_query_data_source"},
    "dropbox": {"search", "search_files", "list_folder", "list_folder_continue", "get_file", "get_file_metadata", "get_file_content",
                "get_file_contents", "download_file", "get_shared_link_file", "get_shared_link_metadata"},
    "telegram": {"search", "search_messages", "get_chat", "get_history", "get_messages", "list_chats", "get_me"},
}


def decide(tool_name):
    if not isinstance(tool_name, str) or not tool_name.startswith("mcp__"):
        return None
    parts = tool_name.lower().split("__")
    provider = next((p for p in READ_TOOLS if any(p in part for part in parts[1:-1])), None)
    if provider is None:
        return None
    action = parts[-1].replace("-", "_")
    if action in READ_TOOLS[provider]:
        return None
    rule = "source-write-or-unknown"
    c.log_decision("guard_sources", "ask", [rule])
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
            "permissionDecisionReason": "[gardenstep-team] 원자료 수집은 읽기 전용입니다. 이 도구는 검증된 읽기 목록에 없습니다. 외부 쓰기·메신저 발신은 현재 작업의 명시적 지시/권한을 확인하세요. 로컬 hook은 서버 권한을 대신하지 않습니다."}}


def main():
    data = c.read_input()
    result = decide(data.get("tool_name"))
    if result:
        c.emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
