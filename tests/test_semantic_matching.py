#!/usr/bin/env python3
"""
测试语义embedding匹配功能
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from contextmind.infra.embedding import get_embedding_client, calculate_embedding_similarity

def test_semantic_matching():
    """测试语义匹配功能"""
    
    print("=" * 70)
    print("测试语义Embedding匹配功能")
    print("=" * 70)
    
    # 获取embedding客户端
    client = get_embedding_client()
    
    if not client or not client.embedding_supported:
        print("❌ Embedding客户端不可用")
        print("\n请配置embedding环境：")
        print("方式1 - 本地模型:")
        print("  export EMBEDDING_MODEL_PATH=/path/to/bge-large-zh-v1.5")
        print("  pip install sentence-transformers")
        print("\n方式2 - API:")
        print("  export EMBEDDING_MODEL=bge-large-zh-v1.5")
        print("  export EMBEDDING_BASE_URL=http://localhost:8001/v1")
        print("  export EMBEDDING_API_KEY=EMPTY")
        return
    
    print(f"✅ Embedding客户端初始化成功")
    print(f"   配置: {client.config.model if client.config else 'N/A'}")
    print(f"   模式: {'本地' if client.config and client.config.use_local else 'API'}")
    
    # 测试用例：语义相似但字符串不同的值对
    test_cases = [
        ("偏贵", "贵点", True, "价格相关，应该匹配"),
        ("周庄古镇", "周庄", True, "同一地点，应该匹配"),
        ("适合朋友游玩", "朋友出游", True, "相同含义，应该匹配"),
        ("昆山", "上海", False, "不同地点，不应该匹配"),
        ("便宜", "昂贵", False, "相反含义，不应该匹配"),
    ]
    
    print("\n" + "=" * 70)
    print("测试用例")
    print("=" * 70)
    
    threshold = 0.85
    passed = 0
    failed = 0
    
    for value1, value2, should_match, description in test_cases:
        print(f"\n【测试】{description}")
        print(f"  值1: '{value1}'")
        print(f"  值2: '{value2}'")
        print(f"  预期: {'匹配' if should_match else '不匹配'}")
        
        # 生成embedding
        emb1 = client.generate_embedding(value1)
        emb2 = client.generate_embedding(value2)
        
        if not emb1 or not emb2:
            print(f"  ❌ Embedding生成失败")
            failed += 1
            continue
        
        # 计算相似度
        similarity, success = calculate_embedding_similarity(emb1, emb2)
        
        if not success:
            print(f"  ❌ 相似度计算失败")
            failed += 1
            continue
        
        is_match = similarity >= threshold
        result = "✅" if is_match == should_match else "❌"
        
        print(f"  相似度: {similarity:.4f}")
        print(f"  阈值: {threshold}")
        print(f"  结果: {'匹配' if is_match else '不匹配'}")
        print(f"  {result} {'通过' if is_match == should_match else '失败'}")
        
        if is_match == should_match:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"测试结果: {passed} 通过, {failed} 失败 (总共 {len(test_cases)} 个)")
    print("=" * 70)
    
    if failed == 0:
        print("✅ 所有测试通过！")
    else:
        print(f"⚠️  有 {failed} 个测试失败")

if __name__ == "__main__":
    test_semantic_matching()
