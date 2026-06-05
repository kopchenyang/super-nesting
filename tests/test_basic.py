"""
基础功能测试
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import (
    Point, Rect, Piece, Marker, NestingConfig, NestingMode,
    RotationMode, GrainDirection
)
from core.engine import NestingEngine


def test_models():
    """测试数据模型"""
    # 创建一个简单的裁片
    contour = [
        Point(0, 0), Point(100, 0), Point(100, 50),
        Point(60, 50), Point(60, 80), Point(0, 80)
    ]
    piece = Piece("测试裁片", contour, quantity=2, size_code="L")

    assert piece.area > 0
    assert piece.bbox.width == 100
    assert piece.bbox.height == 80
    print("✅ 数据模型测试通过")


def test_engine():
    """测试排料引擎"""
    config = NestingConfig()
    config.algorithm = "greedy"
    config.default_spacing = 2.0
    config.time_limit_seconds = 10

    # 创建一些测试裁片
    pieces = []
    for i in range(5):
        w, h = [80, 120, 60, 100, 90][i], [40, 60, 50, 70, 55][i]
        contour = [Point(0, 0), Point(w, 0), Point(w, h), Point(0, h)]
        piece = Piece(f"裁片{i + 1}", contour, quantity=1)
        pieces.append(piece)

    marker = Marker(
        name="测试排料",
        fabric_width=1500,
        pieces=pieces,
    )

    engine = NestingEngine(config)
    result = engine.nest(marker)

    assert len(result.placements) == len(pieces)
    assert result.utilization > 0
    assert result.elapsed_time >= 0
    print(f"✅ 排料引擎测试通过 (利用率: {result.utilization:.1f}%, "
          f"用时: {result.elapsed_time:.2f}秒)")


def test_plt_parser():
    """测试PLT解析器"""
    from parsers.plt_parser import PLTParser

    config = NestingConfig()
    parser = PLTParser(config)

    # 构造最小PLT文件
    plt_content = """
    IN;SP1;
    PU1000,1000;
    PD2000,1000;
    PD2000,1500;
    PD1000,1500;
    PD1000,1000;
    PU0,0;
    SP0;
    """

    pieces = parser.parse(plt_content)
    print(f"✅ PLT解析测试通过 ({len(pieces)} 个裁片)")


if __name__ == "__main__":
    print("服装CAD超级排料系统 - 测试\n")
    test_models()
    test_engine()
    test_plt_parser()
    print("\n🎉 所有测试通过!")
