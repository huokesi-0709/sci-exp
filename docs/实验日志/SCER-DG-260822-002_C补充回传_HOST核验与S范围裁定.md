# SCER-DG-260822-002：C 补充回传、HOST-P 核验与导师 S 范围裁定

时间：2026-08-22T13:05:00+08:00  
类型：数据治理 / 输入级 Gold 预备工作  
formal_evidence：false

## 输入与原件保全

- C 补充回传工作簿：`02_发给C_补充确认与身份登记_v1.2_已填写.xlsx`
- 原始回传件 SHA-256：`A30FFE7E65352A34BC542E52AFF3A3BB8CD33710C89371F2EC3514F56B6356DC`
- 工作区原件归档：`data/annotations/input_gold_v1.0/domain_review/C_supplement_submission_20260822/`
- 干净基线 SHA-256：`C0C93D73D978D68E78BCBE98B46A75E81A74732859C3CB6B7B3DB1252D90FFD8`
- 原始回传件保持不变；固定说明区出现的异常字符串`52`不作为C的实质回答，也不进入派生验收版。

## C 的事实与补充确认

- `training_completed_at`：`2026-06-15T12:16:00+08:00`；HOST-P确认该值为真实时间，原值保留。
- `signed_at`：`2026-06-16T12:16:00+08:00`；HOST-P确认该值为真实时间，原值保留。
- 职业/培训类别：红十字应急救护培训。
- 最高相关资质：红十字应急救护师资。
- 相关年限：6年。
- 两个补充动作均为`REVISE`；四项主持人机械修正均为`ACKNOWLEDGE`。
- C 的原始限制仍然成立：其为公众初级救护教学资质，不是医疗执业资质。

## HOST-P 身份与资质核验

- HOST-P已核验ANN-C的真实身份、红十字应急救护培训背景、红十字应急救护师资资质及相关年限。
- `credential_verified_by`记录为`HOST-P（项目主持人）`。
- 为遵守最小化原则，真实姓名、身份证件、证书编号和证件图片不写入工作簿；工作簿只保留匿名ID和核验结论。
- `allowed_fields`只表示可以处理的标注字段类型；其效力受主题范围限制，不能解释为所有主题的领域资格。

## 导师 S 的限定范围批准

- 裁定：`SCOPED_APPROVAL`。
- 可由当前C背景支持的范围：心肺复苏、AED、创伤处置、低温、烧伤等公众初级救护内容，以及与这些主题直接相关且受冻结公众协议支持的风险、动作、约束和培训参考答案。
- 不能仅凭当前C背景自动视为已获完整领域批准的范围：心理援助/自伤、地质灾害、气象预警、消防、公共卫生。
- 该裁定不是对C资格的否定，而是把审核者资历与具体本体主题逐项匹配，避免把公众急救师资外推为全领域专家。

## 派生验收产物

- 工作簿：`outputs/input_gold_host_acceptance_20260822/03_主持人核验与S范围裁定_干净验收版_v1.3.xlsx`
- SHA-256：`1B86820105B723F9822A613D1925065D4AE982E48244D6805A181EA6105B9E73`
- 派生方法：以干净基线为母版，只合并C授权填写区；HOST-P核验与导师S裁定另表记录。
- 新增审计页：`HOST与S裁定`、`待补领域清单`、`派生与清理记录`。

## QA

- 重新导入后10个工作表齐全：PASS。
- 公式错误扫描：0。
- 异常单值`52`扫描：0。
- 两个确认时间均以完整ISO 8601带时区文本显示：PASS。
- `credential_verified_by`、两个补充动作、四项更正确认、限定范围批准和未覆盖领域均重新读取验证：PASS。
- 关键工作表完成渲染与人工版式检查：PASS。

## 状态变化与下一道门

输入级Gold工作包从
`domain_review_returned_pending_supplement_and_identity_verification`更新为
`partial_domain_approval_pending_uncovered_domain_resolution_and_statistics_approval`。

当前可以继续完成覆盖范围内条目的清洁本体合并和schema机械修复，但完整A/B包保持`HOLD`。
发放完整A/B包前必须二选一：

1. 为心理援助/自伤、地质灾害、气象预警、消防、公共卫生增加相应领域审核者；或
2. 由HOST-P与导师S正式决定从当前训练/试标范围排除这些主题，并重新检查抽样覆盖。

此外，统计/一致性质量门仍需独立统计审核者T批准。本次C身份核验与导师S限定领域批准不能替代T。

## 边界

- 不改变E0 `in_progress_waiting_hardware`。
- 不把`development_gold`升级为正式Gold calibration/test。
- 培训题和试标题永久排除于正式Gold calibration/test。
- 在未覆盖领域完成补审或范围排除、且T批准前，不得宣称完整“双审”成立。
