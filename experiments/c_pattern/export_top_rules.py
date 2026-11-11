from pathlib import Path
import json,hashlib
import pandas as pd
R=Path(__file__).resolve().parent;O=R/'pattern_top_rules';O.mkdir(exist_ok=True)
e=pd.read_csv(R/'patterns/rule_evidence.csv.gz',dtype={'seed':str,'group_id':str},keep_default_na=False)
e=e[e.eligible & e.generated_here].copy()
for field in ['support','confidence','lift','joint_count','antecedent_count']: e[field]=pd.to_numeric(e[field],errors='raise')
n=pd.read_csv(R/'pattern_analysis/product_names.csv',dtype=str).set_index('stock_code').description.to_dict()
records=[];groups=[]
for (method,seed,g),p in e.groupby(['method','seed','group_id'],sort=True):
 p=p.sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]); key=f'{method} / '+(f'seed {seed} / ' if seed else '')+('GLOBAL' if method=='G' else 'C'+g)
 groups.append({'key':key,'method':method,'seed':seed,'group':g,'qualified':len(p),'baskets':int(p.iloc[0].n_baskets)})
 for rank,row in enumerate(p.head(50).itertuples(),1):
  ant=json.loads(row.antecedent);con=json.loads(row.consequent)
  records.append({'scope':key,'rank':rank,'id':row.rule_id,'antecedent':' + '.join(n.get(z,z).strip() for z in ant),'consequent':' + '.join(n.get(z,z).strip() for z in con),'codes':' + '.join(ant)+' → '+' + '.join(con),'joint':row.joint_count,'antecedent_count':row.antecedent_count,'support':row.support,'confidence':row.confidence,'lift':row.lift,'outside_support':row.outside_support,'outside_confidence':row.outside_confidence,'global_rank':row.global_rank})
assert len(groups)==64
for group in groups:
 subset=[x for x in records if x['scope']==group['key']];assert len(subset)==min(50,group['qualified']);assert [x['rank'] for x in subset]==list(range(1,len(subset)+1))
raw={'groups':groups,'rules':records}
(O/'top_rules_data.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')
html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>G/L/R 各组 Top 规则</title><style>body{font:15px "Microsoft YaHei",sans-serif;background:#f4f6fa;color:#223047;margin:28px}h1{margin-bottom:8px}p{line-height:1.7}select,input{padding:10px;border:1px solid #bbc6d4;border-radius:5px;margin:5px}header,.panel{background:white;padding:22px;border-radius:12px;margin-bottom:18px}table{border-collapse:collapse;width:100%;background:white}th,td{padding:12px;border-bottom:1px solid #dce2eb;text-align:left}th{background:#243c60;color:white;position:sticky;top:0}td.num{white-space:nowrap;text-align:right}tr:nth-child(even){background:#f4f7fb}small{color:#68788e}#tablewrap{overflow:auto}.rule{min-width:310px;line-height:1.6}button{padding:10px;cursor:pointer}</style><header><h1>G / L / R 各组 Top 规则</h1><p>Discovery 开发配置｜每个范围独立排名，支持 Top10 / Top20 / Top50。<br>排序：联合次数↓ → confidence↓ → lift↓ → rule_id↑。筛选：support ≥1%，联合及前件次数 ≥20，confidence ≥0.2，lift ≥1。<br><b>这是组内排行榜，不是系统总预算 B 的部署结果。</b>保留方向规则，A→B 与 B→A 分别占位。没有使用 Validation/Test 表现排序。</p></header><div class="panel"><label>范围 <select id="scope"></select></label><label>显示 <select id="limit"><option>10</option><option>20</option><option>50</option></select></label><label>当前榜单搜索 <input id="search" placeholder="商品名称或编码"></label><p id="info"></p><small>群外：同批合格 Discovery 订单中不属于当前组的订单；全局无群外。全局排名为空表示未通过当前全局完整筛选，不能直接解读为算法无法发现。百分数仅显示两位，原始值保存在数据文件。</small></div><div id="tablewrap"><table><thead><tr><th>排名</th><th>商品规则与编码</th><th>联合次数</th><th>前件次数</th><th>Support</th><th>Confidence</th><th>Lift</th><th>群外 Support</th><th>群外 Confidence</th><th>全局排名</th></tr></thead><tbody id="rows"></tbody></table></div><script>const DATA=__DATA__;const el=id=>document.getElementById(id);const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const pct=v=>v===''||v==null?'—':(Number(v)*100).toFixed(2)+'%';for(const g of DATA.groups){const op=document.createElement('option');op.value=g.key;op.textContent=g.key;el('scope').append(op)}function render(){const key=el('scope').value,n=Number(el('limit').value),g=DATA.groups.find(x=>x.key===key),q=el('search').value.trim().toLowerCase();const base=DATA.rules.filter(x=>x.scope===key&&x.rank<=n);const rows=base.filter(x=>(x.antecedent+x.consequent+x.codes).toLowerCase().includes(q));el('info').textContent=`${key}｜${g.baskets.toLocaleString()} 个购物篮｜${g.qualified.toLocaleString()} 条合格规则｜Top${n} 实际 ${base.length} 条，搜索后显示 ${rows.length} 条。`+(g.qualified<n?' 合格规则不足，不补齐。':'');el('rows').innerHTML=rows.map(x=>`<tr><td>${x.rank}</td><td class="rule">${esc(x.antecedent)}<br><b>→ ${esc(x.consequent)}</b><br><small>${esc(x.codes)}</small></td><td class="num">${x.joint}</td><td class="num">${x.antecedent_count}</td><td class="num">${pct(x.support)}</td><td class="num">${pct(x.confidence)}</td><td class="num">${Number(x.lift).toFixed(2)}</td><td class="num">${pct(x.outside_support)}</td><td class="num">${pct(x.outside_confidence)}</td><td class="num">${x.global_rank===''?'—':Number(x.global_rank)}</td></tr>`).join('')}['scope','limit','search'].forEach(id=>el(id).addEventListener('input',render));render();</script></html>'''
html=html.replace('__DATA__',json.dumps(raw,ensure_ascii=False).replace('</','<\\/'))
(O/'G_L_R_Top规则.html').write_text(html,encoding='utf-8')
lines=['G/L/R 各组规则排行榜','排序：联合次数降序、confidence降序、lift降序、rule_id升序。每组独立Top50；Top10/20为前10/20条。不是系统总预算实验。','商品名称来自Discovery订单。正反方向规则保留；全局未合格排名留空。','']
for g in groups:
 lines += [g['key']+f"｜合格规则{g['qualified']}条｜篮数{g['baskets']}"]
 for x in records:
  if x['scope']==g['key']:lines.append(f"{x['rank']:02d}. {x['antecedent']} → {x['consequent']} [{x['codes']}] | 次数={x['joint']}/{x['antecedent_count']} | support={x['support']:.2%} | confidence={x['confidence']:.2%} | lift={x['lift']:.2f}")
 lines.append('')
(O/'全部组Top50规则.txt').write_text('\n'.join(lines),encoding='utf-8')
print('Groups:',len(groups),'rows:',len(records));print([(g['key'],g['qualified']) for g in groups if g['qualified']<50]);print('\n'.join(lines[:15]))
