"""
gui/report_viewer.py — 日报 Markdown 渲染器
============================================
将 .md 文件内容转为带样式的 HTML，在 QTextBrowser 中显示。
"""

# Markdown CSS 样式（类 Notion 风格）
REPORT_CSS = """
<style>
  body {
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 14px;
    line-height: 1.7;
    color: #2c2c2c;
    background: #fafafa;
    padding: 24px 32px;
    margin: 0;
  }
  h1 {
    font-size: 20px;
    font-weight: 700;
    color: #1a1a1a;
    border-bottom: 2px solid #e0e0e0;
    padding-bottom: 8px;
    margin-top: 0;
    margin-bottom: 16px;
  }
  h2 {
    font-size: 16px;
    font-weight: 600;
    color: #333;
    margin-top: 20px;
    margin-bottom: 8px;
  }
  p {
    margin: 8px 0;
    color: #444;
  }
  ul, ol {
    margin: 8px 0;
    padding-left: 24px;
    color: #444;
  }
  li {
    margin: 4px 0;
  }
  strong {
    color: #1a1a1a;
    font-weight: 600;
  }
  code {
    background: #f0f0f0;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: "Fira Code", "Consolas", monospace;
    font-size: 13px;
  }
  pre {
    background: #f5f5f5;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 12px 16px;
    overflow-x: auto;
  }
  pre code {
    background: none;
    padding: 0;
    border: none;
  }
  blockquote {
    border-left: 3px solid #c0c0c0;
    margin: 12px 0;
    padding: 4px 12px;
    color: #666;
    background: #f9f9f9;
    border-radius: 0 4px 4px 0;
  }
  hr {
    border: none;
    border-top: 1px solid #e0e0e0;
    margin: 20px 0;
  }
  a {
    color: #3b82f6;
    text-decoration: none;
  }
  a:hover {
    text-decoration: underline;
  }
  /* 空状态 */
  .empty {
    text-align: center;
    color: #999;
    font-size: 15px;
    margin-top: 60px;
  }
  .empty-icon {
    font-size: 48px;
    display: block;
    margin-bottom: 12px;
  }
</style>
"""


def md_to_html(md_content: str) -> str:
    """
    将 Markdown 文本转为 HTML。
    仅处理最常见的元素：标题、列表、粗体、代码、引用、分割线、emoji。
    """
    lines = md_content.splitlines()
    in_code_block = False
    in_ul = False
    html_lines = []
    buffer = []

    def flush_inline():
        """处理行内内容"""
        if not buffer:
            return ""
        text = "".join(buffer)
        buffer.clear()
        # 粗体 **text**
        import re
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # 行内代码 `code`
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        # emoji 保持原样
        return text

    for line in lines:
        stripped = line.strip()

        # 代码块
        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                html_lines.append("<pre><code>")
            else:
                in_code_block = False
                html_lines.append("</code></pre>")
            continue

        if in_code_block:
            html_lines.append(escape_html(stripped))
            continue

        # 标题
        if stripped.startswith("# "):
            html_lines.append(f"<h1>{flush_inline() or stripped[2:]}</h1>")
            continue
        if stripped.startswith("## "):
            html_lines.append(f"<h2>{flush_inline() or stripped[3:]}</h2>")
            continue
        if stripped.startswith("### "):
            html_lines.append(f"<h3>{flush_inline() or stripped[4:]}</h3>")
            continue

        # 无序列表
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"<li>{flush_inline() or stripped[2:]}</li>")
            continue
        else:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False

        # 分割线
        if stripped in ("---", "***", "___"):
            html_lines.append("<hr>")
            continue

        # 引用
        if stripped.startswith(">"):
            html_lines.append(f"<blockquote>{flush_inline() or stripped[1:].strip()}</blockquote>")
            continue

        # 空行
        if not stripped:
            html_lines.append("<br>")
            buffer.clear()
            continue

        # 普通段落
        buffer.append(escape_html(stripped) + " ")

    if buffer:
        html_lines.append(f"<p>{flush_inline()}</p>")
    if in_ul:
        html_lines.append("</ul>")

    return "".join(html_lines)


def escape_html(text: str) -> str:
    """简单的 HTML 转义"""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def render_report(md_content: str) -> str:
    """生成完整的 HTML 页面"""
    body = md_to_html(md_content) if md_content else ""
    if not body:
        body = (
            '<div class="empty">'
            '<span class="empty-icon">📭</span>'
            '暂无日报内容<br>'
            '<small>开始监测并等待日报生成</small>'
            '</div>'
        )
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'>{REPORT_CSS}</head><body>{body}</body></html>"
