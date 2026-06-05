#!/usr/bin/env python3
"""
打包脚本 - 将系统打包为单个EXE文件
兼容 Windows 7 (需安装Python 3.8和PyInstaller)

使用方法:
    pip install pyinstaller
    python build_exe.py
"""

import os
import sys
import subprocess


def build():
    """打包为exe"""
    project_dir = os.path.dirname(os.path.abspath(__file__))

    # PyInstaller 参数
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=服装CAD超级排料系统",
        "--windowed",       # 不显示控制台
        "--onefile",        # 单个exe文件
        "--icon=NONE",      # 可以替换为图标文件
        "--clean",
        "--add-data=config;config",
        # 排除不需要的模块
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
        # Win7兼容
        "--win-private-assemblies",
        # 主入口
        os.path.join(project_dir, "main.py"),
    ]

    print("🔨 开始打包...")
    print(f"   命令: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=project_dir)

    if result.returncode == 0:
        print("\n✅ 打包完成!")
        print(f"   输出: {project_dir}/dist/服装CAD超级排料系统.exe")
    else:
        print("\n❌ 打包失败!")


if __name__ == "__main__":
    build()
