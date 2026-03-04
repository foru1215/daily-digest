#!/usr/bin/env python3
"""Daily Digest generator for GitHub Projects v2.

Queries the Life Board project, extracts today's tasks using 2-layer logic,
and creates a GitHub Issue with morning/noon/night sections.

Environment variables:
    GH_PAT          - Fine-grained PAT with project:read + issues:write
    DRY_RUN         - Set to "true" to print digest without creating issue
    DIGEST_REPO     - Target repo for issues (default: foru1215/daily-digest)
    PROJECT_ID      - Projects v2 node ID (default: PVT_kwHOD5C6os4BQdT8)
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
PAT = os.environ.get("GH_PAT", "")
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
DIGEST_REPO = os.environ.get("DIGEST_REPO", "foru1215/daily-digest")
PROJECT_ID = os.environ.get("PROJECT_ID", "PVT_kwHOD5C6os4BQdT8")

WEEKDAY_NAMES_JA = ["月", "火", "水", "木", "金", "土", "日"]

DOMAIN_TIME_BLOCK = {
    "資格（電工）": "朝",
    "AI外観検査": "夜",
    "副業": "夜",
    "運用": "夜",
}


def graphql(query):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={
            "Authorization": f"bearer {PAT}",
            "Content-Type": "application/json",
            "User-Agent": "daily-digest/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if "errors" in result:
                print(f"GraphQL errors: {json.dumps(result['errors'], indent=2)}",
                      file=sys.stderr)
                # Check if it's a permission issue
                for err in result.get("errors", []):
                    msg = err.get("message", "")
                    if "resource not accessible" in msg.lower() or "forbidden" in msg.lower():
                        print(
                            "\n=== PAT PERMISSION ISSUE ===\n"
                            "Fine-grained PAT needs:\n"
                            "  Account permissions -> Projects: Read-only\n"
                            "  Repository permissions -> Issues: Read and write\n"
                            "Make sure the PAT owner is the project owner.\n"
                            "============================\n",
                            file=sys.stderr,
                        )
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"GraphQL HTTP error {e.code}: {body}", file=sys.stderr)
        sys.exit(1)


def rest_api(method, path, body=None):
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"bearer {PAT}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "daily-digest/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8")
        print(f"REST error {e.code}: {body_text}", file=sys.stderr)
        sys.exit(1)


def fetch_all_items():
    all_items = []
    cursor = None
    while True:
        after = f', after: "{cursor}"' if cursor else ""
        data = graphql(f'''
        {{
          node(id: "{PROJECT_ID}") {{
            ... on ProjectV2 {{
              items(first: 100{after}) {{
                pageInfo {{ hasNextPage endCursor }}
                nodes {{
                  id
                  fieldValues(first: 20) {{
                    nodes {{
                      ... on ProjectV2ItemFieldTextValue {{
                        text
                        field {{ ... on ProjectV2Field {{ name }} }}
                      }}
                      ... on ProjectV2ItemFieldSingleSelectValue {{
                        name
                        field {{ ... on ProjectV2SingleSelectField {{ name }} }}
                      }}
                      ... on ProjectV2ItemFieldDateValue {{
                        date
                        field {{ ... on ProjectV2Field {{ name }} }}
                      }}
                      ... on ProjectV2ItemFieldNumberValue {{
                        number
                        field {{ ... on ProjectV2Field {{ name }} }}
                      }}
                    }}
                  }}
                  content {{
                    ... on Issue {{
                      title number url
                    }}
                    ... on DraftIssue {{
                      title
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
        ''')
        node = data.get("data", {}).get("node")
        if node is None:
            print(
                "ERROR: Could not access project. Full response:\n"
                f"{json.dumps(data, indent=2, ensure_ascii=False)}",
                file=sys.stderr,
            )
            print(
                "\n=== TROUBLESHOOTING ===\n"
                "1. Verify GH_PAT secret is set in repo settings\n"
                "2. PAT needs Account permissions -> Projects: Read-only\n"
                "3. PAT owner must be the project owner (foru1215)\n"
                "4. If using Fine-grained PAT, ensure it's not expired\n"
                "========================",
                file=sys.stderr,
            )
            sys.exit(1)
        items_data = node["items"]
        all_items.extend(items_data["nodes"])
        if not items_data["pageInfo"]["hasNextPage"]:
            break
        cursor = items_data["pageInfo"]["endCursor"]
    return all_items


def parse_item(item):
    content = item.get("content", {}) or {}
    fields = {}
    for fv in item["fieldValues"]["nodes"]:
        field_name = fv.get("field", {}).get("name")
        if not field_name:
            continue
        if "text" in fv:
            fields[field_name] = fv["text"]
        elif "name" in fv and field_name != "Title":
            fields[field_name] = fv["name"]
        elif "date" in fv:
            fields[field_name] = fv["date"]
        elif "number" in fv:
            fields[field_name] = fv["number"]
    return {
        "id": item["id"],
        "title": content.get("title", ""),
        "number": content.get("number"),
        "url": content.get("url", ""),
        "status": fields.get("Status", ""),
        "time_block": fields.get("Time Block", ""),
        "day_type": fields.get("DayType", ""),
        "domain": fields.get("Domain", ""),
        "phase": fields.get("Phase", ""),
        "next_action": fields.get("Next Action", ""),
        "outcome": fields.get("Outcome", ""),
        "estimate": fields.get("Estimate", ""),
        "energy": fields.get("Energy", ""),
        "due": fields.get("Due", ""),
        "focus": fields.get("Focus", ""),
        "start_date": fields.get("開始日", ""),
        "end_date": fields.get("終了日", ""),
    }


def filter_items(items, today_str):
    layer1 = []
    layer2 = []
    layer1_ids = set()

    for item in items:
        if item["status"] in ("Done", "サボった"):
            continue
        if item["due"] == today_str:
            layer1.append(item)
            layer1_ids.add(item["id"])
        elif (
            item["start_date"]
            and item["end_date"]
            and item["start_date"] <= today_str <= item["end_date"]
            and item["status"] == "In Progress"
            and item["id"] not in layer1_ids
        ):
            if not item["time_block"]:
                item["time_block"] = DOMAIN_TIME_BLOCK.get(item["domain"], "夜")
            layer2.append(item)

    return layer1, layer2


def group_by_time_block(items):
    groups = {"朝": [], "昼": [], "夜": []}
    for item in items:
        block = item.get("time_block", "夜")
        if block in groups:
            groups[block].append(item)
        else:
            groups["夜"].append(item)
    return groups


def sort_items(items):
    def key(item):
        focus = 0 if item.get("focus") == "⭐" else 1
        est = -int(item.get("estimate") or 0)
        return (focus, est)
    return sorted(items, key=key)


def check_constraints(groups, is_weekday):
    warnings = []
    if not is_weekday:
        return warnings
    for item in groups.get("朝", []) + groups.get("昼", []):
        if item["domain"] and item["domain"] not in ("資格（電工）", ""):
            warnings.append(
                f"⚠️ 平日の朝/昼に{item['domain']}タスクあり: {item['title'][:30]}"
            )
    for item in groups.get("夜", []):
        if item["domain"] and item["domain"] not in ("AI外観検査", ""):
            warnings.append(
                f"⚠️ 平日夜にAI以外のタスクあり: {item['title'][:30]}"
            )
    return warnings


def get_plan_b(items):
    candidates = [
        item for item in items
        if item.get("energy") in ("低", "中")
        and item.get("estimate") == "45"
        and item.get("status") not in ("Done", "サボった")
        and item.get("domain") == "AI外観検査"
    ]
    return sort_items(candidates)[:2]


def clean_title(title):
    return re.sub(r"^\[.*?\]\s*\[.*?\]\s*", "", title)


def format_item_line(item, is_layer2=False):
    focus = "⭐ " if item.get("focus") == "⭐" else ""
    source = " `[Sprint]`" if is_layer2 else ""
    na = item.get("next_action", "")
    na_part = f" — {na}" if na else ""
    est = item.get("estimate", "")
    est_part = f" ({est}分)" if est else ""
    url = item.get("url", "")
    title = clean_title(item["title"])
    if url:
        return f"- [ ] {focus}**[{title}]({url})**{na_part}{est_part}{source}"
    return f"- [ ] {focus}**{title}**{na_part}{est_part}{source}"


def format_digest(groups_l1, groups_l2, warnings, plan_b, today, is_weekday):
    today_str = today.strftime("%Y-%m-%d")
    weekday = WEEKDAY_NAMES_JA[today.weekday()]
    day_label = "平日" if is_weekday else "土日"

    lines = [f"# Daily Digest {today_str} ({weekday}) [{day_label}]", ""]

    sections = [
        ("☀️ 朝", "朝"),
        ("🌤️ 昼", "昼"),
        ("🌙 夜", "夜"),
    ]

    for header, block in sections:
        lines.append(f"## {header}")
        lines.append("")
        l1_items = sort_items(groups_l1.get(block, []))
        l2_items = sort_items(groups_l2.get(block, []))
        if not l1_items and not l2_items:
            lines.append("_タスクなし_")
            lines.append("")
            continue
        for item in l1_items[:3]:
            lines.append(format_item_line(item))
        if len(l1_items) > 3:
            lines.append(f"  _...他 {len(l1_items) - 3} 件_")
        for item in l2_items[:2]:
            lines.append(format_item_line(item, is_layer2=True))
        if len(l2_items) > 2:
            lines.append(f"  _...他 {len(l2_items) - 2} 件のアクティブスプリント_")
        lines.append("")

    if plan_b:
        lines.append("### 💤 Plan B（疲れた日・45分版）")
        lines.append("")
        for item in plan_b:
            lines.append(format_item_line(item))
        lines.append("")

    if warnings:
        lines.append("---")
        lines.append("")
        for w in warnings:
            lines.append(w)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "> ルール: 平日夜はAI専用 / 疲れてもゼロ禁止(45分OK、週2まで) / "
        "Focus同時1件まで"
    )

    return "\n".join(lines)


def main():
    if not PAT:
        print("ERROR: GH_PAT environment variable is required.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(JST)
    today_str = now.strftime("%Y-%m-%d")
    is_weekday = now.weekday() < 5

    print(f"Date: {today_str} (JST), Weekday: {is_weekday}")
    print(f"Dry run: {DRY_RUN}")

    print("Fetching project items...")
    raw_items = fetch_all_items()
    items = [parse_item(i) for i in raw_items]
    print(f"Total items: {len(items)}")

    layer1, layer2 = filter_items(items, today_str)
    print(f"Layer 1 (Due=today): {len(layer1)}")
    print(f"Layer 2 (Active sprint): {len(layer2)}")

    groups_l1 = group_by_time_block(layer1)
    groups_l2 = group_by_time_block(layer2)

    merged = {k: groups_l1.get(k, []) + groups_l2.get(k, []) for k in ("朝", "昼", "夜")}
    warnings = check_constraints(merged, is_weekday)
    plan_b = get_plan_b(items)

    body = format_digest(groups_l1, groups_l2, warnings, plan_b, now, is_weekday)
    title = f"Daily Digest {today_str}"

    if DRY_RUN:
        print(f"\n{'='*60}")
        print(f"TITLE: {title}")
        print(f"{'='*60}")
        print(body)
        print(f"{'='*60}")
        print("[DRY RUN] Issue not created.")
        return

    print(f"Creating issue in {DIGEST_REPO}...")
    owner, repo = DIGEST_REPO.split("/")

    # Ensure label exists
    try:
        rest_api("POST", f"/repos/{owner}/{repo}/labels", {
            "name": "daily-digest",
            "color": "0075ca",
            "description": "Auto-generated daily digest",
        })
    except SystemExit:
        pass  # Label already exists

    result = rest_api("POST", f"/repos/{owner}/{repo}/issues", {
        "title": title,
        "body": body,
        "labels": ["daily-digest"],
    })
    print(f"Issue created: {result['html_url']}")


if __name__ == "__main__":
    main()
