"""
服装CAD超级排料系统 - DXF文件解析器
支持AutoCAD DXF R12-2018格式，智能识别裁片轮廓、内部线、刀口
"""

from typing import List, Optional, Dict, Tuple
import math
from core.models import Piece, Point, Notch, Drill, NestingConfig


class DXFParser:
    """DXF文件解析器"""

    def __init__(self, config: Optional[NestingConfig] = None):
        self.config = config or NestingConfig()
        self.pieces: List[Piece] = []
        self._entities: List[dict] = []
        self._layers: Dict[str, List[dict]] = {}

    def parse_file(self, filepath: str) -> List[Piece]:
        """解析DXF文件"""
        self._entities = []
        self._layers = {}

        # 读取DXF
        entities = self._read_dxf_entities(filepath)

        # 按图层分组
        for entity in entities:
            layer = entity.get('layer', '0')
            if layer not in self._layers:
                self._layers[layer] = []
            self._layers[layer].append(entity)

        # 识别裁片
        self.pieces = self._extract_pieces()

        print(f"DXF解析完成: {len(self.pieces)} 个裁片")
        return self.pieces

    def _read_dxf_entities(self, filepath: str) -> List[dict]:
        """读取DXF文件的实体数据"""
        entities = []
        current_entity = None
        in_entities = False
        code = None

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='gbk', errors='ignore') as f:
                lines = f.readlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1

            if line == '0':
                section = lines[i].strip() if i < len(lines) else ''
                i += 1
                if section == 'ENTITIES':
                    in_entities = True
                elif section == 'ENDSEC':
                    if in_entities and current_entity:
                        entities.append(current_entity)
                    in_entities = False
                    current_entity = None
                elif in_entities:
                    # 新的实体开始
                    if current_entity:
                        entities.append(current_entity)
                    current_entity = {'type': section}
                continue

            if not in_entities:
                continue

            try:
                code = int(line)
            except ValueError:
                continue

            value = lines[i].strip() if i < len(lines) else ''
            i += 1

            if current_entity is not None:
                current_entity[code] = value

        if current_entity:
            entities.append(current_entity)

        return entities

    def _extract_pieces(self) -> List[Piece]:
        """从图层实体中提取裁片"""
        pieces = []
        contour_layer = self.config.dxf_contour_layer  # 默认 "CUT"

        # 在所有图层中寻找包含封闭多边形的图层
        candidate_layers = list(self._layers.keys())

        for layer_name in candidate_layers:
            entities = self._layers[layer_name]
            polygons = self._extract_polygons_from_layer(entities)

            for i, poly in enumerate(polygons):
                if len(poly) < 3:
                    continue
                area = self._calc_polygon_area(poly)
                if area < self.config.plt_min_piece_area:
                    continue

                piece = Piece(
                    name=f"{layer_name}_{i + 1}",
                    contour=self._normalize_points(poly),
                )
                pieces.append(piece)

        return pieces

    def _extract_polygons_from_layer(self, entities: List[dict]) -> List[List[Point]]:
        """从图层实体中提取多边形"""
        polygons = []
        current_poly = []

        for entity in entities:
            etype = entity.get('type', '')

            if etype == 'POLYLINE':
                poly_points = self._extract_polyline(entity, entities)
                if poly_points:
                    polygons.append(poly_points)

            elif etype == 'LWPOLYLINE':
                poly_points = self._extract_lwpolyline(entity)
                if poly_points:
                    polygons.append(poly_points)

            elif etype == 'LINE':
                pt1 = self._get_point(entity, '10', '20')
                pt2 = self._get_point(entity, '11', '21')
                if pt1 and pt2:
                    if not current_poly:
                        current_poly.append(pt1)
                    current_poly.append(pt2)

            elif etype == 'CIRCLE':
                center = self._get_point(entity, '10', '20')
                radius = float(entity.get('40', 0))
                if center and radius > 0:
                    # 用36段近似圆
                    circle_pts = []
                    for j in range(36):
                        angle = math.radians(j * 10)
                        circle_pts.append(Point(
                            center.x + radius * math.cos(angle),
                            center.y + radius * math.sin(angle)
                        ))
                    polygons.append(circle_pts)

            elif etype == 'ARC':
                arc_pts = self._extract_arc(entity)
                if arc_pts:
                    polygons.append(arc_pts)

        if current_poly:
            polygons.append(current_poly)

        return polygons

    def _extract_polyline(self, entity: dict, all_entities: List[dict]) -> List[Point]:
        """提取POLYLINE的顶点"""
        points = []
        # LWPOLYLINE的顶点在线内
        if entity['type'] == 'LWPOLYLINE':
            return self._extract_lwpolyline(entity)
        return points

    def _extract_lwpolyline(self, entity: dict) -> List[Point]:
        """提取LWPOLYLINE的顶点"""
        points = []
        # LWPOLYLINE使用90/10/20格式
        vertex_count = int(entity.get('90', 0))

        # 尝试另一种格式：顶点数据
        for key in sorted(entity.keys()):
            if isinstance(key, int) and key >= 10:
                x = float(entity.get(key, 0))
                y = float(entity.get(key + 10, 0)) if (key + 10) in entity else 0
                if x != 0 or y != 0:
                    points.append(Point(x, y))
        return points

    def _extract_arc(self, entity: dict) -> List[Point]:
        """提取ARC为一系列点"""
        center = self._get_point(entity, '10', '20')
        radius = float(entity.get('40', 0))
        start_angle = float(entity.get('50', 0))
        end_angle = float(entity.get('51', 360))

        if not center or radius <= 0:
            return []

        points = []
        if end_angle < start_angle:
            end_angle += 360

        segments = max(8, int(abs(end_angle - start_angle) / 5))
        for i in range(segments + 1):
            angle = math.radians(start_angle + (end_angle - start_angle) * i / segments)
            points.append(Point(
                center.x + radius * math.cos(angle),
                center.y + radius * math.sin(angle)
            ))
        return points

    def _get_point(self, entity: dict, code_x: str, code_y: str) -> Optional[Point]:
        """获取坐标点"""
        x = float(entity.get(code_x, 0))
        y = float(entity.get(code_y, 0))
        return Point(x, y) if (x or y) else None

    def _calc_polygon_area(self, points: List[Point]) -> float:
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

    def _normalize_points(self, points: List[Point]) -> List[Point]:
        """标准化：移到原点，确保闭合"""
        if not points:
            return points
        min_x = min(p.x for p in points)
        min_y = min(p.y for p in points)
        normalized = [Point(p.x - min_x, p.y - min_y) for p in points]
        if normalized[0].distance(normalized[-1]) > 0.01:
            normalized.append(Point(normalized[0].x, normalized[0].y))
        return normalized
