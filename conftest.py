"""
pytest conftest — 将项目根目录加入 sys.path，使 `import contextmind` 在未安装时也可用。
"""
import sys
import os

# 将仓库根目录插入 sys.path 首位，使 `contextmind` 包可直接导入
sys.path.insert(0, os.path.dirname(__file__))
