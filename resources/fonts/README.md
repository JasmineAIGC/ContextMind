# 字体文件说明 (Font Files Documentation)

## NotoSansCJKsc-Regular.otf 存放位置

本目录用于存放项目所需的字体文件，特别是用于中文显示的 Noto Sans CJK 字体。

### 推荐放置位置

**首选位置（项目内）：**
```
resources/fonts/NotoSansCJKsc-Regular.otf
```

**备选位置（用户目录）：**
```
~/.fonts/NotoSansCJKsc-Regular.otf
```

### 手动下载安装

如果您想手动下载字体而不是让程序自动下载，请按以下步骤操作：

1. **下载字体文件：**
   ```bash
   wget https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf \
        -O resources/fonts/NotoSansCJKsc-Regular.otf
   ```

2. **或者使用 curl：**
   ```bash
   curl -L https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf \
        -o resources/fonts/NotoSansCJKsc-Regular.otf
   ```

3. **或者直接从浏览器下载：**
   - 访问：https://github.com/googlefonts/noto-cjk/tree/main/Sans/OTF/SimplifiedChinese
   - 下载 `NotoSansCJKsc-Regular.otf` 文件
   - 将文件放置到 `resources/fonts/` 目录下

### 自动下载

如果您没有手动下载字体，程序会自动执行以下操作：

1. 检查 `resources/fonts/NotoSansCJKsc-Regular.otf` 是否存在
2. 如果不存在，检查 `~/.fonts/NotoSansCJKsc-Regular.otf` 是否存在
3. 如果都不存在，自动从 GitHub 下载到 `~/.fonts/` 目录

### 为什么使用 Noto Sans CJK？

- **开源免费：** Google 和 Adobe 联合开发的开源字体
- **中文支持完整：** 支持简体中文、繁体中文、日文、韩文
- **高质量：** 专业设计，显示效果优秀
- **跨平台：** 在 Linux、macOS、Windows 上都能正常使用

### 故障排除

**问题：中文显示为方框或乱码**
- 检查字体文件是否正确下载（文件大小约 16-20 MB）
- 尝试手动下载字体到推荐位置
- 检查文件权限：`chmod 644 resources/fonts/NotoSansCJKsc-Regular.otf`

**问题：无法自动下载**
- 检查网络连接
- 检查是否能访问 GitHub
- 手动下载字体文件到指定位置

### 其他字体选项

如果您的系统已经安装了其他中文字体，程序会尝试使用以下字体（按优先级）：
1. Noto Sans CJK SC (首选)
2. Noto Sans CJK JP
3. WenQuanYi Micro Hei (文泉驿微米黑)
4. SimHei (黑体)
5. DejaVu Sans
6. Arial Unicode MS

### 注意事项

- 字体文件较大（约 16-20 MB），已在 `.gitignore` 中排除，不会提交到 Git 仓库
- 建议在首次运行前手动下载，避免运行时下载延迟
- 字体文件仅用于生成混淆矩阵等可视化图表时的中文显示
