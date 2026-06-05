# 服装CAD超级排料系统 V1.0

开源免费的服装CAD超级排料软件。支持PLT/DXF文件，兼容Win7，免加密。

## 功能特性

### 文件支持
- ✅ PLT (HP-GL) 文件导入/导出
- ✅ DXF (R12-2018) 文件导入
- ✅ 多码多件批量排料

### 排料算法
- ✅ 混合算法（NFP + 遗传算法 + 模拟退火）
- ✅ 贪心快速排料
- ✅ 遗传算法深度优化
- ✅ 多种旋转模式（自由/90°/180°/45°）
- ✅ 裁片间距控制
- ✅ 面料利用率实时计算

### 工艺支持
- ✅ 倒顺毛排料
- ✅ 对条格排料
- ✅ 捆绑排料
- ✅ 避色差排料
- ✅ 多种分段排料模式

### 系统特性
- ✅ 兼容 Windows 7/8/10/11
- ✅ 免加密，自由使用
- ✅ 暗色主题UI

## 安装

### Windows 用户

```bash
# 1. 安装 Python 3.8+ (Win7用3.8)
# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动
python main.py
```

### 打包为EXE

```bash
pip install pyinstaller
python build_exe.py
# EXE文件在 dist/ 目录下
```

## 使用指南

### GUI模式
1. 双击 `main.py` 或打包好的 exe
2. 点击「导入PLT」或「导入DXF」加载裁片
3. 设置面料幅宽
4. 点击「开始超级排料」
5. 查看排料结果，导出文件

### 命令行模式
```bash
python main.py sample.plt -w 1500 -a hybrid -o result.plt
```

### 快捷键
- `F5` - 开始排料
- `Ctrl+P` - 导入PLT
- `Ctrl+D` - 导入DXF
- `Ctrl+E` - 导出结果

## 项目结构

```
super_nesting/
├── main.py               # 主入口
├── requirements.txt      # 依赖列表
├── build_exe.py          # 打包脚本
├── core/
│   ├── models.py         # 数据模型
│   └── engine.py         # 排料引擎
├── parsers/
│   ├── plt_parser.py     # PLT解析器
│   └── dxf_parser.py     # DXF解析器
├── gui/
│   └── main_window.py    # 主界面
├── tests/
│   └── test_basic.py     # 测试
└── config/               # 配置文件
```

## 技术参数

| 参数 | 值 |
|------|-----|
| 算法 | NFP + 遗传算法 + 模拟退火 |
| 精度 | 0.01mm |
| 最大裁片数 | 无限制 |
| PLT分辨率 | 1016 dpi |
| 闭合误差 | 0.5mm |
| 最小裁片面积 | 25mm² |

## License

MIT - 自由使用，免加密
