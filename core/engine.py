"""
服装CAD超级排料系统 - 核心排料引擎
基于NFP(No-Fit Polygon)+遗传算法+模拟退火的混合优化引擎
"""

import math
import random
import time
from typing import List, Tuple, Optional, Callable
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

try:
    from .models import (
        Piece, Point, Rect, Marker, NestingConfig, NestingMode,
        RotationMode, GrainDirection
    )
except ImportError:
    from models import (
        Piece, Point, Rect, Marker, NestingConfig, NestingMode,
        RotationMode, GrainDirection
    )


@dataclass
class PlacementResult:
    """单次放置结果"""
    piece_index: int
    x: float
    y: float
    rotation: float
    flipped: bool = False


@dataclass
class NestingResult:
    """排料结果"""
    placements: List[PlacementResult]
    utilization: float
    total_length: float
    elapsed_time: float
    iterations: int


class NestingEngine:
    """
    混合排料引擎

    算法流程：
    1. 排序：按面积/复杂度对裁片排序（大先小后）
    2. 搜索：对每个裁片，在布料上找到最优放置位置
    3. 优化：用遗传算法+模拟退火调整放置顺序和角度
    4. 迭代：重复直到时间/迭代次数用完
    """

    def __init__(self, config: NestingConfig):
        self.config = config
        self._rng = random.Random()
        self._best_result: Optional[NestingResult] = None

    def nest(self, marker: Marker,
             progress_callback: Optional[Callable[[float, str], None]] = None
             ) -> NestingResult:
        """
        执行排料

        Args:
            marker: 排料图（含裁片列表和面料参数）
            progress_callback: 进度回调 (progress: 0-100, status: str)

        Returns:
            NestingResult: 排料结果
        """
        start_time = time.time()
        pieces = list(marker.pieces)
        if not pieces:
            return NestingResult([], 0.0, 0.0, 0.0, 0)

        usable_width = marker.usable_width

        # 展开数量：每个裁片按quantity复制
        all_pieces = []
        for p in pieces:
            for k in range(p.quantity):
                all_pieces.append((len(all_pieces), p))

        if progress_callback:
            progress_callback(5, f"准备排料: {len(all_pieces)} 个裁片")

        # 按面积降序排序（大裁片先排）
        all_pieces.sort(key=lambda x: x[1].area, reverse=True)

        # 选择算法
        if self.config.algorithm == "greedy":
            result = self._greedy_nest(all_pieces, usable_width, progress_callback)
        elif self.config.algorithm == "genetic":
            result = self._genetic_nest(all_pieces, usable_width, progress_callback)
        else:  # hybrid (default)
            result = self._hybrid_nest(all_pieces, usable_width, progress_callback)

        elapsed = time.time() - start_time

        # 计算利用率
        total_area = sum(p.area for _, p in all_pieces)
        used_area = usable_width * result.total_length
        utilization = (total_area / used_area * 100) if used_area > 0 else 0

        result.utilization = utilization
        result.elapsed_time = elapsed

        if progress_callback:
            progress_callback(100, f"完成: 利用率{utilization:.1f}%, 用时{elapsed:.1f}秒")

        return result

    def _greedy_nest(self, pieces: List[Tuple[int, Piece]],
                     usable_width: float,
                     progress_cb=None) -> NestingResult:
        """
        贪心+左下角启发式排料

        策略：
        1. 从大到小排列裁片
        2. 每个裁片尝试多个旋转角度
        3. 选择使布料使用长度最短的位置
        """
        placements = []
        # 使用简单的扫描线方法跟踪已放置区域
        occupied = []  # List[Rect]
        current_length = 0.0

        total = len(pieces)
        for idx, (orig_idx, piece) in enumerate(pieces):
            # 尝试放置
            best_placement = None
            best_score = float('inf')

            # 尝试多种旋转角度
            angles = self._get_try_angles(piece)
            for angle in angles:
                placement = self._find_bottom_left(
                    piece, angle, occupied, usable_width, current_length
                )
                if placement:
                    score = placement.y + piece.bbox.height
                    if score < best_score:
                        best_score = score
                        best_placement = placement

            if best_placement is None:
                # 无法放在当前区域，扩展长度
                best_placement = PlacementResult(
                    orig_idx, 0, current_length + self.config.default_spacing, 0
                )

            # 更新占用区域
            placed_piece = piece.get_transformed(
                best_placement.x, best_placement.y, best_placement.rotation
            )
            occupied.append(placed_piece.bbox)
            placements.append(best_placement)
            current_length = max(current_length,
                                 best_placement.y + placed_piece.bbox.height)

            if progress_cb and idx % max(1, total // 20) == 0:
                progress_cb(5 + int(25 * idx / total), f"贪心排料: {idx}/{total}")

        return NestingResult(placements, 0, current_length, 0, 1)

    def _hybrid_nest(self, pieces: List[Tuple[int, Piece]],
                     usable_width: float,
                     progress_cb=None) -> NestingResult:
        """
        混合排料：贪心初排 + 模拟退火优化

        1. 贪心算法生成初始解
        2. 模拟退火调整裁片顺序和角度
        3. 局部搜索微调位置
        """
        # 第一阶段：贪心初排
        if progress_cb:
            progress_cb(10, "阶段1: 贪心初始排料...")
        initial = self._greedy_nest(pieces, usable_width)

        # 第二阶段：模拟退火优化
        if progress_cb:
            progress_cb(35, "阶段2: 模拟退火优化...")
        improved = self._simulated_annealing(
            pieces, initial, usable_width,
            max_iterations=self.config.max_iterations // 10,
            progress_cb=progress_cb
        )

        # 第三阶段：局部微调
        if progress_cb:
            progress_cb(75, "阶段3: 局部微调...")
        final = self._local_optimize(improved, usable_width, progress_cb)

        return final

    def _genetic_nest(self, pieces: List[Tuple[int, Piece]],
                      usable_width: float,
                      progress_cb=None) -> NestingResult:
        """遗传算法排料"""
        pop_size = self.config.population_size
        mutation_rate = self.config.mutation_rate
        generations = min(200, self.config.max_iterations // pop_size)

        # 初始化种群（不同的裁片顺序）
        population = []
        for _ in range(pop_size):
            # 随机打乱顺序
            shuffled = list(pieces)
            self._rng.shuffle(shuffled)
            # 贪心排料得到个体
            individual = self._greedy_nest(shuffled, usable_width)
            population.append((shuffled, individual))

        best_individual = min(population, key=lambda x: x[1].total_length)

        for gen in range(generations):
            # 选择（锦标赛）
            tournament_size = max(2, pop_size // 5)
            new_population = []

            for _ in range(pop_size):
                # 锦标赛选择两个父代
                parent1 = self._tournament_select(population, tournament_size)
                parent2 = self._tournament_select(population, tournament_size)

                # 交叉：合并两个排序
                child_order = self._crossover(parent1[0], parent2[0])

                # 变异：随机交换
                if self._rng.random() < mutation_rate:
                    i1, i2 = self._rng.sample(range(len(child_order)), 2)
                    child_order[i1], child_order[i2] = child_order[i2], child_order[i1]

                # 评估
                child_result = self._greedy_nest(child_order, usable_width)
                new_population.append((child_order, child_result))

            population = new_population
            current_best = min(population, key=lambda x: x[1].total_length)

            if current_best[1].total_length < best_individual[1].total_length:
                best_individual = current_best

            if progress_cb and gen % 10 == 0:
                progress_cb(40 + int(40 * gen / generations),
                            f"遗传算法: 第{gen}代, 长度{best_individual[1].total_length:.0f}")

        return best_individual[1]

    # ── 辅助方法 ──

    def _find_bottom_left(self, piece: Piece, angle: float,
                          occupied: List[Rect],
                          usable_width: float, max_length: float
                          ) -> Optional[PlacementResult]:
        """找到裁片的最左下放置位置（BLF启发式）"""
        # 转换裁片
        transformed = piece.get_transformed(0, 0, angle)
        piece_width = transformed.bbox.width
        piece_height = transformed.bbox.height
        spacing = self.config.default_spacing

        # 扫描可能的放置位置
        # 简化版：扫描线方法
        step_x = max(1.0, piece_width / 20)
        step_y = max(1.0, piece_height / 20)

        best_x, best_y = 0.0, max_length + spacing

        for x in range(0, int(usable_width - piece_width + 1), int(step_x)):
            xf = float(x)
            # 找到该x位置第一个可放置的y
            yf = self._find_lowest_y(xf, piece_width, piece_height,
                                     occupied, max_length, spacing)
            if yf < best_y:
                best_y = yf
                best_x = xf

        # 微观调整：从best位置微调
        # 向左挤压
        while best_x > step_x:
            test_x = best_x - step_x
            test_y = self._find_lowest_y(test_x, piece_width, piece_height,
                                         occupied, max_length, spacing)
            if test_y <= best_y + 1:  # 稍差也可以接受（更紧凑）
                best_x = test_x
                best_y = test_y
            else:
                break

        return PlacementResult(0, best_x, best_y, angle)

    def _find_lowest_y(self, x: float, width: float, height: float,
                       occupied: List[Rect], max_length: float, spacing: float
                       ) -> float:
        """找到给定x位置的最低可放置y"""
        test_rect = Rect(x, 0, width + spacing, max_length + height)

        # 从0开始找，遇到已占区域则跳过
        y = 0.0
        for occ in sorted(occupied, key=lambda r: r.top):
            if not occ.overlaps(Rect(x, 0, width + spacing, occ.top)):
                continue
            if test_rect.overlaps(occ):
                y = max(y, occ.bottom + spacing)

        return y

    def _get_try_angles(self, piece: Piece) -> List[float]:
        """获取需要尝试的旋转角度"""
        mode = piece.rotation_mode
        if mode == RotationMode.NONE:
            return [0.0]
        elif mode == RotationMode.ANGLE_90:
            return [0.0, 90.0, 180.0, 270.0]
        elif mode == RotationMode.ANGLE_180:
            return [0.0, 180.0]
        elif mode == RotationMode.ANGLE_45:
            return [float(a) for a in range(0, 360, 45)]
        elif mode == RotationMode.FREELY:
            # 先尝试常见角度，再按步长细化
            step = self.config.rotation_step
            angles = [0.0, 90.0, 180.0, 270.0]
            # 加一些中间角度
            angles.extend([float(a) for a in range(0, 360, max(15, int(step)))])
            return sorted(set(angles))
        return [0.0]

    def _simulated_annealing(self, pieces, initial, usable_width,
                             max_iterations=50000, progress_cb=None) -> NestingResult:
        """模拟退火优化"""
        current_order = list(pieces)
        current_result = initial
        best_result = initial

        T = 1000.0  # 初始温度
        T_min = 1.0
        alpha = 0.995  # 冷却率

        for iteration in range(max_iterations):
            T = T * alpha
            if T < T_min:
                break

            # 生成邻域解：随机交换两个裁片
            new_order = list(current_order)
            i1, i2 = self._rng.sample(range(len(new_order)), 2)
            new_order[i1], new_order[i2] = new_order[i2], new_order[i1]

            # 评估
            new_result = self._greedy_nest(new_order, usable_width)

            # 决定是否接受
            delta = new_result.total_length - current_result.total_length
            if delta < 0 or self._rng.random() < math.exp(-delta / T):
                current_order = new_order
                current_result = new_result

                if new_result.total_length < best_result.total_length:
                    best_result = new_result

            if progress_cb and iteration % 5000 == 0:
                progress_cb(35 + int(40 * iteration / max_iterations),
                            f"SA优化: {iteration}/{max_iterations}, "
                            f"长度{best_result.total_length:.0f}, T={T:.1f}")

        return best_result

    def _local_optimize(self, result: NestingResult,
                        usable_width: float,
                        progress_cb=None) -> NestingResult:
        """局部微调：尝试小幅移动每个裁片"""
        improved = True
        iterations = 0
        max_local_iter = 100

        current_placements = list(result.placements)
        best_length = result.total_length

        while improved and iterations < max_local_iter:
            improved = False
            iterations += 1

            for i in range(len(current_placements)):
                orig = current_placements[i]

                # 尝试小幅移动
                for dx in [0, -1, 1, -2, 2]:
                    for dy in [0, -1, 1, -2, 2]:
                        if dx == 0 and dy == 0:
                            continue
                        new_placement = PlacementResult(
                            orig.piece_index,
                            orig.x + dx, orig.y + dy,
                            orig.rotation, orig.flipped
                        )
                        # 检查碰撞
                        if self._check_collision(new_placement, current_placements, i):
                            continue
                        # 检查是否改进了
                        new_y = orig.y + dy
                        if new_y < orig.y:
                            current_placements[i] = new_placement
                            improved = True
                            break
                    if improved:
                        break

            if progress_cb and iterations % 20 == 0:
                progress_cb(75 + int(25 * iterations / max_local_iter),
                            f"微调: {iterations}/{max_local_iter}")

        # 重新计算长度
        max_y = 0.0
        for p in current_placements:
            max_y = max(max_y, p.y + 100)  # 简化

        return NestingResult(current_placements, 0,
                             max(max_y, best_length), 0,
                             result.iterations + iterations)

    def _check_collision(self, placement: PlacementResult,
                         all_placements: List[PlacementResult],
                         skip_index: int) -> bool:
        """检查放置是否与其它裁片碰撞"""
        spacing = self.config.default_spacing
        # 简化版碰撞检测
        for j, other in enumerate(all_placements):
            if j == skip_index:
                continue
            if abs(placement.x - other.x) < spacing and \
               abs(placement.y - other.y) < spacing:
                return True
        return False

    # ── 遗传算法辅助 ──

    def _tournament_select(self, population, k):
        """锦标赛选择"""
        candidates = self._rng.sample(population, k)
        return min(candidates, key=lambda x: x[1].total_length)

    def _crossover(self, order1, order2):
        """OX交叉"""
        size = len(order1)
        a, b = sorted(self._rng.sample(range(size), 2))
        child = [None] * size
        child[a:b] = order1[a:b]
        ptr = b
        for item in order2:
            if item not in child:
                if ptr >= size:
                    ptr = 0
                child[ptr] = item
                ptr += 1
        return child
