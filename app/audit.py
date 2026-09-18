"""交接链路审计引擎。

输入按录入顺序（事件 id 升序）给出的事件列表，输出：
- 按时间排序后的事件（携带录入序号 entry_seq 与各自命中的冲突标记）
- findings：冲突/异常清单（逆序、重叠、责任断档、时间断档）
- 可读的审计结论 summary

校验规则
--------
逆序 reversal : 录入顺序中后一条事件的发生时间早于前一条。
重叠 overlap  : 时间排序后相邻两条发生时间完全相同。
责任断档 gap_chain : 时间排序后相邻两条，后一条的交出方不是前一条的接收方。
时间断档 gap_time  : 相邻两条时间差超过阈值（默认 24 小时，可配置）。
"""
from datetime import datetime
import os
from typing import Any


def _default_gap_hours() -> float:
    try:
        return max(float(os.environ.get("GAP_HOURS", "24")), 0.0)
    except ValueError:
        return 24.0


DEFAULT_GAP_HOURS = _default_gap_hours()

# 严重程度排序：error > warning > info
_LEVEL_RANK = {"error": 3, "warning": 2, "info": 1}

LABELS = {
    "reversal": "录入逆序",
    "overlap": "时间重叠",
    "gap_chain": "责任断档",
    "gap_time": "时间断档",
    "self_handover": "自交接",
}


def _parse(dt_text: str) -> datetime:
    return datetime.fromisoformat(dt_text)


def _finding(code: str, severity: str, event_ids: list[int],
             message: str) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "label": LABELS[code],
        "event_ids": event_ids,
        "message": message,
    }


