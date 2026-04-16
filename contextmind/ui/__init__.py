"""
ContextMind UI 模块

子模块:
    styles     — CSS 样式常量及版本号
    components — Gradio 布局和事件绑定（需要安装 gradio）
"""

from .styles import CUSTOM_CSS, APP_VERSION

__all__ = [
    "CUSTOM_CSS",
    "APP_VERSION",
    "create_layout",
    "bind_events",
    "create_gradio_ui",
    "format_state_as_json",
]


def __getattr__(name):
    """按需导入 Gradio 相关组件（避免在未安装 gradio 时导入失败）。"""
    _gradio_exports = {"create_layout", "bind_events", "create_gradio_ui", "format_state_as_json"}
    if name in _gradio_exports:
        from .components import create_layout, bind_events, create_gradio_ui, format_state_as_json
        mapping = {
            "create_layout": create_layout,
            "bind_events": bind_events,
            "create_gradio_ui": create_gradio_ui,
            "format_state_as_json": format_state_as_json,
        }
        return mapping[name]
    raise AttributeError(f"module 'contextmind.ui' has no attribute {name!r}")
