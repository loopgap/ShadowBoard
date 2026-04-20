"""UI component data and styles extracted from web_app.py."""

from __future__ import annotations

from typing import List

from src.core.templates import PROVIDERS, TEMPLATE_LABEL_TO_KEY

# Provider labels for dropdown
PROVIDER_LABELS: List[str] = [v["label"] for v in PROVIDERS.values()]

# History filter options
HISTORY_FILTERS: List[str] = ["全部", "仅成功", "仅失败"]

# Template labels for dropdowns
TEMPLATE_LABELS: List[str] = list(TEMPLATE_LABEL_TO_KEY.keys())


CUSTOM_CSS = """
:root { color-scheme: light; }
footer, #footer, .gradio-container .footer, [data-testid='footer'] { display: none !important; }

.gradio-container {
  --app-surface: #ffffff;
  --app-surface-muted: #f5f7fb;
  --app-text: #111827;
  --app-border: #dbe2ee;
  --body-background-fill: #f5f7fb;
  --block-background-fill: #ffffff;
  --block-border-color: #dbe2ee;
  --block-label-text-color: #111827;
  --body-text-color: #111827;
  --body-text-color-subdued: #4b5563;
  --input-background-fill: #ffffff;
  --input-border-color: #cbd5e1;
  --input-placeholder-color: #6b7280;
  --color-accent: #1a73e8;
  --color-accent-soft: #e8f0fe;
  font-family: "Google Sans", "HarmonyOS Sans SC", "MiSans", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  background:
    radial-gradient(1000px 300px at 8% -8%, #e8f0fe 0%, rgba(232,240,254,0) 65%),
    radial-gradient(800px 260px at 92% -18%, #f3f8ff 0%, rgba(243,248,255,0) 65%),
    #f7f9fc;
  color: #111827;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  font-size: 15px;
  line-height: 1.65;
}

.hero {
  border: 1px solid #d2e3fc;
  border-radius: 22px;
  background: #ffffff;
  padding: 22px;
  margin-bottom: 14px;
  box-shadow: 0 10px 28px rgba(26,115,232,0.08);
}
.hero-title { font-size: 34px; font-weight: 800; color: #202124; margin-bottom: 8px; }
.hero-sub { font-size: 16px; color: #4b5563; margin-bottom: 12px; }
.hero-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.hero-chip {
  display: inline-block;
  border: 1px solid #d2e3fc;
  border-radius: 999px;
  padding: 6px 12px;
  background: #eef4ff;
  color: #174ea6;
  font-size: 13px;
  font-weight: 600;
}

.section-card {
  border: 1px solid var(--app-border);
  border-radius: 18px;
  background: var(--app-surface);
  box-shadow: 0 4px 14px rgba(60,64,67,0.07);
  padding: 14px;
  margin-top: 8px;
}

.section-card,
.section-card * {
  color: #111827 !important;
}

.section-card .prose,
.section-card .prose * {
  background: transparent !important;
}

.section-title {
  font-size: 18px;
  font-weight: 700;
  color: #202124;
  margin-bottom: 10px;
}

.gradio-container .tabs {
  background: transparent !important;
}

.gradio-container .tabs button {
  color: #374151 !important;
  font-weight: 600 !important;
  border-bottom: 2px solid transparent !important;
  background: #f5f7fb !important;
  border-radius: 10px 10px 0 0 !important;
}

.gradio-container .tabs button:hover {
  color: #174ea6 !important;
  background: #eef4ff !important;
}

.gradio-container .tabs button[aria-selected='true'] {
  color: #174ea6 !important;
  font-weight: 700 !important;
  border-bottom: 2px solid #1a73e8 !important;
  background: #ffffff !important;
  box-shadow: inset 0 -1px 0 #1a73e8 !important;
}

.gradio-container textarea,
.gradio-container input,
.gradio-container .wrap,
.gradio-container .block {
  color: #202124 !important;
}

.gradio-container textarea,
.gradio-container input {
  background: #ffffff !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 10px !important;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04) !important;
}

/* Input validation border colors */
.border-valid {
  border-color: #22c55e !important;
  border-width: 2px !important;
}

.border-warning {
  border-color: #f59e0b !important;
  border-width: 2px !important;
}

.border-error {
  border-color: #ef4444 !important;
  border-width: 2px !important;
}

.border-empty {
  border-color: #94a3b8 !important;
}

.gradio-container .prose,
.gradio-container .prose * {
  color: #202124 !important;
}

.gradio-container .prose h1,
.gradio-container .prose h2,
.gradio-container .prose h3,
.gradio-container .prose h4 {
  color: #1f1f1f !important;
}

.gradio-container .prose p,
.gradio-container .prose li,
.gradio-container .prose strong {
  color: #111827 !important;
  line-height: 1.75 !important;
  font-size: 15px !important;
}

.gradio-container .prose code,
.gradio-container .prose pre {
  background: #f6f8fc !important;
  color: #1f1f1f !important;
  border: 1px solid #e3e8f0 !important;
}

.gradio-container [class*='markdown'],
.gradio-container [class*='markdown'] > div {
  background: #ffffff !important;
  border-radius: 10px !important;
}

.action-primary button {
  background: #1a73e8 !important;
  border-color: #1a73e8 !important;
  color: #ffffff !important;
  font-weight: 700 !important;
}
.action-primary button:hover { background: #1967d2 !important; }

.action-secondary button {
  background: #ffffff !important;
  border-color: #d2e3fc !important;
  color: #174ea6 !important;
  font-weight: 700 !important;
}

.provider-card textarea,
.provider-card input {
  background: #f7faff !important;
}

.cn-quick-actions {
  margin-top: 16px;
  margin-bottom: 8px;
  border: 1px solid #d2e3fc;
  border-radius: 16px;
  padding: 14px;
  background: #eef4ff;
}
.cn-quick-title { font-size: 18px; font-weight: 700; color: #174ea6; margin-bottom: 10px; }
.cn-quick-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.cn-quick-btn {
  display: block;
  text-align: center;
  text-decoration: none !important;
  font-size: 15px;
  font-weight: 700;
  color: #ffffff !important;
  padding: 12px 10px;
  border-radius: 10px;
  border: 1px solid #1a73e8;
  background: #1a73e8;
}
.cn-quick-btn:hover { background: #1967d2; }
.cn-quick-tip { margin-top: 10px; color: #3c4043; font-size: 13px; }

.gradio-container label,
.gradio-container .label-wrap,
.gradio-container .svelte-1ipelgc {
  color: #111827 !important;
}

/* History table readability in light mode */
#history-table,
#history-table > div,
#history-table .table-container,
#history-table [data-testid='dataframe'],
#history-table [data-testid='dataframe'] * {
  background: var(--app-surface) !important;
  color: var(--app-text) !important;
  border-color: var(--app-border) !important;
}

#history-table table,
#history-table thead,
#history-table tbody,
#history-table tr,
#history-table th,
#history-table td {
  background: #ffffff !important;
  color: #111827 !important;
  border-color: #dbe2ee !important;
}

#history-table th {
  font-weight: 700 !important;
}

#history-table .table-wrap,
#history-table .table-wrap * {
  color: #111827 !important;
  border-color: #dbe2ee !important;
}

#history-table [role='grid'],
#history-table [role='row'],
#history-table [role='gridcell'],
#history-table [role='columnheader'] {
  background: var(--app-surface) !important;
  color: var(--app-text) !important;
}

#history-table td *,
#history-table th * {
  color: var(--app-text) !important;
  background: transparent !important;
}

#history-filter,
#history-filter * {
  color: #111827 !important;
}

@media (max-width: 900px) {
  .hero-title { font-size: 26px; }
  .cn-quick-grid { grid-template-columns: 1fr; }
}

@media (prefers-color-scheme: dark) {
  :root { color-scheme: dark; }
  .gradio-container {
    --app-surface: #111827;
    --app-surface-muted: #0b1220;
    --app-text: #e5e7eb;
    --app-border: #334155;
    --body-background-fill: #0f172a;
    --block-background-fill: #111827;
    --body-text-color: #e5e7eb;
    --body-text-color-subdued: #9ca3af;
    --input-background-fill: #0b1220;
    --input-border-color: #334155;
    --block-border-color: #334155;
    background:
      radial-gradient(1000px 300px at 8% -8%, #1e3a8a 0%, rgba(30,58,138,0) 65%),
      radial-gradient(800px 260px at 92% -18%, #1f2937 0%, rgba(31,41,55,0) 65%),
      #0b1220 !important;
    color: #e5e7eb !important;
  }

  .hero,
  .section-card,
  .cn-quick-actions {
    background: #111827 !important;
    border-color: #334155 !important;
    color: #e5e7eb !important;
  }

  .hero-title,
  .section-title,
  .gradio-container .prose,
  .gradio-container .prose *,
  .section-card,
  .section-card * {
    color: #e5e7eb !important;
  }

  .hero-sub,
  .cn-quick-tip {
    color: #cbd5e1 !important;
  }

  .gradio-container [class*='markdown'],
  .gradio-container [class*='markdown'] > div {
    background: #111827 !important;
    color: #e5e7eb !important;
  }

  .action-secondary button {
    background: #0b1220 !important;
    color: #93c5fd !important;
    border-color: #334155 !important;
  }

  .gradio-container textarea,
  .gradio-container input {
    background: #0b1220 !important;
    color: #e5e7eb !important;
    border-color: #334155 !important;
  }

  .gradio-container .tabs button {
    background: #0b1220 !important;
    color: #cbd5e1 !important;
  }

  .gradio-container .tabs button[aria-selected='true'] {
    background: #111827 !important;
    color: #93c5fd !important;
    border-bottom-color: #60a5fa !important;
  }

  /* History table readability in dark mode */
  #history-table table,
  #history-table thead,
  #history-table tbody,
  #history-table tr,
  #history-table th,
  #history-table td {
    background: #0b1220 !important;
    color: #e5e7eb !important;
    border-color: #334155 !important;
  }

  #history-table .table-wrap,
  #history-table .table-wrap *,
  #history-table [role='grid'],
  #history-table [role='row'],
  #history-table [role='gridcell'],
  #history-table [role='columnheader'] {
    background: #0b1220 !important;
    color: #e5e7eb !important;
    border-color: #334155 !important;
  }

  #history-table td *,
  #history-table th * {
    color: #e5e7eb !important;
    background: transparent !important;
  }

  #history-filter,
  #history-filter * {
    color: #e5e7eb !important;
  }
}
"""


