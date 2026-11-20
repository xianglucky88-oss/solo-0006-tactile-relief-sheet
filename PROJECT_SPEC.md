# 双面触感压印数据预检：基线契约

## 数据流程

将正背版绘制坐标注册到同一张纸，输出禁区、越界和凸点间距冲突。 输入字段以 `examples/demo.json` 为最小可运行的实际示例。

格点从 0 开始；背版先水平镜像再叠加偏移。矩形左闭右开；点距为两个轴差的最大值。

## 责任边界

命令入口只处理文件输入和退出码。`pipeline.py` 协调校验、数据计算和报告；其余模块负责独立的数据语义。生产代码：`reliefsheet/__main__.py`, `reliefsheet/clearance.py`, `reliefsheet/pipeline.py`, `reliefsheet/plates.py`。

## 验证与边界

运行 `python3 -B examples/smoke.py`。样例经过真实生产入口，既核对核心数据结果也核对非零退出码及不输出部分数据的约束。不安装第三方依赖，不提交未来题目、答案、隐藏测试或评审材料。
