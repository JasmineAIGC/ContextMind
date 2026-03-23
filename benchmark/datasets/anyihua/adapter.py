"""
安逸花（AnyiHua）数据集适配器

从 resources/data/chat_test_100.json 加载安逸花外呼对话，
并从 data/anyihua_sgd/schema.json 加载 SGD 格式 schema。

数据说明：
    - chat_test_100.json：100 条安逸花外呼真实对话，每条包含用户信息、
      对话历史（坐席/用户轮次交替）和最终坐席回复。
    - anyihua_sgd/schema.json：由知识提取流程生成的 SGD 格式服务 schema，
      包含 22 个意图和 24 个槽位，覆盖安逸花外呼业务全流程。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："

# 说话人标签常量
_SPEAKER_AGENT = "坐席"
_SPEAKER_USER = "用户"
_SPEAKER_UNKNOWN = "未知"


@dataclass
class AnyihuaTurn:
    """单个对话轮次。"""

    turn_idx: int
    speaker: str      # "坐席" | "用户" | "未知"
    utterance: str


@dataclass
class AnyihuaDialogue:
    """完整安逸花对话实例。"""

    session_id: str
    user_info_str: str            # 原始用户信息字符串（"#" 分隔）
    turns: List[AnyihuaTurn]
    agent_reply: str              # 最终坐席参考回复
    raw_session: Dict[str, Any]   # 完整原始记录（供 build_generation_engine 使用）

    @property
    def user_turns(self) -> List[AnyihuaTurn]:
        """仅返回用户侧轮次。"""
        return [t for t in self.turns if t.speaker == _SPEAKER_USER]

    @property
    def agent_turns(self) -> List[AnyihuaTurn]:
        """仅返回坐席侧轮次。"""
        return [t for t in self.turns if t.speaker == _SPEAKER_AGENT]


class AnyihuaSGDAdapter:
    """
    安逸花 SGD 数据集适配器。

    负责：
    1. 加载 ``data/anyihua_sgd/schema.json``（SGD 格式，供 PyTOD ServiceSchema 构建）
    2. 加载 ``resources/data/chat_test_100.json``（对话数据，100 条外呼会话）

    用法示例::

        adapter = AnyihuaSGDAdapter()
        schema_raw = adapter.load_schema()          # -> List[dict]（SGD 格式）
        dialogues  = adapter.load_dialogues(limit=10)
        for dlg in dialogues:
            for turn in dlg.user_turns:
                print(turn.utterance)
    """

    def __init__(
        self,
        data_root: str = ".",
        schema_path: str = "data/anyihua_sgd/schema.json",
        dialogues_path: str = "resources/data/chat_test_100.json",
    ) -> None:
        """
        初始化适配器。

        Args:
            data_root:      项目根目录路径（其余路径相对于此）
            schema_path:    SGD schema 文件相对路径
            dialogues_path: 对话数据文件相对路径
        """
        root = Path(data_root)
        self.schema_file = root / schema_path
        self.dialogues_file = root / dialogues_path

        self._schema_raw: Optional[List[Dict[str, Any]]] = None
        self._dialogues: Optional[List[AnyihuaDialogue]] = None

    # ---------------------------------------------------------------------- #
    # Schema
    # ---------------------------------------------------------------------- #

    def load_schema(self) -> List[Dict[str, Any]]:
        """
        加载 data/anyihua_sgd/schema.json（SGD 格式）。

        返回顶层数组（每个元素为一个服务定义），通常只含一个服务 "AnYiHua_1"。
        """
        if self._schema_raw is None:
            with open(self.schema_file, encoding="utf-8") as fh:
                self._schema_raw = json.load(fh)
        return self._schema_raw

    def get_service_schema(self, service_name: str = "") -> Dict[str, Any]:
        """
        按服务名称返回单个服务 schema 字典。

        Args:
            service_name: 服务名称，为空时返回第一个服务

        Returns:
            服务 schema 字典
        """
        schemas = self.load_schema()
        if not service_name:
            return schemas[0]
        for svc in schemas:
            if svc.get("service_name") == service_name:
                return svc
        raise KeyError(f"服务 '{service_name}' 未在 schema 中找到")

    # ---------------------------------------------------------------------- #
    # Dialogues
    # ---------------------------------------------------------------------- #

    def load_dialogues(self, limit: int = -1) -> List[AnyihuaDialogue]:
        """
        加载对话数据。

        Args:
            limit: 最大加载条数，-1 表示全部（默认 100 条）

        Returns:
            AnyihuaDialogue 列表
        """
        if self._dialogues is None:
            with open(self.dialogues_file, encoding="utf-8") as fh:
                sessions: List[Dict[str, Any]] = json.load(fh)
            self._dialogues = [self._parse_session(s) for s in sessions]

        result = self._dialogues
        if limit > 0:
            result = result[:limit]
        return result

    def _parse_session(self, session: Dict[str, Any]) -> AnyihuaDialogue:
        """将单条 chat_test_100 记录转换为 AnyihuaDialogue。"""
        history: List[str] = session.get("对话历史", [])
        turns: List[AnyihuaTurn] = []

        for idx, line in enumerate(history):
            if line.startswith(_AGENT_PREFIX):
                speaker = _SPEAKER_AGENT
                utterance = line[len(_AGENT_PREFIX):]
            elif line.startswith(_USER_PREFIX):
                speaker = _SPEAKER_USER
                utterance = line[len(_USER_PREFIX):]
            else:
                speaker = _SPEAKER_UNKNOWN
                utterance = line
            turns.append(AnyihuaTurn(turn_idx=idx, speaker=speaker, utterance=utterance))

        return AnyihuaDialogue(
            session_id=session.get("session_id", ""),
            user_info_str=session.get("用户信息", ""),
            turns=turns,
            agent_reply=session.get("坐席回复", ""),
            raw_session=session,
        )
