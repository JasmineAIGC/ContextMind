#!/usr/bin/env python3
"""
检查 run_fnctod_transfertod.py 的版本

运行这个脚本来确认你正在使用哪个版本的 FnCTOD 评测脚本。
"""

import os
import sys
from pathlib import Path

def check_version():
    """检查脚本版本"""
    script_path = Path(__file__).parent / "run_fnctod_transfertod.py"
    
    print("=" * 80)
    print("🔍 FnCTOD 评测脚本版本检查工具")
    print("=" * 80)
    print()
    
    if not script_path.exists():
        print(f"❌ 错误: 找不到文件 {script_path}")
        return 1
    
    print(f"✅ 找到文件: {script_path}")
    print(f"文件大小: {script_path.stat().st_size} bytes")
    print()
    
    # 读取文件内容
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    print(f"文件行数: {len(lines)}")
    print()
    
    # 检查版本标识
    version_found = False
    for i, line in enumerate(lines[:30], 1):  # 只检查前30行
        if "VERSION:" in line or "版本标识" in line:
            print(f"✅ 找到版本标识 (第{i}行):")
            print(f"   {line.strip()}")
            version_found = True
        if "2024-02-10" in line and i < 30:
            print(f"✅ 找到版本日期 (第{i}行):")
            print(f"   {line.strip()}")
            version_found = True
    
    print()
    
    # 检查关键函数
    if "class FnCTODTransferTODTest" in content:
        print("✅ 包含 FnCTODTransferTODTest 类 (新版本)")
    else:
        print("❌ 缺少 FnCTODTransferTODTest 类 (旧版本)")
    
    if "async def test_dialogue" in content:
        print("✅ 包含 test_dialogue 异步方法 (新版本)")
    else:
        print("❌ 缺少 test_dialogue 方法 (旧版本)")
    
    if "脚本版本: 2024-02-10" in content:
        print("✅ 包含版本输出语句 (新版本)")
    else:
        print("❌ 缺少版本输出语句 (旧版本)")
    
    if "📊 FnCTOD 测试指标汇总" in content:
        print("✅ 包含详细指标汇总 (新版本)")
    else:
        print("❌ 缺少指标汇总功能 (旧版本)")
    
    print()
    print("=" * 80)
    
    # 判断版本
    if len(lines) > 400 and "FnCTODTransferTODTest" in content:
        print("✅ 结论: 你正在使用 NEW VERSION (完整评测实现)")
        print()
        print("这个版本包含:")
        print("  - 完整的 FnCTOD tracker 集成")
        print("  - 详细的指标计算和报告")
        print("  - 意图评测功能")
        print("  - 错误处理和诊断输出")
        print()
        print("如果运行时看到的是旧版本输出，请:")
        print("  1. 清除 Python 缓存: find . -type d -name '__pycache__' -exec rm -rf {} +")
        print("  2. 确认正在运行正确的文件路径")
        print("  3. 检查是否在正确的 git 分支")
        return 0
    else:
        print("❌ 结论: 你正在使用 OLD VERSION (空运行版本)")
        print()
        print("这个旧版本只会输出:")
        print("  === FnCTOD on TransferTOD 评测 ===")
        print("  找到 X 个对话")
        print("  评测完成！")
        print()
        print("请更新到新版本:")
        print("  1. git pull origin <your-branch>")
        print("  2. 或者手动下载最新的 run_fnctod_transfertod.py")
        return 1

if __name__ == "__main__":
    sys.exit(check_version())
