**第二步（Step 2）：知识库 → 算法专用 Schema 数据生成**

> **ContextMind 三步框架中的第二步**：  
> - **第一步**（`contextmind.knowledge`）：任意数据集 → 知识库（`schema.json`）  
> - **第二步**（`contextmind.schema_builder`，本文档）：知识库 → 适配不同算法的 Schema 数据  
> - **第三步**（`contextmind.modes.*`）：算法执行（DST / FnCTOD / PyTOD / Evolve）  
>  
> 注意：第二步为可选步骤，仅 PyTOD 等需要自动生成 API 代码的算法才用到；DST、FnCTOD、Evolve 可跳过此步直接进入第三步。

以下是最终确定的、清晰规范的 **Step 2 完整运行流程**，严格按照你的要求设计，最终只输出一个 `xxx_pytod_apis.py` 文件。

### Step 2 整体目标
将第一步生成的 `xxx_schema.json`（包含意图和槽位）转换为一个包含所有意图具体实现函数的 Python 文件 `xxx_pytod_apis.py`，每个函数具备清晰入参、具体运算逻辑和统一出参格式。

### Step 2 完整运行步骤（共 5 个阶段）

**阶段 1：解析 schema.json**  
- 读取第一步输出的 `xxx_schema.json` 文件  
- 解析所有 `services` 和其中的 `intents`  
- 提取每个 intent 的核心信息：`intent_name`、`intent_description`、`slots` 列表（每个 slot 包含 `name`、`description`、`required` 等）  
- 输出：内存中的标准化 intent 列表，以及参数 slots（包含 name、description、required 等）

**阶段 2：构建测试用例**  
- 读取一个或多个真实的业务测试数据文件（JSON 格式）  
- 按 intent_name 聚合对话 turn  
- 为 schema.json 中每个 intent 提取 5~10 条高质量测试用例  
- 每条测试用例包含：`input_slots`（实际填充的槽位值）和 `expected_result`（预期返回结果 / label）  
- 支持过滤：仅保留有明确结果的 turn，避免噪声  
- 输出：`test_cases` 字典（key 为 intent_name，value 为测试用例列表）

**阶段 3：初始函数生成**  
- 对 schema.json 中的每一个 intent 逐一处理  
- 为每个 intent 构造 LLM Prompt，内容包括：  
  - intent_name 和 intent_description  
  - slots 详细信息（name + description）  
  - 从测试用例中选取的 few-shot 示例（输入槽位 + 预期结果）  
- 调用真实 LLM 生成函数体（body）  
- 函数体必须包含：具体运算逻辑、业务处理步骤、中文注释、输入处理逻辑  
- 生成统一返回格式：`{"status": "success"|"error", "message": "...", "result": {...}}`  
- 输出：每个 intent 的初始函数体代码

**阶段 4：验证与迭代优化**  
- 使用阶段 2 构建的测试用例，对已生成的函数进行批量执行验证  
- 计算每个 intent 的 pass_rate（通过率）  
- 对于 pass_rate 未达到阈值（例如 90%）或执行出错的 intent：  
  - 收集失败案例（输入、预期结果、实际输出、错误信息）  
  - 构造修复 Prompt（包含原始描述、失败反馈、few-shot）  
  - 调用 LLM 重新生成该 intent 的函数体  
  - 替换旧函数体，重新执行验证  
- 重复迭代最多 N 轮（推荐 3 轮），直到通过阈值或达到最大迭代次数  
- 冷门 intent（无测试用例）跳过迭代，仅保留初始生成结果  
- 输出：优化后的最终函数体

**阶段 5：生成最终输出文件**  
- 组装完整 Python 代码文件 `xxx_pytod_apis.py`，结构如下：  
  - 文件头部注释（说明生成方式、时间等）  
  - 每个 intent 对应的函数定义：  
    - 清晰的函数签名（根据 slots 生成入参）  
    - 详细 docstring（包含 intent 描述和槽位说明）  
    - 输入验证代码  
    - 具体运算逻辑 + 中文注释  
    - 统一返回 dict 格式  
  - 文件底部添加 `INTENT_REGISTRY` 字典（intent_name → 函数名映射）  
  - 添加简单加载提示  
- 可选：同时生成 `validation_report.json`，记录每个 intent 的初始通过率、最终通过率、迭代次数等信息  
- 最终输出：**单个文件 `xxx_pytod_apis.py`**（可直接被 Step 3 import 使用）

### 伪代码概述（流程主线）

```python
# Step 2 主流程伪代码
def run_step2(schema_path, test_data_paths=None, output_path="xxx_pytod_apis.py"):
    # 阶段1
    schema = parse_schema(schema_path)          # 提取 intents + slots
    
    # 阶段2
    if test_data_paths:
        test_cases = build_test_cases(test_data_paths, schema)
    else:
        test_cases = {}
    
    # 阶段3 + 阶段4
    functions = {}
    for intent in schema.all_intents:
        body = initial_generate(intent, test_cases.get(intent.name))
        
        if test_cases.get(intent.name):
            body = iterative_optimize(intent, body, test_cases[intent.name])
        
        functions[intent.name] = build_full_function(intent, body)
    
    # 阶段5
    final_code = assemble_python_file(functions, schema)
    save_to_file(final_code, output_path)
    
    print("Step 2 完成，最终输出：", output_path)
```

### 运行注意事项
- 整个过程以 `schema.json`（第一步输出）中的意图和槽位为核心依据
- 测试数据仅用于增强生成质量和迭代优化，不强制要求
- 最终输出仅为一个 `xxx_pytod_apis.py` 文件，结构清晰、函数独立、可直接执行
- 迭代优化仅针对有测试用例且初始验证失败的意图，控制计算成本
- **第三步**（`contextmind.modes.pytod`）可直接 import 该文件，通过 `INTENT_REGISTRY` 调用任意意图函数
- DST、FnCTOD、Evolve 等算法**不需要**执行第二步，可从第一步直接进入第三步

