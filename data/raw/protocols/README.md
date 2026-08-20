# 原始协议目录

只放置可追溯的权威原始协议候选。原文件不可覆盖；来源、版本、正文和许可证
完成核验前不得进入正式知识库。

正式数据不应使用 `data/processed/sample_protocols.jsonl`；该文件仅用于
smoke test。

## 当前候选来源

`协议来源登记_v0.1.jsonl` 当前登记15份权威材料。文件已经下载到
`原始文件/`，但全部保持 `status=draft`、`content_review_status=pending` 和
`license_status=pending_manual_confirmation`。

这些文件不能直接作为正式知识库。当前只允许生成：

```text
data/processed/候选协议切块_v0.1.jsonl
```

可复现命令：

```powershell
python scripts\下载权威协议源.py `
  --registry data\raw\protocols\协议来源登记_v0.1.jsonl `
  --report data\logs\权威协议源下载报告_v0.2.json

python scripts\回填协议文件哈希.py `
  --registry data\raw\protocols\协议来源登记_v0.1.jsonl `
  --report data\logs\权威协议源下载报告_v0.2.json

$env:PYTHONPATH = "$PWD\src"
python -m sci_exp.cli prepare-protocols `
  --registry data\raw\protocols\协议来源登记_v0.1.jsonl `
  --output data\processed\候选协议切块_v0.1.jsonl `
  --target-characters 600 `
  --overlap-characters 80

python scripts\审计候选协议.py `
  --input data\processed\候选协议切块_v0.1.jsonl `
  --output data\logs\候选协议切块审计_v0.1.json
```

人工审查要求见 `docs/权威协议来源与内容审计_v0.1.md` 和
`data/annotations/协议内容审查表_v0.1.csv`。

## 章节级精选候选

原始宽范围切块仅用于审计。先导证据绑定使用可复现章节规则从13份来源生成
64条精选候选；另2份专业/英文材料排除直接检索：

```powershell
python scripts\生成协议派生候选.py `
  --registry data\raw\protocols\协议来源登记_v0.1.jsonl `
  --rules data\raw\protocols\协议章节筛选规则_v0.1.jsonl `
  --derived-directory data\processed\协议派生文本_v0.1 `
  --derived-registry data\processed\协议派生登记_v0.1.jsonl `
  --chunks data\processed\精选候选协议切块_v0.1.jsonl `
  --report data\logs\协议派生候选报告_v0.1.json `
  --target-characters 600 `
  --overlap-characters 80

python scripts\审计候选协议.py `
  --input data\processed\精选候选协议切块_v0.1.jsonl `
  --output data\logs\精选候选协议切块审计_v0.1.json
```

派生登记中的文件路径采用相对路径，可随整个 `sci-exp` 复制到
`/home/radxa/sci-exp`。派生文件和切块仍然待双审、待许可证确认。
