# Pilot 数据

只保存培训和独立试标。所有文件必须标记 `annotation_phase=PILOT`，不得进入正式训练、
校准或测试。培训题和准入试标题必须使用不同 query ID 集合。

`pipeline_test_A.csv` 和 `pipeline_test_B.csv` 是纯管线占位数据，只用于验证统计脚本；其
查询、标签和 ID 均不是协议 Gold，也不能作为培训参考答案。
