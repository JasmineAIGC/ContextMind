#!/usr/bin/env python3
"""
DST模式 - RiSAWOZ数据集评测脚本（待实现）

使用RiSAWOZ数据集测试DialogueStateTracker的槽位提取能力。

待实现功能：
1. RiSAWOZ数据加载
2. DST算法评测
3. 指标计算和报告生成

使用方式（待实现后）:
    python benchmark/runners/run_dst_risawoz.py
    python benchmark/runners/run_dst_risawoz.py --domain 酒店 --limit 10
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    """主函数"""
    print("=" * 70)
    print("DST模式 - RiSAWOZ数据集评测")
    print("=" * 70)
    print()
    print("⚠️  此功能尚未实现")
    print()
    print("待实现内容：")
    print("  1. RiSAWOZ数据集适配器")
    print("  2. DST-RiSAWOZ适配代码")
    print("  3. 评测流程和指标计算")
    print()
    print("请等待后续版本更新。")
    print("=" * 70)
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
