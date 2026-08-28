# 分歧仲裁与冻结 SOP

## 1. 仲裁输入

领域仲裁者 C 接收：

- 冻结查询和 observable context；
- A/B 原始标签及各自 rationale；
- 当前协议语料、来源卡和证据全文；
- 当前风险/动作/约束本体；
- 一致性报告生成的分歧字段清单。

C 不需要看到模型输出、配置、能耗、风险分数或论文期望方向。

## 2. 必须仲裁的项目

- 任一 categorical 字段不一致；
- 任一集合字段不一致；
- A/B 任一方标记 evidence gap、ontology gap 或协议冲突；
- S3 与非 S3、升级 YES 与 NO 的分歧；
- required/critical/prohibited 的任何冲突；
- evidence ID 的版本、对象、辖区或直接支持关系存疑；
- 一致性报告列出的全部严重分歧。

此外，C 应复核 100% 的 S3、100% 的 `escalation_required=YES`、100% evidence gap，以及
至少 10% 的低风险一致项。抽检比例可在正式协议中提高，不得事后因为结果好看而降低。

## 3. 仲裁原则

1. 以冻结协议证据为首要依据，不以多数票为依据；
2. 不把 C 的个人经验自动写入 Gold；
3. 若个人经验提示协议有缺口，标记 protocol gap 并启动语料变更流程；
4. 无法确定时允许保留 Unknown、evidence gap 或 exclude；
5. 不强迫每条记录得到确定答案；
6. 任何手册/本体变更必须递增版本并评估是否影响整批记录。

## 4. 仲裁记录字段

每条仲裁记录应包含：

- `query_id`；
- `disputed_fields`；
- `reviewer_a_value`；
- `reviewer_b_value`；
- `final_value`；
- `decision`：A/B/NEW/UNRESOLVED/EXCLUDE；
- `supporting_evidence_ids`；
- `adjudication_reason`；
- `protocol_gap`；
- `manual_or_ontology_change_required`；
- `adjudicator_id`；
- `adjudicated_at`。

选择 NEW 时必须解释为何 A/B 均不正确。选择 UNRESOLVED 或 EXCLUDE 时不得进入需要确定
标签的监督目标。

## 5. 变更影响评估

如果仲裁发现定义或本体错误：

1. 暂停当前批次冻结；
2. 发布手册/本体新版本；
3. 列出受影响的全部 query ID，而不仅是当前分歧项；
4. 由 A/B 在不知道对方答案的情况下重新标注受影响项；
5. 生成新的原始文件版本和一致性报告；
6. 保留旧文件和变更原因。

## 6. 最终 Gold 合并

P 根据 A/B 和仲裁文件生成最终 Gold，不能直接手工复制粘贴。每个最终字段必须可追溯为：

- `AGREED_AB`：A/B 原始一致；
- `ADJUDICATED_TO_A`；
- `ADJUDICATED_TO_B`；
- `ADJUDICATED_NEW`；
- `UNRESOLVED`；
- `EXCLUDED`。

## 7. 冻结门禁

冻结前必须完成：

- A/B 文件、仲裁文件、统计报告均有 SHA-256；
- 全部 query ID 一一对应；
- 无未处理内容分歧；
- 无 required/prohibited 交集；
- critical 是 required 子集；
- evidence ID 和 span 均存在；
- 高风险复核和低风险抽检完成；
- 用途、分区和 `source_group_id` 隔离通过；
- C、S、T 的审核状态已记录；
- 伦理/隐私状态已确认；
- 最终文件通过 JSON Schema；
- 冻结 manifest 记录 Git commit、版本和时间。

冻结后的文件只读保存。任何修改生成新版本，禁止覆盖。

