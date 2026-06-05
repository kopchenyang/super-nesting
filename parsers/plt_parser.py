"""
服装CAD超级排料系统 - PLT (HP-GL) 文件解析器
支持HP-GL/HP-GL2指令集，解析裁片轮廓、刀口、纱向等信息
"""

from typing import List, Tuple, Optional, BinaryIO
import re
import math
try:
    from ..core.models import Piece, Point, Notch, Drill, NestingConfig
except ImportError:
    from core.models import Piece, Point, Notch, Drill, NestingConfig


class PLTParser:
    """
    PLT (HP-GL) 文件解析器

    HP-GL常用指令：
      PU x,y      抬笔移动到(x,y)
      PD x,y      落笔画到(x,y)
      PA x,y,...  绝对坐标
      PR x,y,...  相对坐标
      SP n        选择笔号
      IN          初始化
      VS v        笔速
      PW w        笔宽
      LB text     标签文字
    """

    def __init__(self, config: Optional[NestingConfig] = None):
        self.config = config or NestingConfig()
        self.pieces: List[Piece] = []
        self._current_pos = Point(0, 0)
        self._current_pen = 1         # 1=绘图, 0=抬笔
        self._resolution = self.config.plt_resolution  # 1016 dpi
        self._scale = 25.4 / self._resolution          # 每步长 = mm

    def parse_file(self, filepath: str) -> List[Piece]:
        """解析PLT文件，返回裁片列表"""
        with open(filepath, 'r', encoding='ascii', errors='ignore') as f:
            content = f.read()
        return self.parse(content)

    def parse(self, content: str) -> List[Piece]:
        """解析PLT内容"""
        self.pieces = []
        self._current_pos = Point(0, 0)
        self._current_pen = 1

        # 清理内容：移除注释，合并多行指令
        content = self._clean_content(content)

        # 分离指令
        instructions = self._tokenize(content)

        # 提取所有笔画的路径段
        paths = self._extract_paths(instructions)

        # 将路径段合并为封闭轮廓
        raw_contours = self._merge_to_contours(paths)

        # 识别裁片：分离外轮廓和内线
        self.pieces = self._identify_pieces(raw_contours)

        print(f"PLT解析完成: {len(self.pieces)} 个裁片")
        return self.pieces

    def _clean_content(self, content: str) -> str:
        """清理PLT内容"""
        # 移除注释
        content = re.sub(r'#.*', '', content)
        # 统一换行和分号
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        return content

    def _tokenize(self, content: str) -> List[str]:
        """将PLT内容分解为指令序列"""
        # 在指令字母前加分隔符
        content = re.sub(r'([A-Za-z]{2})', r'\n\1', content)
        tokens = content.strip().split('\n')
        return [t.strip() for t in tokens if t.strip()]

    def _extract_paths(self, instructions: List[str]) -> List[List[Point]]:
        """从指令中提取笔画路径"""
        paths = []
        current_path = []

        for inst in instructions:
            cmd = inst[:2].upper()
            # 解析坐标参数
            coords_str = inst[2:].strip()
            coords = self._parse_coordinates(coords_str)

            if cmd in ('PU', 'PA'):  # 抬笔 / 绝对坐标
                if current_path:
                    paths.append(current_path)
                    current_path = []
                self._current_pos = coords[-1] if coords else self._current_pos
                # PU后跟的坐标是新的起点

            elif cmd == 'PD':  # 落笔
                self._current_pen = 1
                for pt in coords:
                    current_path.append(pt)
                self._current_pos = coords[-1] if coords else self._current_pos

            elif cmd == 'PR':  # 相对坐标
                for pt in coords:
                    self._current_pos = Point(
                        self._current_pos.x + pt.x,
                        self._current_pos.y + pt.y
                    )
                    if self._current_pen == 1:
                        current_path.append(self._current_pos)

            elif cmd == 'SP':  # 换笔
                try:
                    self._current_pen = int(coords_str)
                except ValueError:
                    pass

            elif cmd == 'IN':  # 初始化
                self._current_pos = Point(0, 0)
                self._current_pen = 1

        if current_path:
            paths.append(current_path)

        return paths

    def _parse_coordinates(self, coords_str: str) -> List[Point]:
        """解析坐标字符串，转换为世界坐标(mm)"""
        points = []
        if not coords_str:
            return points

        # 匹配坐标对: x,y 或 x y
        pairs = re.findall(r'(-?\d+)[,\s]+(-?\d+)', coords_str)
        for x_str, y_str in pairs:
            x = int(x_str) * self._scale
            y = int(y_str) * self._scale
            points.append(Point(x, y))
        return points

    def _merge_to_contours(self, paths: List[List[Point]]) -> List[List[Point]]:
        """将路径段合并为封闭轮廓"""
        if not paths:
            return []

        # 过滤太短的路径
        min_area_px = self.config.plt_min_piece_area
        filtered = [p for p in paths if len(p) >= 3]

        # 尝试连接首尾相近的路径
        tolerance = self.config.plt_close_tolerance
        merged = []
        used = set()

        for i, path in enumerate(filtered):
            if i in used:
                continue
            contour = list(path)

            # 尝试连接后续路径
            for j in range(i + 1, len(filtered)):
                if j in used:
                    continue
                other = filtered[j]
                # 检查是否首尾相接
                if (contour[-1].distance(other[0]) < tolerance or
                        contour[-1].distance(other[-1]) < tolerance):
                    contour.extend(other if contour[-1].distance(other[0]) < tolerance
                                   else reversed(other))
                    used.add(j)
                elif (contour[0].distance(other[-1]) < tolerance or
                      contour[0].distance(other[0]) < tolerance):
                    contour = (other if contour[0].distance(other[-1]) < tolerance
                               else list(reversed(other))) + contour
                    used.add(j)

            merged.append(contour)
            used.add(i)

        return merged

    def _identify_pieces(self, contours: List[List[Point]]) -> List[Piece]:
        """识别裁片：区分外轮廓和内线"""
        pieces = []
        # 按面积排序，大的可能是外轮廓
        scored = [(self._polygon_area(c), i, c) for i, c in enumerate(contours)]
        scored.sort(key=lambda x: x[0], reverse=True)

        min_area = self.config.plt_min_piece_area
        outer_contours = []
        inner_contours = []

        for area, idx, contour in scored:
            if area < min_area:
                continue
            # 简单地按面积分：最大的几个为外轮廓
            if area > min_area * 2 and len(outer_contours) < len(scored) * 0.7:
                outer_contours.append(contour)
            else:
                inner_contours.append(contour)

        for i, contour in enumerate(outer_contours):
            piece = Piece(
                name=f"裁片{i + 1}",
                contour=self._normalize_contour(contour),
            )
            pieces.append(piece)

        return pieces

    def _polygon_area(self, points: List[Point]) -> float:
        """计算多边形面积"""
        n = len(points)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += points[i].x * points[j].y
            area -= points[j].x * points[i].y
        return abs(area) / 2.0

    def _normalize_contour(self, points: List[Point]) -> List[Point]:
        """标准化轮廓（闭合、顺时针、去重）"""
        if not points:
            return points

        # 确保闭合
        if points[0].distance(points[-1]) > 0.01:
            points.append(points[0])

        # 移到原点附近（第一象限）
        min_x = min(p.x for p in points)
        min_y = min(p.y for p in points)
        return [Point(p.x - min_x, p.y - min_y) for p in points]
