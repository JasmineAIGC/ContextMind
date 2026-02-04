"""
ContextMind 测试模块

包含 DST 和 Evolve 两种模式的测试代码
测试数据来自 data/duihua.md 中的 7 通电话对话

目录结构:
    tests/
    ├── __init__.py           # 本文件
    ├── dialogues/            # 对话文本文件
    │   ├── dialogue_1.txt
    │   ├── dialogue_2.txt
    │   └── ...
    ├── labels/               # 标签文件
    │   ├── dialogue_1_dst.json
    │   ├── dialogue_1_evolve.json
    │   └── ...
    ├── test_dst_mode.py      # DST 模式测试
    └── test_evolve_mode.py   # Evolve 模式测试

使用方式:
    # 运行所有测试
    python -m pytest tests/ -v
    
    # 运行 DST 测试
    python -m pytest tests/test_dst_mode.py -v
    python tests/test_dst_mode.py
    
    # 运行 Evolve 测试
    python -m pytest tests/test_evolve_mode.py -v
    python tests/test_evolve_mode.py
"""

__version__ = "0.2.1"
