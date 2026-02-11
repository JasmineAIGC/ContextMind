# RiSAWOZ 数据集设置指南

## 快速回答

**用户问题**: RiSAWOZ 数据集都是zip 文件，我解压到原路径，代码里的访问路径需要特殊处理吗？或者我需要把数据结构做什么处理？

**答案**: ✅ **不需要特殊处理！**

只需确保解压后的3个JSON文件在同一目录即可：

```
./data/RiSAWOZ/
├── train.json
├── val.json
└── test.json
```

## 快速开始（3步完成）

### 步骤1: 创建目录

```bash
mkdir -p ./data/RiSAWOZ
```

### 步骤2: 解压文件

```bash
# 假设你已经下载了 RiSAWOZ 数据集的ZIP文件
# 解压到目标目录
unzip train.zip -d ./data/RiSAWOZ/
unzip val.zip -d ./data/RiSAWOZ/
unzip test.zip -d ./data/RiSAWOZ/

# 或者如果是单个ZIP包含所有文件
unzip RiSAWOZ.zip -d ./data/RiSAWOZ/
```

### 步骤3: 验证

```bash
ls ./data/RiSAWOZ/
# 应该看到: train.json  val.json  test.json
```

✅ **完成！** 现在可以运行评测了：

```bash
python benchmark/run_dst_risawoz.py
```

## 详细说明

### 标准目录结构

代码期望的目录结构非常简单：

```
./data/RiSAWOZ/          ← 数据集根目录（默认）
├── train.json           ← 训练集数据
├── val.json             ← 验证集数据
└── test.json            ← 测试集数据
```

**关键点**:
- ✅ 3个JSON文件必须在同一目录下
- ✅ 文件名必须是 `train.json`, `val.json`, `test.json`
- ✅ 不需要子目录
- ✅ 不需要其他额外文件

### 为什么这么简单？

查看代码实现（`adapter.py` 第80行）：

```python
file_path = self.data_root / f"{split}.json"
```

代码只是简单地在 `data_root` 目录下查找 `{split}.json` 文件，不涉及复杂的子目录结构。

## 下载和解压详细步骤

### 1. 下载 RiSAWOZ 数据集

从官方 GitHub 仓库下载：
- 仓库地址: https://github.com/terryqj0107/RiSAWOZ
- 数据文件通常在 `data/` 目录下

```bash
# 克隆仓库（如果还没有）
git clone https://github.com/terryqj0107/RiSAWOZ.git

# 或者直接下载ZIP文件
wget https://github.com/terryqj0107/RiSAWOZ/archive/refs/heads/master.zip
```

### 2. 解压文件

#### 情况A: 如果是单个ZIP包含所有数据

```bash
# 解压
unzip RiSAWOZ-master.zip

# 移动JSON文件到正确位置
mkdir -p ./data/RiSAWOZ
cp RiSAWOZ-master/data/*.json ./data/RiSAWOZ/

# 验证
ls ./data/RiSAWOZ/
# 应该看到: train.json  val.json  test.json
```

#### 情况B: 如果是分开的ZIP文件

```bash
# 创建目标目录
mkdir -p ./data/RiSAWOZ

# 分别解压每个文件
unzip train.zip -d ./data/RiSAWOZ/
unzip val.zip -d ./data/RiSAWOZ/
unzip test.zip -d ./data/RiSAWOZ/
```

#### 情况C: 如果解压后有嵌套目录

```bash
# 例如解压后是这样:
# ./data/RiSAWOZ/RiSAWOZ-master/train.json

# 移动文件到正确位置
mv ./data/RiSAWOZ/RiSAWOZ-master/*.json ./data/RiSAWOZ/

# 删除空目录
rm -rf ./data/RiSAWOZ/RiSAWOZ-master
```

### 3. 验证文件完整性

```bash
# 检查文件是否存在
ls -lh ./data/RiSAWOZ/

# 检查文件大小（应该不是空文件）
# train.json 通常最大（8000+对话）
# val.json 和 test.json 较小（各1500+对话）

# 快速检查JSON格式
python -c "import json; json.load(open('./data/RiSAWOZ/train.json'))"
python -c "import json; json.load(open('./data/RiSAWOZ/val.json'))"
python -c "import json; json.load(open('./data/RiSAWOZ/test.json'))"
```

如果没有错误，说明文件格式正确。

## 路径配置

### 方式1: 使用默认路径（推荐）

将数据放在 `./data/RiSAWOZ/` 目录下，然后直接运行：

```bash
python benchmark/run_dst_risawoz.py
```

代码会自动使用默认路径 `./data/RiSAWOZ`。

### 方式2: 命令行指定路径

如果数据在其他位置，使用 `--data-root` 参数：

