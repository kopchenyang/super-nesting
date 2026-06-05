"""
服装CAD超级排料系统 - 主界面 (PyQt5)
兼容 Windows 7/8/10/11
"""

import sys
import os
import time
from typing import List, Optional

try:
    from PyQt5.QtWidgets import (
        QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTableWidget, QTableWidgetItem, QFileDialog,
        QMessageBox, QStatusBar, QMenuBar, QAction, QToolBar, QSplitter,
        QTreeWidget, QTreeWidgetItem, QGroupBox, QDockWidget, QSpinBox,
        QDoubleSpinBox, QComboBox, QCheckBox, QProgressBar, QTabWidget,
        QTextEdit, QHeaderView
    )
    from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
    from PyQt5.QtGui import QPainter, QPen, QColor, QBrush, QFont, QFontMetrics
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    print("PyQt5未安装。请运行: pip install PyQt5")


class NestingCanvas(QWidget):
    """排料画布 - 显示排料结果"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.marker = None
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.setMinimumSize(800, 500)
        self.setMouseTracking(True)
        self._last_mouse_pos = None
        self._dragging = False
        self.setStyleSheet("background-color: #1a1a2e;")

    def set_marker(self, marker):
        self.marker = marker
        self.update()

    def paintEvent(self, event):
        if not self.marker:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 面料背景
        fabric_width_px = self.marker.usable_width * self.scale
        fabric_length_px = max(self.height() * 2,
                               self.marker.fabric_length * self.scale)

        painter.fillRect(
            int(50 * self.scale), int(10 * self.scale),
            int(fabric_width_px), int(fabric_length_px),
            QColor("#2d2d44")
        )

        # 绘制已放置的裁片
        colors = [
            QColor("#4ecdc4"), QColor("#ff6b6b"), QColor("#45b7d1"),
            QColor("#f9ca24"), QColor("#6c5ce7"), QColor("#a29bfe"),
            QColor("#fd79a8"), QColor("#00b894"),
        ]

        for i, (piece, x, y, angle) in enumerate(
                self.marker.placed_pieces if hasattr(self.marker, 'placed_pieces') else []):
            color = colors[i % len(colors)]
            painter.setPen(QPen(color.darker(120), 1))
            painter.setBrush(QBrush(color))

            # 绘制裁片轮廓
            path_points = piece.contour
            if path_points and len(path_points) >= 2:
                from PyQt5.QtGui import QPolygonF
                from PyQt5.QtCore import QPointF
                polygon = QPolygonF()
                for pt in path_points:
                    px = (pt.x + x) * self.scale + 50
                    py = (pt.y + y) * self.scale + 10
                    polygon.append(QPointF(px, py))
                painter.drawPolygon(polygon)

            # 标签
            painter.setPen(QColor("#ffffff"))
            if path_points:
                bx = path_points[0].x * self.scale + 50
                by = path_points[0].y * self.scale + 10
                painter.drawText(int(bx), int(by) - 5,
                                 f"{piece.name}(x{piece.quantity})")

        # 边框
        painter.setPen(QPen(QColor("#e0e0e0"), 2))
        painter.drawRect(
            int(50 * self.scale), int(10 * self.scale),
            int(fabric_width_px), int(min(fabric_length_px,
                                          self.marker.fabric_length * self.scale))
        )

        # 利用率标注
        painter.setPen(QColor("#ffffff"))
        font = QFont("Microsoft YaHei", 11)
        painter.setFont(font)
        utilization = self.marker.utilization if hasattr(self.marker, 'utilization') else 0
        painter.drawText(
            10, self.height() - 20,
            f"面料宽度: {self.marker.fabric_width}mm | "
            f"利用率: {utilization:.1f}% | "
            f"缩放: {self.scale:.2f}x"
        )

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.scale = min(5.0, self.scale * 1.1)
        else:
            self.scale = max(0.1, self.scale / 1.1)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton or event.button() == Qt.RightButton:
            self._last_mouse_pos = event.pos()
            self._dragging = True

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def mouseMoveEvent(self, event):
        if self._dragging and self._last_mouse_pos:
            delta = event.pos() - self._last_mouse_pos
            self.offset_x += delta.x()
            self.offset_y += delta.y()
            self._last_mouse_pos = event.pos()
            self.update()


class NestingThread(QThread):
    """排料计算线程（后台运行，不阻塞UI）"""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)

    def __init__(self, engine, marker):
        super().__init__()
        self.engine = engine
        self.marker = marker

    def run(self):
        result = self.engine.nest(
            self.marker,
            progress_callback=lambda p, s: self.progress.emit(p, s)
        )
        self.finished.emit(result)


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("服装CAD超级排料系统 V1.0")
        self.resize(1400, 900)

        # 数据
        self.pieces: List = []
        self.marker: Optional = None
        self.config = None
        self._setup_config()

        # UI
        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()

    def _setup_config(self):
        """初始化配置"""
        try:
            from ..core.models import NestingConfig
        except ImportError:
            from core.models import NestingConfig
        self.config = NestingConfig()

    def _setup_ui(self):
        """构建主界面"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # 左侧面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setMaximumWidth(400)

        # 裁片列表
        pieces_group = QGroupBox("裁片列表")
        pieces_layout = QVBoxLayout(pieces_group)

        self.pieces_table = QTableWidget()
        self.pieces_table.setColumnCount(6)
        self.pieces_table.setHorizontalHeaderLabels(
            ["名称", "尺码", "数量", "面积(mm²)", "旋转", "色组"]
        )
        self.pieces_table.horizontalHeader().setStretchLastSection(True)
        self.pieces_table.setMinimumHeight(200)
        pieces_layout.addWidget(self.pieces_table)

        # 导入按钮
        btn_layout = QHBoxLayout()
        self.btn_import_plt = QPushButton("导入PLT")
        self.btn_import_dxf = QPushButton("导入DXF")
        self.btn_import_plt.clicked.connect(self._import_plt)
        self.btn_import_dxf.clicked.connect(self._import_dxf)
        btn_layout.addWidget(self.btn_import_plt)
        btn_layout.addWidget(self.btn_import_dxf)
        pieces_layout.addLayout(btn_layout)

        left_layout.addWidget(pieces_group)

        # 排料参数
        params_group = QGroupBox("排料参数")
        params_layout = QVBoxLayout(params_group)

        # 面料幅宽
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("面料幅宽(mm):"))
        self.spin_width = QDoubleSpinBox()
        self.spin_width.setRange(100, 5000)
        self.spin_width.setValue(1500)
        self.spin_width.setSuffix(" mm")
        row1.addWidget(self.spin_width)
        params_layout.addLayout(row1)

        # 排料模式
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("排料模式:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            "混合超排", "单件分段", "单码分段", "单片分段",
            "自定义分段", "最佳幅宽", "距离分段", "避瑕疵"
        ])
        row2.addWidget(self.combo_mode)
        params_layout.addLayout(row2)

        # 算法选择
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("算法:"))
        self.combo_algo = QComboBox()
        self.combo_algo.addItems(["混合算法(推荐)", "贪心快速", "遗传算法"])
        row3.addWidget(self.combo_algo)
        params_layout.addLayout(row3)

        # 裁片间距
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("裁片间距(mm):"))
        self.spin_spacing = QDoubleSpinBox()
        self.spin_spacing.setRange(0, 50)
        self.spin_spacing.setValue(2.0)
        self.spin_spacing.setSuffix(" mm")
        row4.addWidget(self.spin_spacing)
        params_layout.addLayout(row4)

        # 时间限制
        row5 = QHBoxLayout()
        row5.addWidget(QLabel("时间限制(秒):"))
        self.spin_time = QSpinBox()
        self.spin_time.setRange(10, 3600)
        self.spin_time.setValue(300)
        self.spin_time.setSuffix(" 秒")
        row5.addWidget(self.spin_time)
        params_layout.addLayout(row5)

        # 选项
        self.chk_napped = QCheckBox("倒顺毛面料")
        self.chk_stripe = QCheckBox("对条格排料")
        self.chk_bundle = QCheckBox("捆绑排料")
        self.chk_defect = QCheckBox("避色差")
        params_layout.addWidget(self.chk_napped)
        params_layout.addWidget(self.chk_stripe)
        params_layout.addWidget(self.chk_bundle)
        params_layout.addWidget(self.chk_defect)

        left_layout.addWidget(params_group)

        # 排料按钮
        self.btn_nest = QPushButton("🚀 开始超级排料")
        self.btn_nest.setStyleSheet("""
            QPushButton {
                background-color: #4ecdc4; color: white;
                font-size: 16px; font-weight: bold;
                padding: 12px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #45b7d1; }
        """)
        self.btn_nest.clicked.connect(self._start_nesting)
        left_layout.addWidget(self.btn_nest)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        left_layout.addWidget(self.progress)

        # 状态文本
        self.status_text = QTextEdit()
        self.status_text.setMaximumHeight(100)
        self.status_text.setReadOnly(True)
        left_layout.addWidget(self.status_text)

        left_layout.addStretch()
        layout.addWidget(left_panel)

        # 右侧画布
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        self.canvas = NestingCanvas()
        right_layout.addWidget(self.canvas)

        # 结果信息
        info_layout = QHBoxLayout()
        self.lbl_result = QLabel("就绪 - 请导入裁片文件后开始排料")
        self.lbl_result.setStyleSheet("color: #888; font-size: 12px;")
        info_layout.addWidget(self.lbl_result)
        info_layout.addStretch()
        self.btn_export = QPushButton("导出PLT")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_result)
        info_layout.addWidget(self.btn_export)
        right_layout.addLayout(info_layout)

        layout.addWidget(right_panel)

    def _setup_menu(self):
        """设置菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        file_menu.addAction("导入PLT文件...", self._import_plt, "Ctrl+P")
        file_menu.addAction("导入DXF文件...", self._import_dxf, "Ctrl+D")
        file_menu.addSeparator()
        file_menu.addAction("导出排料结果...", self._export_result, "Ctrl+E")
        file_menu.addSeparator()
        file_menu.addAction("退出(&X)", self.close, "Alt+F4")

        # 排料菜单
        nest_menu = menubar.addMenu("排料(&N)")
        nest_menu.addAction("开始排料(&S)", self._start_nesting, "F5")
        nest_menu.addAction("停止排料(&T)", self._stop_nesting, "Esc")

        # 设置菜单
        settings_menu = menubar.addMenu("设置(&S)")
        settings_menu.addAction("系统参数...", self._open_settings)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        help_menu.addAction("使用说明", self._show_help)
        help_menu.addAction("关于系统", self._show_about)

    def _setup_statusbar(self):
        """状态栏"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("就绪 | 兼容Win7/8/10/11 | 免加密版本")

    # ── 事件处理 ──

    def _import_plt(self):
        """导入PLT文件"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "导入PLT文件", "",
            "PLT文件 (*.plt *.PLT);;所有文件 (*.*)"
        )
        if filepath:
            self._load_file(filepath, 'plt')

    def _import_dxf(self):
        """导入DXF文件"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "导入DXF文件", "",
            "DXF文件 (*.dxf *.DXF);;所有文件 (*.*)"
        )
        if filepath:
            self._load_file(filepath, 'dxf')

    def _load_file(self, filepath, file_type):
        """加载文件"""
        self.statusbar.showMessage(f"正在解析 {filepath}...")
        try:
            try:
                from ..parsers.plt_parser import PLTParser
                from ..parsers.dxf_parser import DXFParser
            except ImportError:
                from parsers.plt_parser import PLTParser
                from parsers.dxf_parser import DXFParser

            if file_type == 'plt':
                parser = PLTParser(self.config)
            else:
                parser = DXFParser(self.config)

            self.pieces = parser.parse_file(filepath)
            self._update_pieces_table()
            self.statusbar.showMessage(
                f"加载完成: {os.path.basename(filepath)} | "
                f"{len(self.pieces)} 个裁片"
            )
        except Exception as e:
            QMessageBox.critical(self, "加载失败", str(e))
            self.statusbar.showMessage("加载失败")

    def _update_pieces_table(self):
        """更新裁片列表"""
        self.pieces_table.setRowCount(len(self.pieces))
        for i, piece in enumerate(self.pieces):
            self.pieces_table.setItem(i, 0, QTableWidgetItem(piece.name))
            self.pieces_table.setItem(i, 1, QTableWidgetItem(piece.size_code))
            self.pieces_table.setItem(i, 2, QTableWidgetItem(str(piece.quantity)))
            self.pieces_table.setItem(i, 3, QTableWidgetItem(f"{piece.area:.1f}"))
            self.pieces_table.setItem(i, 4, QTableWidgetItem(
                piece.rotation_mode.name
            ))
            self.pieces_table.setItem(i, 5, QTableWidgetItem(str(piece.color_group)))

    def _start_nesting(self):
        """开始排料"""
        if not self.pieces:
            QMessageBox.warning(self, "提示", "请先导入裁片文件！")
            return

        try:
            from ..core.models import Marker, NestingConfig
            from ..core.engine import NestingEngine
        except ImportError:
            from core.models import Marker, NestingConfig
            from core.engine import NestingEngine

        # 构建Marker
        self.marker = Marker(
            name=f"排料_{time.strftime('%Y%m%d_%H%M%S')}",
            fabric_width=self.spin_width.value(),
            pieces=list(self.pieces),
            spacing=self.spin_spacing.value(),
            is_napped=self.chk_napped.isChecked(),
            has_stripe=self.chk_stripe.isChecked(),
        )

        # 配置引擎
        algo_map = {"混合算法(推荐)": "hybrid", "贪心快速": "greedy", "遗传算法": "genetic"}
        self.config.algorithm = algo_map[self.combo_algo.currentText()]
        self.config.default_spacing = self.spin_spacing.value()
        self.config.time_limit_seconds = self.spin_time.value()

        engine = NestingEngine(self.config)

        # 启动后台线程
        self.nest_thread = NestingThread(engine, self.marker)
        self.nest_thread.progress.connect(self._on_progress)
        self.nest_thread.finished.connect(self._on_nesting_done)
        self.nest_thread.start()

        self.btn_nest.setEnabled(False)
        self.progress.setVisible(True)
        self.statusbar.showMessage("正在超级排料中...")

    def _stop_nesting(self):
        """停止排料"""
        if hasattr(self, 'nest_thread') and self.nest_thread.isRunning():
            self.nest_thread.terminate()
            self.nest_thread.wait()
            self.btn_nest.setEnabled(True)
            self.progress.setVisible(False)
            self.statusbar.showMessage("排料已中断")

    def _on_progress(self, percent, message):
        """进度更新"""
        self.progress.setValue(percent)
        self.status_text.append(f"[{percent}%] {message}")

    def _on_nesting_done(self, result):
        """排料完成"""
        self.btn_nest.setEnabled(True)
        self.progress.setVisible(False)

        # 更新marker
        for placement in result.placements:
            # 找对应的piece
            for _, piece in enumerate(self.pieces):
                pass  # 简化处理

        self.marker.utilization = result.utilization
        self.canvas.set_marker(self.marker)

        self.lbl_result.setText(
            f"✅ 排料完成 | 利用率: {result.utilization:.1f}% | "
            f"用时: {result.elapsed_time:.1f}秒 | "
            f"迭代: {result.iterations}次"
        )
        self.lbl_result.setStyleSheet("color: #4ecdc4; font-weight: bold;")
        self.btn_export.setEnabled(True)
        self.statusbar.showMessage(
            f"排料完成 | 利用率 {result.utilization:.1f}%"
        )

    def _export_result(self):
        """导出结果"""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出排料结果", "marker_result.plt",
            "PLT文件 (*.plt);;DXF文件 (*.dxf);;所有文件 (*.*)"
        )
        if filepath:
            try:
                self._write_plt_output(filepath)
                QMessageBox.information(self, "导出成功",
                                        f"排料结果已保存到:\n{filepath}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", str(e))

    def _write_plt_output(self, filepath):
        """写入PLT输出文件"""
        with open(filepath, 'w') as f:
            f.write("IN;SP1;\n")
            for piece, x, y, angle in (self.marker.placed_pieces if hasattr(
                    self.marker, 'placed_pieces') else []):
                f.write(f"PU{int(x)},{int(y)};\n")
                f.write(f"PD{int(x + piece.bbox.width)},{int(y)};\n")
                f.write(f"PD{int(x + piece.bbox.width)},{int(y + piece.bbox.height)};\n")
                f.write(f"PD{int(x)},{int(y + piece.bbox.height)};\n")
                f.write(f"PD{int(x)},{int(y)};\n")
            f.write("SP0;\n")

    def _open_settings(self):
        QMessageBox.information(self, "系统设置",
                                "系统参数设置面板（开发中）\n"
                                "可配置: PLT分辨率、DXF单位、显示颜色等")

    def _show_help(self):
        QMessageBox.information(self, "使用说明",
                                "服装CAD超级排料系统 V1.0\n\n"
                                "1. 点击「导入PLT」或「导入DXF」加载裁片\n"
                                "2. 设置面料幅宽和排料参数\n"
                                "3. 点击「开始超级排料」自动计算\n"
                                "4. 查看结果后导出排料图\n\n"
                                "快捷键: F5开始排料, Ctrl+P导入PLT")

    def _show_about(self):
        QMessageBox.about(self, "关于",
                          "服装CAD超级排料系统 V1.0\n\n"
                          "开源免费 | 免加密 | 兼容Win7+\n"
                          "核心算法: NFP + 遗传算法 + 模拟退火\n\n"
                          "© 2026 SuperNesting Project")


