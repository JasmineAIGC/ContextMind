#!/usr/bin/env python3
"""
Schema 数据预生成脚本

从 data/ 目录下的 *_schema.json 文件生成各算法所需的 companion 数据文件：

  - data/*_pytod_apis.py   — PyTOD API 函数代码（每个意图一个 Python 函数定义）
                               （含 result_slots 字段，供 AP 通过 say(xN.field) 引用）
  - data/*_fnctod_domain.json — FnCTOD 域定义数据
                               （序列化的 DomainSpec，供 FunctionManager 直接加载）

使用方式::

    # 处理 data/ 下所有 schema
    python examples/build_schema_data.py

    # 处理指定目录
    python examples/build_schema_data.py --data-dir /path/to/schemas

    # 仅生成 PyTOD API 函数代码（跳过 FnCTOD）
    python examples/build_schema_data.py --pytod-only

    # 不覆盖已存在的文件
    python examples/build_schema_data.py --no-overwrite

    # 处理单个 schema 文件
    python examples/build_schema_data.py --schema data/anyihua_schema.json

这是一个 **一次性预生成步骤**，生成的文件应加入版本控制（git），
这样运行时无需重新生成，PyTOD 追踪器在初始化时直接加载 companion 文件。

当 schema.json 内容更新后，需重新运行本脚本以同步 companion 文件。
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径，无需安装即可直接运行
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.modes.schema_builder import SchemaDataBuilder

_DEFAULT_DATA_DIR = _PROJECT_ROOT / "data"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 schema.json 预生成 PyTOD / FnCTOD companion 数据文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data-dir",
        default=str(_DEFAULT_DATA_DIR),
        help=f"包含 *_schema.json 文件的目录（默认: {_DEFAULT_DATA_DIR}）",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="处理单个 schema.json 文件（与 --data-dir 互斥）",
    )
    parser.add_argument(
        "--pytod-only",
        action="store_true",
        help="仅生成 PyTOD APIs .py 文件，跳过 FnCTOD domain 文件",
    )
    parser.add_argument(
        "--fnctod-only",
        action="store_true",
        help="仅生成 FnCTOD domain 文件，跳过 PyTOD mock 文件",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="跳过已存在的文件，不覆盖",
    )
    args = parser.parse_args()

    builder = SchemaDataBuilder(overwrite=not args.no_overwrite)

    if args.schema:
        schema_path = Path(args.schema)
        if not schema_path.exists():
            print(f"❌ 文件不存在: {schema_path}", file=sys.stderr)
            sys.exit(1)
        _process_single(builder, schema_path, args)
    else:
        data_dir = Path(args.data_dir)
        if not data_dir.is_dir():
            print(f"❌ 目录不存在: {data_dir}", file=sys.stderr)
            sys.exit(1)
        _process_dir(builder, data_dir, args)


def _process_single(builder: SchemaDataBuilder, schema_path: Path, args: argparse.Namespace) -> None:
    """处理单个 schema 文件。"""
    print(f"📋 处理 schema: {schema_path}")
    import json
    from contextmind.modes.pytod.schemas import load_schema_from_dict
    try:
        with open(schema_path, encoding="utf-8") as fh:
            schema = load_schema_from_dict(json.load(fh))
    except Exception as exc:
        print(f"❌ 加载失败: {exc}", file=sys.stderr)
        sys.exit(1)

    if not args.fnctod_only:
        p = builder.build_pytod_apis(schema_path, schema=schema)
        if p:
            print(f"✅ PyTOD mock → {p}")
        else:
            print(f"⚠️  PyTOD mock 未写入（已存在且 --no-overwrite）")

    if not args.pytod_only:
        p = builder.build_fnctod_domain(schema_path, schema=schema)
        if p:
            print(f"✅ FnCTOD domain → {p}")
        else:
            print(f"⚠️  FnCTOD domain 未写入（已存在且 --no-overwrite）")


def _process_dir(builder: SchemaDataBuilder, data_dir: Path, args: argparse.Namespace) -> None:
    """处理目录下所有 schema 文件。"""
    schema_files = sorted(data_dir.glob("*_schema.json"))
    if not schema_files:
        print(f"⚠️  {data_dir} 下未找到任何 *_schema.json 文件")
        return

    print(f"📂 数据目录: {data_dir}")
    print(f"📋 找到 {len(schema_files)} 个 schema 文件:")
    for f in schema_files:
        print(f"   - {f.name}")
    print()

    import json
    from contextmind.modes.pytod.schemas import load_schema_from_dict

    written_total = 0
    for schema_path in schema_files:
        try:
            with open(schema_path, encoding="utf-8") as fh:
                schema = load_schema_from_dict(json.load(fh))
        except Exception as exc:
            print(f"❌ 加载失败 {schema_path.name}: {exc}", file=sys.stderr)
            continue

        print(f"📋 {schema_path.name} → service={schema.service_name}, intents={len(schema.intents)}")

        if not args.fnctod_only:
            p = builder.build_pytod_apis(schema_path, schema=schema)
            if p:
                print(f"   ✅ PyTOD mock  → {p.name}")
                written_total += 1
            else:
                print(f"   ⚠️  PyTOD mock  跳过（已存在）")

        if not args.pytod_only:
            p = builder.build_fnctod_domain(schema_path, schema=schema)
            if p:
                print(f"   ✅ FnCTOD domain → {p.name}")
                written_total += 1
            else:
                print(f"   ⚠️  FnCTOD domain 跳过（已存在）")

    print()
    print(f"🎉 完成！共写入 {written_total} 个文件")
    print()
    print("💡 提示：请将生成的文件加入版本控制（git add data/*_pytod_apis.json data/*_fnctod_domain.json）")
    print("💡 当 schema.json 更新后，重新运行本脚本以同步 companion 文件")


if __name__ == "__main__":
    main()