```bash
python benchmark/run_dst_risawoz.py --data-root /path/to/your/RiSAWOZ
```

**示例**:
```bash
# 数据在 /home/user/datasets/RiSAWOZ
python benchmark/run_dst_risawoz.py --data-root /home/user/datasets/RiSAWOZ

# 数据在 Windows 路径
python benchmark/run_dst_risawoz.py --data-root C:/datasets/RiSAWOZ
```

### 方式3: 在代码中配置

如果你要在 Python 代码中使用适配器：

```python
from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter

# 使用自定义路径
adapter = RiSAWOZAdapter(data_root="/custom/path/to/RiSAWOZ")

# 加载对话
dialogue = adapter.load_dialogue("dialogue_id", split="val")
```

## 常见问题和解决方案

### Q1: FileNotFoundError: 数据文件不存在

**错误信息**:
```
FileNotFoundError: 数据文件不存在: ./data/RiSAWOZ/val.json
```

**原因**: 文件路径不正确或文件不存在。

**解决方案**:

1. **检查文件是否存在**:
```bash
ls -la ./data/RiSAWOZ/
```

2. **检查文件名是否正确**:
- 必须是 `train.json`, `val.json`, `test.json`
- 注意大小写（Linux/Mac 区分大小写）
- 不能有额外的后缀（如 `.json.txt`）

3. **检查路径是否正确**:
```bash
# 使用绝对路径
pwd  # 查看当前目录
ls -la ./data/RiSAWOZ/  # 相对路径
```

4. **使用绝对路径运行**:
```bash
python benchmark/run_dst_risawoz.py --data-root /absolute/path/to/RiSAWOZ
```

### Q2: 解压后目录结构不对

**问题**: 解压后有多余的嵌套目录

**示例**:
```
./data/RiSAWOZ/
└── RiSAWOZ-master/      ← 多了一层目录
    ├── train.json
    ├── val.json
    └── test.json
```

**解决方案1: 移动文件**:
```bash
# 移动JSON文件到上层目录
mv ./data/RiSAWOZ/RiSAWOZ-master/*.json ./data/RiSAWOZ/

# 删除空目录
rm -rf ./data/RiSAWOZ/RiSAWOZ-master

# 验证
ls ./data/RiSAWOZ/
```

**解决方案2: 重新解压**:
```bash
# 删除错误的目录
rm -rf ./data/RiSAWOZ

# 解压到临时目录
unzip RiSAWOZ.zip

# 创建正确的目录并复制文件
mkdir -p ./data/RiSAWOZ
cp RiSAWOZ-master/data/*.json ./data/RiSAWOZ/
```

### Q3: ZIP文件内部结构复杂

**问题**: ZIP文件包含多个子目录

**解决方案**:

1. **先查看ZIP内容**:
```bash
unzip -l RiSAWOZ.zip
# 查看文件列表，找到JSON文件的位置
```

2. **提取特定文件**:
```bash
# 只提取JSON文件
unzip RiSAWOZ.zip "*/train.json" "*/val.json" "*/test.json" -d temp/

# 找到并移动文件
find temp/ -name "*.json" -exec cp {} ./data/RiSAWOZ/ \;
```

### Q4: Windows 路径问题

**问题**: 在 Windows 上路径格式不同

**解决方案**:

```bash
# Windows 使用反斜杠，但在命令行中可以用正斜杠
python benchmark/run_dst_risawoz.py --data-root C:/data/RiSAWOZ

# 或者使用双反斜杠
python benchmark/run_dst_risawoz.py --data-root C:\\data\\RiSAWOZ

# 或者使用原始字符串（在Python代码中）
adapter = RiSAWOZAdapter(r"C:\data\RiSAWOZ")
```

### Q5: 权限问题

**错误**: Permission denied

**解决方案**:

```bash
# 检查文件权限
ls -l ./data/RiSAWOZ/

# 修改权限（Linux/Mac）
chmod 644 ./data/RiSAWOZ/*.json

# 修改目录权限
chmod 755 ./data/RiSAWOZ/
```

### Q6: 如何验证数据集设置正确？

**方法1: 快速验证**:
```python
python -c "from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter; \
           adapter = RiSAWOZAdapter('./data/RiSAWOZ'); \
           print('✅ 数据集设置成功!')"
```

**方法2: 详细验证**:
```python
from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter

# 初始化适配器
adapter = RiSAWOZAdapter('./data/RiSAWOZ')

# 检查每个数据集划分
for split in ['train', 'val', 'test']:
    try:
        dialogues = adapter.get_dialogues_by_domain(split=split)
        print(f"✅ {split}: {len(dialogues)} 对话")
    except Exception as e:
        print(f"❌ {split}: {e}")

print("验证完成!")
```

