"""审计报告生成：Markdown 与独立可打开的 HTML。"""
from datetime import datetime
from html import escape
from typing import Any


def _fmt_party(e: dict[str, Any]) -> str:
    loc = f"（地点：{e['location']}）" if e.get("location") else ""
    return f"{e['from_party']} → {e['to_party']}{loc}"


def build_markdown(sample: dict[str, Any], result: dict[str, Any]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# 样本交接链路审计报告",
        "",
        f"- 样本编号：{sample['code']}",
        f"- 样本名称：{sample['name']}",
        f"- 时间跨度：{result['span']}",
        f"- 事件总数：{result['total']}",
        f"- 断档阈值：{result['gap_hours']:g} 小时",
        f"- 生成时间：{now}",
        "",
        "## 审计结论",
        "",
        f"**{result['headline']}**",
        "",
    ]
    for line in result["summary"].split("\n"):
        lines.append(f"> {line}")
    lines.append("")

    lines.append("## 交接时间线（按发生时间排序）")
    lines.append("")
    if result["timeline"]:
        lines.append("| # | 发生时间 | 交出方 | 接收方 | 地点 | 录入序号 | 标记 |")
        lines.append("|---|----------|--------|--------|------|----------|------|")
        for i, e in enumerate(result["timeline"], 1):
            tags = "、".join(f["label"] for f in e["flags"]) or "正常"
            lines.append(
                f"| {i} | {e['occurred_at']} | {e['from_party']} | "
                f"{e['to_party']} | {e.get('location') or ''} | "
                f"{e['entry_seq']} | {tags} |"
            )
            if e.get("note"):
                lines.append(f"| | 备注 | {e['note']} | | | | |")
    else:
        lines.append("暂无交接事件。")
    lines.append("")

    lines.append("## 冲突与异常清单")
    lines.append("")
    if result["findings"]:
        sev_cn = {"error": "严重", "warning": "警告", "info": "提示"}
        for i, f in enumerate(result["findings"], 1):
            lines.append(f"{i}. **[{sev_cn[f['severity']]}] {f['label']}** — {f['message']}")
    else:
        lines.append("未发现断档、重叠或逆序，交接链路完整。")
    lines.append("")

    if sample.get("description"):
        lines += ["## 样本备注", "", sample["description"], ""]

    return "\n".join(lines)


_SEVERITY_CN = {"error": "严重", "warning": "警告", "info": "提示"}
_STATUS_BADGE = {
    "pass": ("通过", "#168a4a"),
    "warning": ("通过（警告）", "#b26a00"),
    "fail": ("不通过", "#c62828"),
    "empty": ("无事件", "#666"),
}


