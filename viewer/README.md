# LLM 量化论文本地阅读页

## 功能
- 读取 `../papers_record.xlsx` 并转换为 `papers_data.json`
- 本地静态页面展示论文卡片
- 按日期区间筛选（抓取日期或发表日期）
- 支持关键词检索（标题/作者/单位/分类/摘要）
- 收藏保存在服务器端 `favorites.json`，多个浏览器访问可共享

## 启动
在本目录执行：

```bash
/home/wsg/.hermes/hermes-agent/venv/bin/python run_viewer.py
```

如果端口被占用，可换端口启动：

```bash
/home/wsg/.hermes/hermes-agent/venv/bin/python run_viewer.py --port 7770
```

浏览器打开：

```text
http://127.0.0.1:8765
```

局域网设备可访问：

```text
http://<你的机器局域网IP>:8765
```

启动后终端会打印实际 LAN 访问地址。

## 仅更新数据

```bash
/home/wsg/.hermes/hermes-agent/venv/bin/python build_data.py
```
