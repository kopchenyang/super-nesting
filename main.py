#!/usr/bin/env python3
"""
服装CAD超级排料系统 - 主程序入口
兼容 Windows 7/8/10/11
免加密，自由使用
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """主入口"""
    # 检查依赖
    try:
        import PyQt5
    except ImportError:
        print("❌ 未安装 PyQt5")
        print("   请运行: pip install PyQt5")
        print("   或运行: pip install -r requirements.txt")
        input("按回车键退出...")
        sys.exit(1)

    # 启动GUI
    from gui.main_window import run
    run()


def main_cli():
    """命令行模式（无需GUI）"""
    import argparse
    from core.models import NestingConfig, Marker
    from core.engine import NestingEngine
    from parsers.plt_parser import PLTParser
    from parsers.dxf_parser import DXFParser

    parser = argparse.ArgumentParser(
        description="服装CAD超级排料系统 - 命令行版"
    )
    parser.add_argument("input", help="输入文件 (.plt 或 .dxf)")
    parser.add_argument("-w", "--width", type=float, default=1500,
                        help="面料幅宽(mm), 默认1500")
    parser.add_argument("-o", "--output", default="result.plt",
                        help="输出文件, 默认result.plt")
    parser.add_argument("-a", "--algorithm", default="hybrid",
                        choices=["hybrid", "greedy", "genetic"],
                        help="排料算法, 默认hybrid")
    parser.add_argument("-t", "--time", type=int, default=300,
                        help="时间限制(秒), 默认300")

    args = parser.parse_args()

    # 加载文件
    ext = os.path.splitext(args.input)[1].lower()
    config = NestingConfig()
    config.algorithm = args.algorithm
    config.time_limit_seconds = args.time

    if ext == '.plt':
        parser_obj = PLTParser(config)
    elif ext == '.dxf':
        parser_obj = DXFParser(config)
    else:
        print(f"不支持的文件格式: {ext}")
        sys.exit(1)

    print(f"📂 加载文件: {args.input}")
    pieces = parser_obj.parse_file(args.input)
    print(f"   解析完成: {len(pieces)} 个裁片")

    # 排料
    marker = Marker(
        name=os.path.basename(args.input),
        fabric_width=args.width,
        pieces=pieces,
    )

    print(f"🚀 开始排料 (算法: {args.algorithm}, 幅宽: {args.width}mm)")
    engine = NestingEngine(config)
    result = engine.nest(
        marker,
        progress_callback=lambda p, s: print(f"   [{p}%] {s}")
    )

    print(f"\n✅ 排料完成!")
    print(f"   利用率: {result.utilization:.1f}%")
    print(f"   用时: {result.elapsed_time:.1f}秒")
    print(f"   输出: {args.output}")

    # TODO: 导出结果


if __name__ == "__main__":
    # 无参数时启动GUI，有参数时启动CLI
    if len(sys.argv) > 1:
        main_cli()
    else:
        main()