def run():
    """启动应用"""
    if not PYQT_AVAILABLE:
        print("需要安装PyQt5: pip install PyQt5")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 暗色主题
    app.setStyleSheet("""
        QMainWindow { background-color: #1a1a2e; color: #e0e0e0; }
        QGroupBox {
            color: #4ecdc4; font-weight: bold;
            border: 1px solid #333; border-radius: 6px;
            margin-top: 10px; padding-top: 15px;
        }
        QGroupBox::title {
            subcontrol-origin: margin; left: 10px;
        }
        QLabel { color: #ccc; }
        QPushButton {
            background-color: #333; color: #ccc;
            border: 1px solid #555; border-radius: 4px;
            padding: 6px 12px;
        }
        QPushButton:hover { background-color: #444; }
        QTableWidget {
            background-color: #222; color: #ccc;
            gridline-color: #333; border: 1px solid #333;
        }
        QHeaderView::section { background-color: #333; color: #ccc; }
        QSpinBox, QDoubleSpinBox, QComboBox {
            background-color: #222; color: #ccc;
            border: 1px solid #555; padding: 4px;
        }
        QProgressBar {
            border: 1px solid #555; border-radius: 4px;
            text-align: center; color: white;
        }
        QProgressBar::chunk { background-color: #4ecdc4; }
        QStatusBar { background-color: #222; color: #888; }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run()
