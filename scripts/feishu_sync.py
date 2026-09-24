#!/usr/bin/env python3
"""飞书多维表格双向同步。

本地 info_source.db 是唯一真相源；飞书只是另一个可读、可输入的入口。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import selection_db

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "selection-sync.json"
OUTPUT_DIR = PROJECT_ROOT / "output"
LARK_CLI = os.environ.get("LARK_CLI", "lark-cli")

TABLE_NAME = "选题"
SCRIPT_FIELD = "稿子"
FIELDS: list[dict[str, Any]] = [
    {"name": "标题", "type": "text"},
    {
        "name": "类型",
        "type": "select",
        "multiple": False,
        "options": [{"name": "灵感"}, {"name": "GitHub 项目"}],
    },
    {"name": "项目名", "type": "text"},
    {"name": "链接", "type": "text"},
    {"name": "一句话说明", "type": "text"},
    {"name": "为什么值得讲", "type": "text"},
    {
        "name": "状态",
        "type": "select",
        "multiple": False,
        "options": [
            {"name": "灵感收件箱"},
            {"name": "候选"},
            {"name": "已选"},
            {"name": "不讲"},
            {"name": "排期中"},
            {"name": "已讲"},
            {"name": "归档"},
            {"name": "冲突"},
        ],
    },
    {
        "name": "优先级",
        "type": "select",
        "multiple": False,
        "options": [{"name": "高"}, {"name": "中"}, {"name": "低"}],
    },
    {"name": "来源", "type": "text"},
    {"name": "本地ID", "type": "text"},
    {"name": "更新时间", "type": "text"},
    # 讲稿附件挂在选题记录上（见 push_script）。字段由 ensure_script_field 兜底创建，
    # 列在这里是为了「重新 setup 一张新表」时字段不丢。
    {"name": SCRIPT_FIELD, "type": "attachment"},
]
VIEWS = [
    {"name": "灵感收件箱", "type": "grid", "filter_status": "灵感收件箱"},
    {"name": "本周候选", "type": "grid", "filter_status": "候选"},
    {"name": "已讲", "type": "grid", "filter_status": "已讲"},
    {"name": "归档", "type": "grid", "filter_status": "归档"},
]
STATUS_TO_LOCAL = {
    "灵感收件箱": "inbox",
    "候选": "candidate",
    "已选": "shortlist",
    "不讲": "rejected",
    "排期中": "scheduled",
    "已讲": "used",
    "归档": "archived",
}
STATUS_TO_REMOTE = {v: k for k, v in STATUS_TO_LOCAL.items()}
PRIORITY_TO_LOCAL = {"高": 1, "中": 2, "低": 3}
PRIORITY_TO_REMOTE = {1: "高", 2: "中", 3: "低"}


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(data: dict[str, Any]) -> Path:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return CONFIG_PATH


def is_configured(config: dict[str, Any] | None = None) -> bool:
    cfg = config or load_config()
    return bool(cfg.get("base_token") and cfg.get("table_id"))


def _run(args: list[str], timeout: int = 60) -> dict[str, Any]:
    cmd = [LARK_CLI, "base", *args, "--as", "user", "--format", "json"]
    env = os.environ.copy()
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(key, None)
    # lark-cli 的启动头是 `#!/usr/bin/env node`。launchd/launchctl 拉起的环境
    # 常常没有 node，这里把已知的 node 安装位置补进 PATH，避免同步静默失败。
    node_dirs = [
        "/usr/local/bin",
        "/opt/homebrew/bin",
        str(Path.home() / ".local" / "bin"),
    ]
    path_parts = env.get("PATH", "").split(os.pathsep)
    for d in node_dirs:
        if os.path.exists(os.path.join(d, "node")) and d not in path_parts:
            path_parts.insert(0, d)
    env["PATH"] = os.pathsep.join(path_parts)
    proc = subprocess.run(
        cmd, cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=timeout, env=env
    )
    text = (proc.stdout or "").strip()
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "lark-cli 调用失败").strip()[-1500:])
    if not text:
        raise RuntimeError("lark-cli 没有返回 JSON")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # 有些子命令会先打印一行提示，这里取第一段完整 JSON。
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("lark-cli 输出不是 JSON：" + text[:300]) from exc
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            raise ValueError("lark-cli 输出不是 JSON：" + text[:300]) from exc


def _find_objects(data: Any, keys: set[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(data, dict):
        if any(k in data for k in keys):
            found.append(data)
        for value in data.values():
            found.extend(_find_objects(value, keys))
    elif isinstance(data, list):
        for value in data:
            found.extend(_find_objects(value, keys))
    return found


def _unique_items(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        rid = item.get(key)
        if not rid or rid in seen:
            continue
        seen.add(str(rid))
        out.append(item)
    return out


def _records(payload: Any) -> list[dict[str, Any]]:
    # lark-cli record-list 会返回 fields + record_id_list + data 二维数组。
    objs = _find_objects(payload, {"record_id_list", "recordIdList"})
    out: list[dict[str, Any]] = []
    for obj in objs:
        names = obj.get("fields") or []
        ids = obj.get("record_id_list") or obj.get("recordIdList") or []
        rows = obj.get("data") or obj.get("records") or []
        if names and isinstance(rows, list):
            for i, row in enumerate(rows):
                if i >= len(ids):
                    break
                values = row if isinstance(row, list) else []
                out.append({
                    "record_id": ids[i],
                    "fields": dict(zip(names, values)),
                })
    if out:
        return out
    items = _find_objects(payload, {"record_id", "recordId", "fields"})
    return _unique_items(items, "record_id" if any("record_id" in x for x in items) else "recordId")


def _record_id(payload: Any) -> str:
    objs = _find_objects(payload, {"record_id", "recordId"})
    for obj in objs:
        rid = obj.get("record_id") or obj.get("recordId")
        if rid:
            return str(rid)
    raise RuntimeError("lark-cli 返回里没有 record_id")


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return " ".join(filter(None, [_cell_text(v) for v in value])).strip()
    if isinstance(value, dict):
        for key in ("text", "name", "value", "link"):
            if key in value:
                return str(value[key]).strip()
    return str(value).strip()


def selection_to_fields(row: dict[str, Any], mark_conflict: bool = False) -> dict[str, Any]:
    status = "冲突" if mark_conflict else STATUS_TO_REMOTE.get(row.get("status", ""), "灵感收件箱")
    kind = "灵感" if row.get("kind") == "idea" else "GitHub 项目"
    return {
        "标题": row.get("title") or "未命名选题",
        "类型": kind,
        "项目名": row.get("project_full_name") or "",
        "链接": row.get("url") or "",
        "一句话说明": row.get("summary") or "",
        "为什么值得讲": row.get("why") or "",
        "状态": status,
        "优先级": PRIORITY_TO_REMOTE.get(int(row.get("priority") or 2), "中"),
        "来源": row.get("source") or "手动",
        "本地ID": str(row["id"]),
        "更新时间": row.get("updated_at") or now(),
    }


def fields_to_selection(fields: dict[str, Any], local_id: str | None = None) -> dict[str, Any]:
    kind_text = _cell_text(fields.get("类型"))
    status_text = _cell_text(fields.get("状态"))
    priority_text = _cell_text(fields.get("优先级"))
    title = _cell_text(fields.get("标题")) or _cell_text(fields.get("项目名")) or "未命名选题"
    project = _cell_text(fields.get("项目名"))
    row: dict[str, Any] = {
        "title": title,
        "kind": "idea" if "灵感" in kind_text else "project",
        "project_full_name": project or None,
        "url": _cell_text(fields.get("链接")) or None,
        "summary": _cell_text(fields.get("一句话说明")) or None,
        "why": _cell_text(fields.get("为什么值得讲")) or None,
        "priority": PRIORITY_TO_LOCAL.get(priority_text, 2),
        "source": _cell_text(fields.get("来源")) or "飞书",
    }
    # 「冲突」是同步标记，不导入成本地状态。
    if status_text in STATUS_TO_LOCAL:
        row["status"] = STATUS_TO_LOCAL[status_text]
    if local_id:
        row["source"] = row["source"] or "飞书"
    return row


def content_hash(fields: dict[str, Any]) -> str:
    payload = {
        key: _cell_text(fields.get(key))
        for key in ("标题", "类型", "项目名", "链接", "一句话说明", "为什么值得讲", "状态", "优先级", "来源")
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _list_records(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    payload = _run(
        [
            "+record-list",
            "--base-token",
            str(cfg["base_token"]),
            "--table-id",
            str(cfg["table_id"]),
            "--limit",
            "200",
        ]
    )
    return _records(payload)


def _upsert_record(
    cfg: dict[str, Any], fields: dict[str, Any], record_id: str | None
) -> str:
    args = [
        "+record-upsert",
        "--base-token",
        str(cfg["base_token"]),
        "--table-id",
        str(cfg["table_id"]),
        "--json",
        json.dumps(fields, ensure_ascii=False),
    ]
    if record_id:
        args += ["--record-id", record_id]
    payload = _run(args)
    try:
        return _record_id(payload)
    except RuntimeError:
        if record_id:
            return str(record_id)
        # +record-upsert 新建时只返回字段快照；用本地ID回查 record_id。
        local_id = str(fields.get("本地ID") or "")
        for rec in _list_records(cfg):
            if _cell_text((rec.get("fields") or {}).get("本地ID")) == local_id:
                return str(rec.get("record_id") or rec.get("recordId"))
        raise


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _local_changed(row: dict[str, Any], state: dict[str, Any] | None) -> bool:
    if not state or not state.get("last_synced_at"):
        return True
    local = _parse_time(row.get("updated_at"))
    synced = _parse_time(state.get("last_synced_at"))
    return bool(local and synced and local > synced)


def sync_once(db_path: str | Path | None = None) -> dict[str, Any]:
    """同步一次；返回每个动作的计数和错误。"""
    cfg = load_config()
    if not is_configured(cfg):
        return {"ok": False, "reason": "未配置飞书表", "created_remote": 0, "imported": 0, "updated_remote": 0, "conflicts": 0}
    selection_db.init_db(db_path)
    states = selection_db.feishu_states(db_path)
    remote_records = _list_records(cfg)
    by_local_id: dict[str, dict[str, Any]] = {}
    by_record_id: dict[str, dict[str, Any]] = {}
    for rec in remote_records:
        rid = str(rec.get("record_id") or rec.get("recordId") or "")
        fields = rec.get("fields") or {}
        local_id = _cell_text(fields.get("本地ID"))
        if local_id:
            by_local_id[local_id] = rec
        if rid:
            by_record_id[rid] = rec

    result = {
        "ok": True,
        "created_remote": 0,
        "imported": 0,
        "updated_remote": 0,
        "conflicts": 0,
        "errors": [],
    }

    # 1. 飞书新增/修改导入本地。
    for rec in remote_records:
        try:
            rid = str(rec.get("record_id") or rec.get("recordId") or "")
            fields = rec.get("fields") or {}
            local_id = _cell_text(fields.get("本地ID"))
            current_hash = content_hash(fields)
            if not local_id:
                row = selection_db.create_selection(fields_to_selection(fields), db_path)
                row = selection_db.update_selection(
                    row["id"], {"lark_record_id": rid}, db_path
                )
                selection_db.set_feishu_state(
                    row["id"], cfg["base_token"], cfg["table_id"], rid,
                    _cell_text(fields.get("更新时间")), current_hash, "ok", None, db_path,
                )
                result["imported"] += 1
                continue

            if not local_id.isdigit():
                continue
            local = selection_db.get_selection(int(local_id), db_path)
            if not local:
                continue
            state = states.get(local["id"])
            old_hash = state.get("remote_hash") if state else None
            remote_changed = bool(old_hash and old_hash != current_hash)
            local_changed = _local_changed(local, state)
            if remote_changed and local_changed:
                # 本地优先；飞书只打冲突标记，不覆盖本地内容。
                if state and state.get("sync_status") != "conflict":
                    conflict_fields = {"状态": "冲突"}
                    _upsert_record(cfg, conflict_fields, rid)
                    result["conflicts"] += 1
                selection_db.set_feishu_state(
                    local["id"], cfg["base_token"], cfg["table_id"], rid,
                    _cell_text(fields.get("更新时间")), current_hash, "conflict",
                    "两端都有改动，已保留本地版本。", db_path,
                )
                continue
            if remote_changed and not local_changed:
                remote_row = fields_to_selection(fields)
                # 不把「冲突」标记导回本地。
                remote_row["updated_at"] = selection_db.now()
                selection_db.update_selection(local["id"], remote_row, db_path)
                selection_db.set_feishu_state(
                    local["id"], cfg["base_token"], cfg["table_id"], rid,
                    _cell_text(fields.get("更新时间")), current_hash, "ok", None, db_path,
                )
                result["imported"] += 1
        except Exception as exc:  # noqa: BLE001
            result["errors"].append("导入飞书记录失败：%s" % exc)

    # 2. 本地新增或本地改动推到飞书。
    for row in selection_db.list_selections(db_path):
        try:
            sid = row["id"]
            state = states.get(sid)
            record_id = state.get("record_id") or row.get("lark_record_id") if state else row.get("lark_record_id")
            record_id = str(record_id) if record_id else None
            # 飞书里没找到这条 record 时就新建，不硬删。
            if record_id and record_id not in by_record_id:
                record_id = None
            if not state and not record_id:
                fields = selection_to_fields(row)
                rid = _upsert_record(cfg, fields, None)
                selection_db.update_selection(sid, {"lark_record_id": rid}, db_path)
                selection_db.set_feishu_state(
                    sid, cfg["base_token"], cfg["table_id"], rid,
                    fields["更新时间"], content_hash(fields), "ok", None, db_path,
                )
                result["created_remote"] += 1
                continue
            if (not state and record_id) or (state and _local_changed(row, state) and state.get("sync_status") != "conflict"):
                fields = selection_to_fields(row)
                rid = _upsert_record(cfg, fields, record_id)
                selection_db.update_selection(sid, {"lark_record_id": rid}, db_path)
                selection_db.set_feishu_state(
                    sid, cfg["base_token"], cfg["table_id"], rid,
                    fields["更新时间"], content_hash(fields), "ok", None, db_path,
                )
                result["updated_remote"] += 1
        except Exception as exc:  # noqa: BLE001
            result["errors"].append("推送本地选题失败：%s" % exc)

    if result["errors"]:
        result["ok"] = False
    return result


def create_views(cfg: dict[str, Any]) -> list[str]:
    """创建四个常用视图；已存在时 CLI 会返回错误，这里跳过。"""
    made: list[str] = []
    for view in VIEWS:
        try:
            payload = _run(
                [
                    "+view-create",
                    "--base-token",
                    str(cfg["base_token"]),
                    "--table-id",
                    str(cfg["table_id"]),
                    "--json",
                    json.dumps({"name": view["name"], "type": view["type"]}, ensure_ascii=False),
                ]
            )
            objs = _find_objects(payload, {"view_id", "viewId", "name"})
            view_id = ""
            for obj in objs:
                if obj.get("name") == view["name"]:
                    view_id = str(obj.get("view_id") or obj.get("viewId") or view["name"])
                    break
            if view_id:
                try:
                    _run(
                        [
                            "+view-set-filter",
                            "--base-token",
                            str(cfg["base_token"]),
                            "--table-id",
                            str(cfg["table_id"]),
                            "--view-id",
                            view_id,
                            "--json",
                            json.dumps(
                                {"logic": "and", "conditions": [["状态", "==", view["filter_status"]]]},
                                ensure_ascii=False,
                            ),
                        ]
                    )
                except Exception:
                    pass
            made.append(view["name"])
        except Exception:
            continue
    return made


def setup() -> dict[str, Any]:
    """创建 Base 和第一张表，把非敏感 token 写进配置。"""
    payload = _run(
        [
            "+base-create",
            "--name",
            "播客选题台",
            "--table-name",
            TABLE_NAME,
            "--fields",
            json.dumps(FIELDS, ensure_ascii=False),
        ],
        timeout=90,
    )
    # 兼容 data.base.app_token / data.app_token / app_token。
    base_token = ""
    table_id = ""

    def walk(data: Any) -> None:
        nonlocal base_token, table_id
        if isinstance(data, dict):
            base_token = base_token or str(data.get("base_token") or data.get("app_token") or "")
            table_id = table_id or str(data.get("table_id") or data.get("id") or "")
            for value in data.values():
                walk(value)
        elif isinstance(data, list):
            for value in data:
                walk(value)

    walk(payload)
    if not base_token or not table_id:
        objs = _find_objects(payload, {"base_token", "app_token", "table_id"})
        for obj in objs:
            base_token = base_token or str(obj.get("base_token") or obj.get("app_token") or "")
            table_id = table_id or str(obj.get("table_id") or "")
    if not base_token or not table_id:
        raise RuntimeError("无法从 lark-cli 返回里取到 base_token/table_id")

    cfg = {
        "base_token": base_token,
        "table_id": table_id,
        "table_name": TABLE_NAME,
        "views": [v["name"] for v in VIEWS],
        "fields": [f["name"] for f in FIELDS],
    }
    save_config(cfg)
    cfg["created_views"] = create_views(cfg)
    save_config(cfg)
    return cfg


# ---------------------------------------------------------------- 讲稿推送
#
# 为什么走「附件字段」而不是写文本：讲稿是四五万字节的 md，塞进文本字段既读不动、
# 也不是它的用途；Base 原生附件单元格可以直接在飞书里下载和预览。
#
# 命令实测（lark-cli 1.0.70）：
#   +record-upload-attachment  --record-id --field-id <字段名或ID> --file <路径> --file ...
#       语义是 **append**：同一个格重复调用会越堆越多，所以上传前必须先删。
#   +record-remove-attachment  --record-id --field-id --file-token <token> --yes
#       是 high-risk-write，**必须带 --yes**，缺了直接报错。
#   --field-id 字段名和字段 ID 都收，这里统一传字段名「稿子」。


def _md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _latest_script(date_str: str | None = None) -> Path | None:
    """output/ 下带日期的稿子：给日期取那天，否则取最新一份。

    刻意不读 latest-script.md —— 那是当期滚动指针，夜班一跑就滚，钉它会推错稿子
    （工作台期次卡片踩过这个坑）。
    """
    if date_str:
        p = OUTPUT_DIR / ("%s-script.md" % date_str)
        return p if p.exists() else None
    cands = sorted(OUTPUT_DIR.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-script.md"))
    return cands[-1] if cands else None


def _date_from_script(name: str) -> str:
    m = re.match(r"(\d{4}-\d{2}-\d{2})-script\.md$", name)
    return m.group(1) if m else name


def _field_objects(payload: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for obj in _find_objects(payload, {"name", "type"}):
        if isinstance(obj.get("name"), str) and "type" in obj:
            out.append(obj)
    return out


def ensure_script_field(cfg: dict[str, Any]) -> bool:
    """确保选题表有「稿子」附件字段；没有就建。返回是否新建。"""
    args = ["--base-token", str(cfg["base_token"]), "--table-id", str(cfg["table_id"])]
    for field in _field_objects(_run(["+field-list", *args])):
        if field.get("name") == SCRIPT_FIELD:
            return False
    _run(
        [
            "+field-create",
            *args,
            "--json",
            json.dumps({"type": "attachment", "name": SCRIPT_FIELD}, ensure_ascii=False),
        ]
    )
    return True


def _file_tokens(payload: Any) -> list[str]:
    """递归收集返回里的 file_token，兼容 file_token / file_tokens 两种形状。"""
    found: list[str] = []

    def walk(data: Any) -> None:
        if isinstance(data, dict):
            for key, value in data.items():
                if key in ("file_token", "fileToken") and isinstance(value, str):
                    found.append(value)
                elif key in ("file_tokens", "fileTokens") and isinstance(value, list):
                    found.extend(str(v) for v in value if isinstance(v, str))
                else:
                    walk(value)
        elif isinstance(data, list):
            for value in data:
                walk(value)

    walk(payload)
    out: list[str] = []
    for token in found:
        if token and token not in out:
            out.append(token)
    return out


def _attachment_cells(value: Any) -> list[dict[str, str]]:
    """从附件单元格值里抽 {file_token, name}，不假设具体返回形状。"""
    out: list[dict[str, str]] = []

    def walk(data: Any) -> None:
        if isinstance(data, dict):
            token = data.get("file_token") or data.get("fileToken")
            if token:
                out.append({"file_token": str(token), "name": str(data.get("name") or "")})
                return
            for item in data.values():
                walk(item)
        elif isinstance(data, list):
            for item in data:
                walk(item)

    walk(value)
    return out


def _record_attachment_cells(
    cfg: dict[str, Any], record_id: str, field: str
) -> list[dict[str, str]]:
    for rec in _list_records(cfg):
        if str(rec.get("record_id") or "") == str(record_id):
            return _attachment_cells((rec.get("fields") or {}).get(field))
    return []


def _base_args(cfg: dict[str, Any], record_id: str) -> list[str]:
    return [
        "--base-token", str(cfg["base_token"]),
        "--table-id", str(cfg["table_id"]),
        "--record-id", str(record_id),
        "--field-id", SCRIPT_FIELD,
    ]


def _upload_attachment(cfg: dict[str, Any], record_id: str, path: Path) -> list[str]:
    # lark-cli 只收「当前目录内的相对路径」——_run() 的 cwd 就是 PROJECT_ROOT，
    # 传绝对路径会被判 unsafe file path 直接拒（实测报错，别改回绝对路径）。
    rel = os.path.relpath(path, PROJECT_ROOT)
    payload = _run(
        ["+record-upload-attachment", *_base_args(cfg, record_id), "--file", rel],
        timeout=120,
    )
    return _file_tokens(payload)


def _remove_attachments(cfg: dict[str, Any], record_id: str, tokens: list[str]) -> list[str]:
    if not tokens:
        return []
    args = ["+record-remove-attachment", *_base_args(cfg, record_id), "--yes"]
    for token in tokens:
        args += ["--file-token", token]
    _run(args)
    return list(tokens)


def push_script(
    db_path: str | Path | None = None,
    date_str: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """把某期讲稿 md 推成选题记录「稿子」字段的附件。

    幂等靠 script_pushes 里的 md5：稿子没变且非 force 直接 skipped。
    上传前先删掉上一次的附件（upload 是 append 语义），换稿子只留一份。
    """
    cfg = load_config()
    day = date_str or ""
    if not is_configured(cfg):
        return {"ok": False, "reason": "未配置飞书表", "date": day}
    selection_db.init_db(db_path)

    script = _latest_script(date_str)
    if not script:
        return {
            "ok": False,
            "date": day,
            "reason": "找不到稿子文件（%s）" % (date_str or "output/ 下没有 *-script.md"),
        }
    day = date_str or _date_from_script(script.name)
    digest = _md5_file(script)

    prev = selection_db.get_script_push(day, db_path)
    if prev and prev.get("file_md5") == digest and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "稿子没变，跳过",
            "date": day,
            "file": script.name,
            "record_id": prev.get("record_id") or "",
            "file_token": prev.get("file_token") or "",
        }

    selection = selection_db.selection_scheduled_for(day, db_path)
    if not selection:
        return {"ok": False, "date": day, "file": script.name,
                "reason": "%s 没有排期选题，无处可挂" % day}
    record_id = str(selection.get("lark_record_id") or "")
    if not record_id:
        return {
            "ok": False, "date": day, "file": script.name,
            "reason": "选题 #%s 还没有飞书 record_id，先跑一次同步" % selection.get("id"),
        }

    ensure_script_field(cfg)

    # 防重复堆积：台账里的 token 是必删的；再读一遍表格把同名附件也收进来，
    # 覆盖「台账丢了」或「手动传过一份」的情况。读回失败不拦上传，靠台账兜底。
    stale: list[str] = []
    if prev and prev.get("file_token"):
        stale.append(str(prev["file_token"]))
    try:
        for cell in _record_attachment_cells(cfg, record_id, SCRIPT_FIELD):
            if cell["name"] in ("", script.name) and cell["file_token"] not in stale:
                stale.append(cell["file_token"])
    except Exception:  # noqa: BLE001
        pass
    removed = _remove_attachments(cfg, record_id, stale)

    tokens = _upload_attachment(cfg, record_id, script)
    token = tokens[0] if tokens else ""
    selection_db.set_script_push(
        day, int(selection["id"]), record_id, script.name, digest, token, db_path
    )
    return {
        "ok": True, "skipped": False, "date": day, "file": script.name,
        "selection_id": int(selection["id"]), "record_id": record_id,
        "removed": removed, "file_token": token,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="飞书选题表同步器")
    ap.add_argument("--setup", action="store_true", help="创建飞书 Base/表/视图并写配置")
    ap.add_argument("--once", action="store_true", help="同步一次")
    ap.add_argument("--push-script", action="store_true", help="把讲稿 md 推到选题记录的「稿子」附件字段")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD（默认取 output/ 下最新一期稿子）")
    ap.add_argument("--force", action="store_true", help="稿子没变也重推（先删旧附件再传）")
    args = ap.parse_args()
    try:
        if args.setup:
            cfg = setup()
            print(json.dumps({"ok": True, "config": cfg}, ensure_ascii=False, indent=2))
            return 0
        if args.push_script:
            result = push_script(date_str=args.date, force=args.force)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("ok") else 2
        result = sync_once()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 2
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
