from pathlib import Path
import pandas as pd,json
r=Path(__file__).resolve().parent; o=r/'patterns'
a=pd.read_csv(o/'scope_audit.csv',keep_default_na=False); b=pd.read_csv(o/'budget_audit.csv',keep_default_na=False); m=json.loads((o/'manifest.json').read_text())
lines=['Pattern mining 第一版交付（Discovery）','', '已完成G/L/R统一FP-Growth：全局1次、真实群3次、20个随机seed各3次，共64次。','输入：7521个Discovery有效购物篮；画像期已知顾客；所有方法使用同一批订单。','共同候选商品规则：'+str(m['common_pool_rules'])+'；各范围证据行：'+str(m['evidence_rows'])+'。','', '真实群Discovery样本量：',a[a.method.eq('L')].to_string(index=False),'','合格候选及预算（native）：',b[(b.flow=='native')&b.method.ne('R')].to_string(index=False),'','独立检查：全部方案订单范围一致；未超总预算；无重复部署规则；150条抽样规则由Python集合逐条重算前件/联合计数、support、confidence，通过。','', '推荐交接给D：selected_rules.csv、config.json、scope_audit.csv、budget_audit.csv。详细证据见rule_evidence.csv.gz。','当前1%支持度、至少20次前件/联合出现、confidence>=0.2、lift>=1是开发配置，不是已选最优阈值。','预算50时，真实群C0/C1/C2名额为5/15/30；各群合计50，不能每群各取50。','尚未对Validation或Test评价，不能据候选数量、lift或Discovery案例宣称真实分群更好。','下一步：D对这些固定规则做Validation；如需更多参数配置，可按预先约定的小范围修改CFG再运行，并另存输出避免覆盖当前交付。','全量规则证据与顾客/订单样例只保存在本地，尚未上传GitHub。']
(r/'Pattern阶段结果说明.txt').write_text('\n'.join(lines),encoding='utf-8')