**方法3: 运行小规模测试**:
```bash
# 限制测试数量，快速验证
python benchmark/run_dst_risawoz.py --limit 5 --verbose
```

## 数据集信息

### 基本信息

- **总对话数**: ~11,000
- **领域数**: 12个
- **语言**: 中文

### 数据集划分

- **训练集 (train.json)**: ~8,000 对话
- **验证集 (val.json)**: ~1,500 对话
- **测试集 (test.json)**: ~1,500 对话

### 12个领域

1. 景点 (Attraction)
2. 酒店 (Hotel)
3. 餐厅 (Restaurant)
4. 地铁 (Metro)
5. 出租 (Taxi)
6. 火车 (Train)
7. 电视剧 (TV Series)
8. 天气 (Weather)
9. 航班 (Flight)
10. 医院 (Hospital)
11. 电影 (Movie)
12. 音乐 (Music)

## 验证脚本

将以下脚本保存为 `verify_risawoz.py`:

```python
#!/usr/bin/env python3
"""验证 RiSAWOZ 数据集设置"""

import sys
from pathlib import Path

def verify_risawoz(data_root="./data/RiSAWOZ"):
    """验证 RiSAWOZ 数据集"""
    
    print("=" * 70)
    print("RiSAWOZ 数据集验证")
    print("=" * 70)
    
    data_path = Path(data_root)
    
    # 1. 检查目录是否存在
    print(f"\n1. 检查目录: {data_path}")
    if not data_path.exists():
        print(f"❌ 目录不存在: {data_path}")
        print(f"   请创建目录: mkdir -p {data_path}")
        return False
    print(f"✅ 目录存在")
    
    # 2. 检查文件是否存在
    print("\n2. 检查文件:")
    all_files_exist = True
    for split in ['train', 'val', 'test']:
        file_path = data_path / f"{split}.json"
        if file_path.exists():
            size_mb = file_path.stat().st_size / (1024 * 1024)
            print(f"✅ {split}.json ({size_mb:.2f} MB)")
        else:
            print(f"❌ {split}.json 不存在")
            all_files_exist = False
    
    if not all_files_exist:
        print("\n请确保所有JSON文件都已解压到正确位置。")
        return False
    
    # 3. 检查JSON格式
    print("\n3. 检查JSON格式:")
    try:
        from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter
        
        adapter = RiSAWOZAdapter(data_root)
        
        for split in ['train', 'val', 'test']:
            try:
                dialogues = adapter.get_dialogues_by_domain(split=split)
                print(f"✅ {split}: {len(dialogues)} 对话")
            except Exception as e:
                print(f"❌ {split}: {e}")
                return False
                
    except ImportError:
        print("⚠️  无法导入 RiSAWOZAdapter，跳过详细检查")
        import json
        for split in ['train', 'val', 'test']:
            file_path = data_path / f"{split}.json"
            try:
                with open(file_path) as f:
                    data = json.load(f)
                print(f"✅ {split}.json: JSON格式正确")
            except Exception as e:
                print(f"❌ {split}.json: {e}")
                return False
    
    print("\n" + "=" * 70)
    print("✅ 所有检查通过！数据集设置正确。")
    print("=" * 70)
    print("\n现在可以运行评测:")
    print("  python benchmark/run_dst_risawoz.py")
    return True

if __name__ == "__main__":
    data_root = sys.argv[1] if len(sys.argv) > 1 else "./data/RiSAWOZ"
    success = verify_risawoz(data_root)
    sys.exit(0 if success else 1)
```

**使用方法**:
```bash
# 使用默认路径
python verify_risawoz.py

# 使用自定义路径
python verify_risawoz.py /path/to/RiSAWOZ
```

## 总结

### 关键点

1. ✅ **不需要特殊处理** - 代码只需要3个JSON文件在同一目录
2. ✅ **简单的目录结构** - 不需要复杂的子目录
3. ✅ **灵活的路径配置** - 支持默认路径和自定义路径
4. ✅ **完整的验证方法** - 可以确认设置是否正确

### 标准流程

```bash
# 1. 创建目录
mkdir -p ./data/RiSAWOZ

# 2. 解压文件
unzip *.zip -d ./data/RiSAWOZ/

# 3. 验证
ls ./data/RiSAWOZ/  # 应该看到: train.json val.json test.json

# 4. 运行评测
python benchmark/run_dst_risawoz.py
```

### 参考资料

- RiSAWOZ GitHub: https://github.com/terryqj0107/RiSAWOZ
- 适配器代码: `benchmark/datasets/risawoz/adapter.py`
- 评测脚本: `benchmark/run_dst_risawoz.py`
- 使用文档: `benchmark/datasets/risawoz/README.md`

---

**最后更新**: 2026-02-11
