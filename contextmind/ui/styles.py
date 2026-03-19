"""
ContextMind UI — 全局 CSS 样式

从 components.py 中提取，便于独立维护和复用。
"""

# 当前版本号，用于 UI 页脚显示
APP_VERSION = "0.2.1"

CUSTOM_CSS = """
/* 全局样式 */
.gradio-container {
    max-width: 1200px !important;
    margin: 0 auto !important;
}

/* 聊天区域 */
.chatbot {
    border-radius: 8px !important;
}

/* JSON显示区 */
.json-display {
    font-family: 'Consolas', 'Monaco', monospace !important;
    font-size: 0.9em !important;
}

/* Footer样式 */
.footer {
    text-align: center !important;
    color: #666 !important;
    font-size: 0.85em !important;
    margin-top: 20px !important;
    padding: 15px !important;
    border-top: 1px solid #e5e7eb !important;
}
"""
