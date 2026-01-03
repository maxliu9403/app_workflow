"""
Vinted 自动化控制台 - 入口文件
==============================

运行此文件启动应用程序
"""

import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.main_window import MainWindow


def main():
    """应用程序入口"""
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()