def get_hero_html() -> str:
    return """
<div class='hero'>
  <div class='hero-title'>网页 AI 半自动助手</div>
  <div class='hero-sub'>现代化配色 多平台模型入口 引导式流程与可审计执行</div>
  <div class='hero-chips'>
    <span class='hero-chip'>多平台适配</span>
    <span class='hero-chip'>自动重试和错误日志</span>
    <span class='hero-chip'>新手引导和一键准备</span>
  </div>
</div>
""".strip()


def get_faq_markdown() -> str:
    return """
<div class='section-title'>常见问题</div>
1 登录后仍失败 先点击 登录完成检查 再点击 执行冒烟测试
2 页面元素找不到 在平台与参数把发送方式切到 点击按钮发送
3 长文本效果差 建议分段执行 每段三千字以内
4 出现验证码 请在浏览器手动完成后重试
""".strip()


def get_quick_actions_html() -> str:
    return """
<div class='cn-quick-actions'>
  <div class='cn-quick-title'>常用功能</div>
  <div class='cn-quick-grid'>
    <a class='cn-quick-btn' href='javascript:window.scrollTo({top:0,behavior:"smooth"})'>返回顶部</a>
    <a class='cn-quick-btn' href='https://www.gradio.app/docs' target='_blank'>框架说明</a>
    <a class='cn-quick-btn' href='https://platform.openai.com/docs' target='_blank'>开发参考</a>
  </div>
  <div class='cn-quick-tip'>接口文档功能已内置在帮助文档页 可直接刷新和导出</div>
</div>
""".strip()
