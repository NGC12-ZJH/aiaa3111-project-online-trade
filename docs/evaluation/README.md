# D 分支交付

D 使用固定的 Discovery 规则评价未来交易。Validation 用于比较配置和预算，正式 Test 使用选定并提交的 P5 协议。

| 阶段 | 看什么 |
|---|---|
| **[Validation](validation/README.md)** | 为什么选 P5／100，哪些规则通过共同质量验收，分群和全局有哪些差异，合并规则能否补充覆盖 |
| **[Test](test/README.md)** | P5／100 主结果、20／50／100 预算曲线、顾客配对区间和 P3 合并补充结果 |

给组员讲解时，先打开 [Test 报告](test/README.md) 看最终结果，再到 [Validation 总览](validation/README.md) 查选参理由。需要重跑时使用 [复现说明](reproduce.md)；计算输入和规则清单的校验值见 [Test 冻结协议](../../configs/test_frozen.json)。
