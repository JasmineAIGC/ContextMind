#!/usr/bin/env python3
"""
测试字体文件位置和加载
Test font file location and loading
"""

from pathlib import Path
import sys

def show_font_locations():
    """显示字体文件的推荐位置"""
    
    # 项目根目录
    project_root = Path(__file__).parent.parent
    
    # 首选位置：项目内
    project_font = project_root / 'resources' / 'fonts' / 'NotoSansCJKsc-Regular.otf'
    
    # 备选位置：用户目录
    user_font = Path.home() / '.fonts' / 'NotoSansCJKsc-Regular.otf'
    
    print("=" * 70)
    print("字体文件位置说明 (Font File Location Guide)")
    print("=" * 70)
    print()
    
    print("📁 首选位置 (Recommended - Project Directory):")
    print(f"   {project_font}")
    print(f"   存在: {'✓ 是' if project_font.exists() else '✗ 否'}")
    print()
    
    print("📁 备选位置 (Alternative - User Directory):")
    print(f"   {user_font}")
    print(f"   存在: {'✓ 是' if user_font.exists() else '✗ 否'}")
    print()
    
    if not project_font.exists() and not user_font.exists():
        print("⚠️  字体文件未找到！")
        print()
        print("请下载字体到首选位置:")
        print()
        print("  方法1 - 使用 wget:")
        print(f"    wget https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf \\")
        print(f"         -O {project_font}")
        print()
        print("  方法2 - 使用 curl:")
        print(f"    curl -L https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf \\")
        print(f"         -o {project_font}")
        print()
        print("  方法3 - 手动下载:")
        print("    访问: https://github.com/googlefonts/noto-cjk/tree/main/Sans/OTF/SimplifiedChinese")
        print(f"    下载后放置到: {project_font}")
        print()
        print("💡 提示: 如果不手动下载，程序会自动下载到用户目录")
    else:
        print("✓ 找到字体文件！")
        if project_font.exists():
            print(f"  使用项目字体: {project_font}")
            print(f"  文件大小: {project_font.stat().st_size / (1024*1024):.2f} MB")
        else:
            print(f"  使用用户字体: {user_font}")
            print(f"  文件大小: {user_font.stat().st_size / (1024*1024):.2f} MB")
    
    print()
    print("=" * 70)

if __name__ == '__main__':
    show_font_locations()
