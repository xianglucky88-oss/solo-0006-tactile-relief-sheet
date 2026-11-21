# 双面触感压印数据预检

将正背版绘制坐标注册到同一张纸，输出禁区、越界和凸点间距冲突。 这是处理合成数据的离线参考应用，不依赖网络、数据库服务或第三方库。

```sh
python3 -B -m reliefsheet examples/demo.json
python3 -B -m reliefsheet examples/heads.json
python3 -B -m reliefsheet examples/heads.json --replace-head 'dual-pad:0,-2,2,1'
python3 -B examples/smoke.py
```

需要 Python 3.9+。传入任意匹配契约的 UTF-8 JSON 文件，输出 JSON 写到标准输出；非法输入使用退出码 2，诊断写到标准错误。业务上发现冲突仍会产生完整分析结果。完整测试套件暂缓；随仓冒烟样例从实际命令行入口验证有效结果与输入拒绝。

格点从 0 开始；背版先水平镜像再叠加偏移。矩形左闭右开；点距为两个轴差的最大值。混排压头时，点在 `head` 中选型号，型号在 `heads` 中给出相对标记的半开占位矩形（必须含原标记格，可不对称），未选型号的点仍是单格；占位随标记一起套准到纸面后按实占格查边界、禁区和点对距离。替换型号时用 `--replace-head`，只输出受影响证据的 `added`/`removed`/`changed` 三类结果。 详见 [项目说明](PROJECT_SPEC.md) 和 [输入样例](examples/demo.json)、[压头样例](examples/heads.json)。
