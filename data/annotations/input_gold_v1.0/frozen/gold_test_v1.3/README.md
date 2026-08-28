# Gold Test v1.3（范围限定）

- `gold_test_v1.3.csv`：12条正式监督/评估记录。
- `gold_uncertainty_challenge_v1.3.csv`：5条不确定性挑战记录，不进入确定监督目标。
- `gold_excluded_pending_v1.3.csv`：8条排除或待本体处理记录。
- `gold_full_archive_v1.3.xlsx`：全量25条正式审核归档。
- `gold_test_query_ids_v1.3.txt`：正式评估集ID。
- `gold_nontraining_ids_v1.3.txt`：全量25条禁止进入训练、few-shot、调参和检索示例的ID。

## 使用规则

1. 模型训练、few-shot、检索库和调参必须排除 `gold_nontraining_ids_v1.3.txt` 中的全部25条。
2. 正式评估只读取 `gold_test_v1.3.csv`。
3. 不要评估 `hazard_family_id` 和 `query_intent_ids`，这两个本体尚未冻结。
4. 不要修改这些文件；若本体改变，建立新的 v1.4 版本。