def audit(events: list[Any], gap_hours: float = DEFAULT_GAP_HOURS) -> dict[str, Any]:
    """执行审计。

    events 中每个元素至少包含：
    id, occurred_at, from_party, to_party, location, note
    （sqlite3.Row 或 dict 均可）
    """
    raw = [dict(e) for e in events]
    # 录入序号，从 1 开始
    for seq, e in enumerate(raw, start=1):
        e["entry_seq"] = seq

    findings: list[dict[str, Any]] = []
    # event_id -> 命中的标记
    flags: dict[int, list[dict[str, str]]] = {e["id"]: [] for e in raw}

    # ---- 1. 录入逆序：按录入顺序比较相邻事件 ----
    for prev, curr in zip(raw, raw[1:]):
        if _parse(curr["occurred_at"]) < _parse(prev["occurred_at"]):
            f = _finding(
                "reversal", "error", [prev["id"], curr["id"]],
                f"第 {curr['entry_seq']} 条录入的事件"
                f"（{curr['occurred_at']}，{curr['from_party']} → "
                f"{curr['to_party']}）早于上一条第 {prev['entry_seq']} 条"
                f"（{prev['occurred_at']}），录入顺序与实际发生时间逆序。",
            )
            findings.append(f)
            flags[curr["id"]].append({"code": "reversal", "label": LABELS["reversal"],
                                      "severity": "error"})

    # ---- 按时间排序（时间相同则保持录入先后，稳定排序）----
    ordered = sorted(raw, key=lambda e: (_parse(e["occurred_at"]), e["entry_seq"]))

    # ---- 2/3/4. 时间线上的相邻校验 ----
    gap_hours = max(float(gap_hours or DEFAULT_GAP_HOURS), 0.0)
    for prev, curr in zip(ordered, ordered[1:]):
        t_prev, t_curr = _parse(prev["occurred_at"]), _parse(curr["occurred_at"])
        delta = t_curr - t_prev
        hours = delta.total_seconds() / 3600.0

        # 重叠：同一时刻存在两条交接，责任归属不唯一
        if delta.total_seconds() == 0:
            f = _finding(
                "overlap", "error", [prev["id"], curr["id"]],
                f"{t_curr:%Y-%m-%d %H:%M} 同时存在两条交接："
                f"{prev['from_party']} → {prev['to_party']} 与 "
                f"{curr['from_party']} → {curr['to_party']}，时间点重叠。",
            )
            findings.append(f)
            for eid in (prev["id"], curr["id"]):
                flags[eid].append({"code": "overlap", "label": LABELS["overlap"],
                                   "severity": "error"})

        # 责任断档：上一棒接收方与下一棒交出方不一致
        if prev["to_party"] != curr["from_party"]:
            f = _finding(
                "gap_chain", "warning", [prev["id"], curr["id"]],
                f"{prev['occurred_at']} 的接收方为「{prev['to_party']}」，"
                f"而 {curr['occurred_at']} 的交出方为「{curr['from_party']}」，"
                f"两者不一致，交接链路存在责任空档。",
            )
            findings.append(f)
            flags[curr["id"]].append({"code": "gap_chain",
                                      "label": LABELS["gap_chain"],
                                      "severity": "warning"})

        # 时间断档：两棒间隔超过阈值
        if gap_hours > 0 and hours > gap_hours:
            f = _finding(
                "gap_time", "info", [prev["id"], curr["id"]],
                f"「{prev['to_party']}」于 {prev['occurred_at']} 接收后，"
                f"间隔 {hours:.1f} 小时才于 {curr['occurred_at']} 交给"
                f"「{curr['to_party']}」，超过 {gap_hours:g} 小时阈值。",
            )
            findings.append(f)
            flags[curr["id"]].append({"code": "gap_time",
                                      "label": LABELS["gap_time"],
                                      "severity": "info"})

        # 自交接：同一方既是交出方又是接收方（信息性提示）
        if curr["from_party"] == curr["to_party"]:
            f = _finding(
                "self_handover", "info", [curr["id"]],
                f"{curr['occurred_at']} 的交出方与接收方均为"
                f"「{curr['from_party']}」，为自交接，请确认记录是否有误。",
            )
            findings.append(f)
            flags[curr["id"]].append({"code": "self_handover",
                                      "label": LABELS["self_handover"],
                                      "severity": "info"})

    # 单条事件也检查自交接
    if len(ordered) == 1:
        only = ordered[0]
        if only["from_party"] == only["to_party"]:
            f = _finding(
                "self_handover", "info", [only["id"]],
                f"{only['occurred_at']} 的交出方与接收方均为"
                f"「{only['from_party']}」，为自交接，请确认记录是否有误。",
            )
            findings.append(f)
            flags[only["id"]].append({"code": "self_handover",
                                      "label": LABELS["self_handover"],
                                      "severity": "info"})

    # ---- 汇总 ----
    counts = {"error": 0, "warning": 0, "info": 0}
    by_code: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] += 1
        by_code[f["code"]] = by_code.get(f["code"], 0) + 1

    if not raw:
        status, headline = "empty", "暂无交接事件"
    elif counts["error"]:
        status, headline = "fail", "审计不通过"
    elif counts["warning"]:
        status, headline = "warning", "审计通过（存在警告）"
    else:
        status, headline = "pass", "审计通过"

    if ordered:
        span = (f"{ordered[0]['occurred_at']} ～ {ordered[-1]['occurred_at']}")
    else:
        span = "—"

    summary_lines = [
        f"结论：{headline}",
        f"事件总数：{len(raw)}；时间跨度：{span}",
        f"严重问题 {counts['error']} 条，警告 {counts['warning']} 条，"
        f"提示 {counts['info']} 条。",
    ]
    if by_code:
        parts = [f"{LABELS[code]} {n} 处" for code, n in by_code.items()]
        summary_lines.append("异常分布：" + "，".join(parts) + "。")
    if raw and counts["error"] == 0 and counts["warning"] == 0:
        summary_lines.append("交接链路连续完整，未发现断档、重叠或逆序。")

    ordered_out = []
    for e in ordered:
        item = dict(e)
        item["flags"] = flags[e["id"]]
        ordered_out.append(item)

    return {
        "status": status,
        "headline": headline,
        "summary": "\n".join(summary_lines),
        "gap_hours": gap_hours,
        "total": len(raw),
        "counts": counts,
        "by_code": by_code,
        "span": span,
        "timeline": ordered_out,
        "findings": findings,
    }
