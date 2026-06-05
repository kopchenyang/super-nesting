"""
服装CAD超级排料系统 - 核心数据模型
Copyright (c) 2026 SuperNesting. All rights reserved.
License: MIT (免加密，自由使用)
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from enum import Enum, IntEnum
import math


class GrainDirection(IntEnum):
    """纱向（布纹方向）"""
    BIDIRECTIONAL = 0    # 双向
    UNIDIRECTIONAL = 1   # 单向（倒顺毛）
    NONE = 2             # 无要求


class RotationMode(IntEnum):
    """旋转模式"""
    NONE = 0             # 禁止旋转
    FREELY = 1           # 自由旋转
    ANGLE_90 = 2         # 仅90度旋转
    ANGLE_180 = 3        # 仅180度旋转
    ANGLE_45 = 4         # 45度增量
    ANGLE_CUSTOM = 5     # 自定义角度


class NestingMode(IntEnum):
    """排料模式"""
    MIXED = 0            # 混合超排
    SINGLE_PIECE = 1     # 单件分段
    SINGLE_SIZE = 2      # 单码分段
    SINGLE_PART = 3      # 单片分段
    CUSTOM_SEGMENT = 4   # 自定义分段
    BEST_WIDTH = 5       # 最佳幅宽
    DISTANCE_SEGMENT = 6 # 距离分段
    DEFECT_AVOID = 7     # 避瑕疵


@dataclass
class Point:
    """2D点"""
    x: float
    y: float

    def __add__(self, other: 'Point') -> 'Point':
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: 'Point') -> 'Point':
        return Point(self.x - other.x, self.y - other.y)

    def __mul__(self, scale: float) -> 'Point':
        return Point(self.x * scale, self.y * scale)

    def distance(self, other: 'Point') -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def rotate(self, angle_deg: float, center: 'Point' = None) -> 'Point':
        """绕指定点旋转"""
        if center is None:
            center = Point(0, 0)
        rad = math.radians(angle_deg)
        dx, dy = self.x - center.x, self.y - center.y
        return Point(
            center.x + dx * math.cos(rad) - dy * math.sin(rad),
            center.y + dx * math.sin(rad) + dy * math.cos(rad)
        )

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


@dataclass
class Rect:
    """矩形区域"""
    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float: return self.x

    @property
    def right(self) -> float: return self.x + self.width

    @property
    def top(self) -> float: return self.y

    @property
    def bottom(self) -> float: return self.y + self.height

    @property
    def area(self) -> float: return self.width * self.height

    def overlaps(self, other: 'Rect') -> bool:
        return (self.left < other.right and self.right > other.left and
                self.top < other.bottom and self.bottom > other.top)

    def contains(self, point: Point) -> bool:
        return (self.left <= point.x <= self.right and
                self.top <= point.y <= self.bottom)


@dataclass
class Notch:
    """刀口/对位标记"""
    position: Point
    angle: float = 0.0         # 刀口方向角
    notch_type: str = "V"      # V型 / U型 / I型
    width: float = 3.0         # 刀口宽度(mm)
    depth: float = 2.0         # 刀口深度(mm)


@dataclass
class Drill:
    """钻孔标记（给自动裁床用）"""
    position: Point
    diameter: float = 2.0      # 钻孔直径(mm)


@dataclass
class Piece:
    """衣片（裁片）"""
    name: str                           # 名称（如"前片L"）
    contour: List[Point]                # 外轮廓点列表（封闭）
    inner_lines: List[List[Point]] = field(default_factory=list)  # 内部线
    grain_line: Tuple[Point, Point] = None  # 纱向线（起点,终点）
    notches: List[Notch] = field(default_factory=list)  # 刀口
    drills: List[Drill] = field(default_factory=list)    # 钻孔

    # 工艺属性
    quantity: int = 1                   # 数量
    size_code: str = "M"                # 尺码
    fabric_type: str = ""               # 面料类型
    rotation_mode: RotationMode = RotationMode.FREELY
    grain_direction: GrainDirection = GrainDirection.BIDIRECTIONAL
    max_tilt_angle: float = 0.0         # 最大倾斜角度（度）
    allow_overlap: bool = False         # 是否允许重叠（压角）
    is_bundled: bool = False            # 捆绑排料
    bundle_group: int = 0               # 捆绑组号
    color_group: int = 0                # 色差组号

    # 计算属性缓存
    _bbox: Optional[Rect] = None
    _area: Optional[float] = None
    _convex_hull: Optional[List[Point]] = None

    @property
    def bbox(self) -> Rect:
        """包围盒"""
        if self._bbox is None:
            xs = [p.x for p in self.contour]
            ys = [p.y for p in self.contour]
            self._bbox = Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        return self._bbox

    @property
    def area(self) -> float:
        """多边形面积（Shoelace公式）"""
        if self._area is None:
            n = len(self.contour)
            area = 0.0
            for i in range(n):
                j = (i + 1) % n
                area += self.contour[i].x * self.contour[j].y
                area -= self.contour[j].x * self.contour[i].y
            self._area = abs(area) / 2.0
        return self._area

    def get_transformed(self, dx: float = 0, dy: float = 0,
                         angle: float = 0, scale: float = 1.0,
                         flip_x: bool = False, flip_y: bool = False) -> 'Piece':
        """获取变换后的裁片副本"""
        if angle == 0 and scale == 1.0 and not flip_x and not flip_y:
            return Piece(
                name=self.name,
                contour=[Point(p.x + dx, p.y + dy) for p in self.contour],
                inner_lines=[[Point(p.x + dx, p.y + dy) for p in line]
                             for line in self.inner_lines],
                grain_line=((Point(self.grain_line[0].x + dx, self.grain_line[0].y + dy),
                             Point(self.grain_line[1].x + dx, self.grain_line[1].y + dy))
                            if self.grain_line else None),
                notches=[Notch(Point(n.position.x + dx, n.position.y + dy),
                               n.angle, n.notch_type, n.width, n.depth)
                         for n in self.notches],
                quantity=self.quantity, size_code=self.size_code,
                rotation_mode=self.rotation_mode,
                grain_direction=self.grain_direction,
                max_tilt_angle=self.max_tilt_angle,
                color_group=self.color_group,
            )

        # 复杂变换
        center = Point(0, 0)
        new_contour = []
        for p in self.contour:
            np = Point(p.x * (1 if not flip_x else -1), p.y * (1 if not flip_y else -1))
            np = np.rotate(angle, center)
            np = Point(np.x * scale + dx, np.y * scale + dy)
            new_contour.append(np)
        return Piece(name=self.name, contour=new_contour,
                     quantity=self.quantity, size_code=self.size_code,
                     rotation_mode=self.rotation_mode)


@dataclass
class Marker:
    """排料图（唛架）"""
    name: str                           # 排料图名称
    fabric_width: float                 # 面料幅宽(mm)
    fabric_length: float = 50000.0      # 面料长度(mm)
    pieces: List[Piece] = field(default_factory=list)
    placed_pieces: List[Tuple[Piece, float, float, float]] = field(default_factory=list)
    # (裁片, x, y, 旋转角度)

    # 排料参数
    nesting_mode: NestingMode = NestingMode.MIXED
    spacing: float = 2.0                # 裁片间距(mm)
    margin_left: float = 10.0           # 左边距
    margin_right: float = 10.0          # 右边距
    margin_top: float = 10.0            # 上边距
    margin_bottom: float = 10.0         # 下边距

    # 面料参数
    fabric_type: str = ""               # 面料类型
    has_stripe: bool = False            # 有条纹
    stripe_spacing: float = 0.0         # 条纹间距
    has_check: bool = False             # 有格纹
    check_spacing_x: float = 0.0        # 格纹X间距
    check_spacing_y: float = 0.0        # 格纹Y间距
    is_napped: bool = False             # 倒顺毛面料

    @property
    def usable_width(self) -> float:
        return self.fabric_width - self.margin_left - self.margin_right

    @property
    def total_area(self) -> float:
        return self.fabric_width * self.fabric_length

    @property
    def utilization(self) -> float:
        """面料利用率"""
        if not self.placed_pieces:
            return 0.0
        total_piece_area = sum(piece.area for piece, _, _, _ in self.placed_pieces)
        used_length = max(
            (piece.bbox.bottom + self.spacing for piece, _, y, _ in self.placed_pieces),
            default=0
        )
        used_area = self.fabric_width * used_length
        return (total_piece_area / used_area * 100) if used_area > 0 else 0.0


@dataclass
class NestingConfig:
    """排料系统配置"""
    # 通用设置
    unit: str = "mm"                    # 单位
    precision: int = 2                  # 精度（小数位）
    language: str = "zh_CN"             # 语言

    # 算法参数
    algorithm: str = "hybrid"           # hybrid | genetic | greedy | simulated_annealing
    max_iterations: int = 500000        # 最大迭代次数
    population_size: int = 100          # 种群大小（遗传算法）
    mutation_rate: float = 0.1          # 变异率
    time_limit_seconds: int = 300       # 时间限制（秒）
    early_stop_no_improve: int = 50     # 无改善早停代数

    # 排料参数
    default_spacing: float = 2.0        # 默认间距
    min_piece_distance: float = 1.0     # 最小裁片间距
    max_overlap_area: float = 0.0       # 最大允许重叠面积
    max_rotation_angle: float = 180.0   # 最大旋转角度
    rotation_step: float = 1.0          # 旋转步长（度）

    # PLT解析参数
    plt_resolution: int = 1016          # PLT分辨率(dpi)
    plt_close_tolerance: float = 0.5    # PLT闭合误差(mm)
    plt_min_piece_area: float = 25.0    # 最小裁片面积(mm²)
    plt_segment_distance: float = 50.0  # 分码距离(mm)

    # DXF解析参数
    dxf_units: str = "mm"               # DXF单位
    dxf_contour_layer: str = "CUT"      # 轮廓图层名
    dxf_inner_layer: str = "INNER"      # 内部线图层名
    dxf_notch_layer: str = "NOTCH"      # 刀口图层名

    # 显示参数
    bg_color: str = "#1a1a2e"           # 背景色
    fabric_color: str = "#2d2d44"       # 面料色
    piece_colors: List[str] = field(default_factory=lambda: [
        "#4ecdc4", "#ff6b6b", "#45b7d1", "#f9ca24",
        "#6c5ce7", "#a29bfe", "#fd79a8", "#00b894"
    ])
    show_grid: bool = True
    grid_size: float = 100.0

    # 输出参数
    output_format: str = "PLT"          # PLT | DXF | PDF
    output_resolution: int = 1016
    include_notches: bool = True
    include_drills: bool = True
    include_labels: bool = True