def build_html(sample: dict[str, Any], result: dict[str, Any]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    badge_text, badge_color = _STATUS_BADGE[result["status"]]

    timeline_rows = []
    for i, e in enumerate(result["timeline"], 1):
        tag_html = "".join(
            f'<span class="tag sev-{f["severity"]}">{escape(f["label"])}</span>'
            for f in e["flags"]
        ) or '<span class="tag sev-ok">正常</span>'
        note = f'<div class="note">备注：{escape(e["note"])}</div>' if e.get("note") else ""
        timeline_rows.append(f"""
        <tr>
          <td>{i}</td>
          <td class="mono">{escape(e['occurred_at'])}</td>
          <td>{escape(e['from_party'])}</td>
          <td>→</td>
          <td>{escape(e['to_party'])}</td>
          <td>{escape(e.get('location') or '')}</td>
          <td>{e['entry_seq']}</td>
          <td>{tag_html}</td>
        </tr>""")
        if note:
            timeline_rows.append(f'<tr class="note-row"><td colspan="8">{note}</td></tr>')
    timeline_html = "\n".join(timeline_rows) or (
        '<tr><td colspan="8" class="empty">暂无交接事件</td></tr>'
    )

    if result["findings"]:
        findings_html = "\n".join(
            f'<li class="finding sev-{f["severity"]}">'
            f'<span class="tag sev-{f["severity"]}">'
            f'{_SEVERITY_CN[f["severity"]]} · {escape(f["label"])}</span>'
            f'{escape(f["message"])}</li>'
            for f in result["findings"]
        )
    else:
        findings_html = '<li class="ok">未发现断档、重叠或逆序，交接链路完整。</li>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>审计报告 - {escape(sample['code'])}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #f4f6f9; color: #1f2933;
         font: 15px/1.7 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }}
  .page {{ max-width: 960px; margin: 32px auto; background: #fff;
           border-radius: 12px; box-shadow: 0 2px 16px rgba(0,0,0,.08);
           padding: 40px 48px; }}
  h1 {{ margin: 0 0 4px; font-size: 26px; }}
  .sub {{ color: #667; margin-bottom: 24px; }}
  .badge {{ display: inline-block; padding: 4px 16px; border-radius: 999px;
            color: #fff; font-weight: 600; background: {badge_color}; }}
  .meta {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px;
           background: #f8fafc; border: 1px solid #e4e9f0; border-radius: 8px;
           padding: 16px 20px; margin: 20px 0; }}
  .meta div {{ color: #52606d; }}
  .meta b {{ color: #1f2933; font-weight: 600; }}
  h2 {{ font-size: 18px; margin: 28px 0 12px; padding-left: 10px;
        border-left: 4px solid #2c6fb0; }}
  .summary {{ white-space: pre-line; background: #f8fafc;
              border: 1px solid #e4e9f0; border-radius: 8px; padding: 14px 18px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th, td {{ border: 1px solid #e4e9f0; padding: 8px 10px; text-align: left; }}
  th {{ background: #f0f4f8; font-weight: 600; }}
  .mono {{ font-family: ui-monospace, Menlo, Consolas, monospace; }}
  .note-row td {{ background: #fafbfd; color: #667; font-size: 13px; }}
  .note {{ margin: 0; }}
  .empty {{ text-align: center; color: #999; padding: 24px; }}
  .tag {{ display: inline-block; padding: 1px 10px; border-radius: 999px;
          color: #fff; font-size: 12px; margin-right: 4px; }}
  .sev-error {{ background: #c62828; }}
  .sev-warning {{ background: #e08a00; }}
  .sev-info {{ background: #5b7fa6; }}
  .sev-ok {{ background: #2e9e5b; }}
  ul.findings {{ list-style: none; padding: 0; margin: 0; }}
  .finding {{ padding: 10px 14px; border-radius: 8px; margin-bottom: 8px;
              background: #fafbfd; border: 1px solid #e4e9f0; }}
  .finding .tag {{ margin-right: 8px; }}
  li.ok {{ color: #168a4a; }}
  .footer {{ margin-top: 32px; color: #99a; font-size: 12px; text-align: center; }}
  @media print {{
    body {{ background: #fff; }}
    .page {{ box-shadow: none; margin: 0; max-width: none; }}
  }}
</style>
</head>
<body>
<div class="page">
  <h1>样本交接链路审计报告</h1>
  <div class="sub">生成时间：{now}　<span class="badge">{badge_text}</span></div>

  <div class="meta">
    <div>样本编号：<b>{escape(sample['code'])}</b></div>
    <div>样本名称：<b>{escape(sample['name'])}</b></div>
    <div>时间跨度：<b>{escape(result['span'])}</b></div>
    <div>事件总数：<b>{result['total']}</b></div>
    <div>断档阈值：<b>{result['gap_hours']:g} 小时</b></div>
    <div>严重 / 警告 / 提示：<b>{result['counts']['error']} /
        {result['counts']['warning']} / {result['counts']['info']}</b></div>
  </div>

  <h2>审计结论</h2>
  <div class="summary">{escape(result['summary'])}</div>

  <h2>交接时间线（按发生时间排序）</h2>
  <table>
    <thead><tr>
      <th>#</th><th>发生时间</th><th>交出方</th><th></th><th>接收方</th>
      <th>地点</th><th>录入序号</th><th>标记</th>
    </tr></thead>
    <tbody>{timeline_html}</tbody>
  </table>

  <h2>冲突与异常清单</h2>
  <ul class="findings">{findings_html}</ul>

  <div class="footer">样本交接链路审计系统 · 本报告由系统自动生成</div>
</div>
</body>
</html>"""
