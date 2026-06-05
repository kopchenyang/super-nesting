#!/usr/bin/env python3
"""
服装CAD超级排料系统 - 主程序入口
兼容 Windows 7/8/10/11，免加密
"""

import sys
import os

# 兼容PyInstaller打包路径
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)


def main():
    """主入口 - GUI模式"""
    try:
        from gui.main_window import run
        run()
    except ImportError as e:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("错误", f"模块导入失败: {e}\n\n请重新安装程序")
    except Exception as e:
        import traceback
        err_file = os.path.join(os.path.expanduser("~"), "super_nesting_error.txt")
        with open(err_file, 'w') as f:
            traceback.print_exc(file=f)
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("错误",
            f"程序出错: {e}\n\n详细日志已保存到:\n{err_file}")


def main_cli():
    """命令行模式"""
    import argparse
    from core.models import NestingConfig, Marker
    from core.engine import NestingEngine
    from parsers.plt_parser import PLTParser

    parser = argparse.ArgumentParser(description="服装CAD超级排料系统")
    parser.add_argument("input", help="输入文件 (.plt)")
    parser.add_argument("-w", "--width", type=float, default=1500, help="面料幅宽(mm)")
    parser.add_argument("-o", "--output", default="result.plt", help="输出文件")
    parser.add_argument("-a", "--algorithm", default="hybrid",
                        choices=["hybrid", "greedy", "genetic"])

    args = parser.parse_args()

    config = NestingConfig()
    config.algorithm = args.algorithm

    ext = os.path.splitext(args.input)[1].lower()
    if ext == '.dxf':
        from parsers.dxf_parser import DXFParser
        parser_obj = DXFParser(config)
    else:
        parser_obj = PLTParser(config)

    print(f"加载: {args.input}")
    pieces = parser_obj.parse_file(args.input)

    marker = Marker(name=os.path.basename(args.input),
                    fabric_width=args.width, pieces=pieces)

    engine = NestingEngine(config)
    result = engine.nest(marker, progress_callback=lambda p, s: print(f"  [{p}%] {s}"))

    print(f"完成! 利用率: {result.utilization:.1f}%")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main_cli()
    else:
        main()
