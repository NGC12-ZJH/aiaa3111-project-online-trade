from pathlib import Path
import json, argparse, html, hashlib
import pandas as pd
p=argparse.ArgumentParser();p.add_argument('--root',required=True);r=Path(p.parse_args().root)
src=r/'taxonomy_analysis';out=r/'cross_category_analysis';out.mkdir(exist_ok=True)
q=pd.read_csv(src/'qualified_rules_taxonomy.csv.gz',dtype={'seed':str,'group_id':str},keep_default_na=False)
for c in ['joint_count','antecedent_count','support','confidence','lift']:q[c]=pd.to_numeric(q[c])
assert not q.taxonomy_unknown.any()
x=q[q.is_cross_category].copy()
assert len(x)+q.rule_type.eq('同类换款').sum()==len(q)
def ncat(row):return len(set(json.loads(row.antecedent_l2_id)+json.loads(row.consequent_l2_id)))
x['distinct_l2_count']=x.apply(ncat,axis=1)
assert x.distinct_l2_count.ge(2).all()
x.to_csv(out/'all_cross_category_rules.csv.gz',index=False,compression='gzip')
x[x.method.ne('R')].to_csv(out/'GL_cross_category_rules.csv',index=False,encoding='utf-8-sig')
tops=[];counts=[];sections=[]
for scope,z in q.groupby(['method','seed','group_id']):
    method,seed,g=scope;key='G' if method=='G' else ('C'+g if method=='L' else f'R seed={seed} group={g}')
    cross=x[(x.method==method)&(x.seed==seed)&(x.group_id==g)]
    for length in [0,2,3]:
        orig=z if not length else z[z.length.eq(length)]
        a=(cross if not length else cross[cross.length.eq(length)]).sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]).copy()
        a['rank']=range(1,len(a)+1);a['ranking_length']=length;tops.append(a.head(50))
        counts.append(dict(scope=key,method=method,seed=seed,group_id=g,length=length,original=len(orig),retained=len(a),removed=len(orig)-len(a),retained_share=len(a)/len(orig) if len(orig) else 0,unique_combinations=a.itemset.nunique()))
        records=[]
        for row in a.head(50).itertuples():
            records.append(dict(rank=row.rank,rule=row.antecedent_name+' → '+row.consequent_name,codes=row.antecedent+' → '+row.consequent,categories=row.antecedent_category+' → '+row.consequent_category,type=row.rule_type,n_categories=row.distinct_l2_count,joint=row.joint_count,support=row.support,confidence=row.confidence,lift=row.lift))
        sections.append(dict(scope=key,length=length,total=len(a),rules=records))
counts=pd.DataFrame(counts);counts.to_csv(out/'scope_counts.csv',index=False,encoding='utf-8-sig');pd.concat(tops).to_csv(out/'cross_category_top50.csv',index=False,encoding='utf-8-sig')
intro='商品层跨类规则：沿用原有 generated_here 且 eligible 规则，删除全部商品同一 l2 的规则。保留同系列配套与其他跨类搭配；当前无 other。未重跑挖掘、未改门槛、未使用 Validation/Test。按联合次数↓、confidence↓、lift↓、rule_id↑ 排序；方向规则分别计数，Top 为各范围独立排名，不是系统预算。三商品可涉及2或3个子类。'
page='''<!doctype html><meta charset="utf-8"><title>商品层跨类规则</title><style>body{font:15px system-ui;margin:32px;color:#203047}p{line-height:1.8}select{padding:8px;margin:8px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}th{background:#eaf0f7}small{color:#637080}</style><h1>商品层跨类规则</h1><p>INTRO</p><label>范围<select id="scope"></select></label><label>商品数<select id="len"><option value="0">混合</option><option value="2">二商品</option><option value="3">三商品</option></select></label><label>榜单<select id="limit"><option>10</option><option>20</option><option>50</option></select></label><p id="info"></p><table><thead><tr><th>排名</th><th>商品与子类</th><th>分类</th><th>联合次数</th><th>Support</th><th>Confidence</th><th>Lift</th></tr></thead><tbody id="rows"></tbody></table><script>const data=DATA;const el=id=>document.getElementById(id);const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));for(const s of [...new Set(data.map(d=>d.scope))]){const o=document.createElement('option');o.value=s;o.textContent=s;el('scope').append(o)}function render(){let d=data.find(d=>d.scope===el('scope').value&&d.length===+el('len').value);el('info').textContent=`剩余 ${d.total} 条合格方向规则；显示前 ${Math.min(d.total,+el('limit').value)} 条。`;el('rows').innerHTML=d.rules.slice(0,+el('limit').value).map(r=>`<tr><td>${r.rank}</td><td>${esc(r.rule)}<br><small>${esc(r.codes)}<br>${esc(r.categories)}</small></td><td>${esc(r.type)}<br>${r.n_categories}个子类</td><td>${r.joint}</td><td>${(r.support*100).toFixed(2)}%</td><td>${(r.confidence*100).toFixed(2)}%</td><td>${r.lift.toFixed(2)}</td></tr>`).join('')}['scope','len','limit'].forEach(id=>el(id).onchange=render);render()</script>'''
(out/'商品层跨类规则.html').write_text(page.replace('INTRO',html.escape(intro)).replace('DATA',json.dumps(sections,ensure_ascii=False).replace('</','<\\/')),encoding='utf-8')
lines=['# 商品层跨类规则',intro,'|范围|商品数|原规则|保留|移除|保留比例|不同组合|','|---|---|---|---|---|---|---|']
for row in counts[counts.method.ne('R')].itertuples():lines.append(f'|{row.scope}|{row.length or "混合"}|{row.original}|{row.retained}|{row.removed}|{row.retained_share:.2%}|{row.unique_combinations}|')
lines+=['完整榜单见同目录 HTML，可切换64个范围与Top10/20/50。完整规则见 all_cross_category_rules.csv.gz；G/L规则另存CSV。随机组逐seed保留，不将60组当作独立重复。','分类筛选不证明互补、显著性或未来稳定性；原有随机差异结论不能自动移用于筛选后的规则集。']
(out/'商品层跨类规则报告.md').write_text('\n\n'.join(lines[:2])+'\n\n'+'\n'.join(lines[2:]),encoding='utf-8')
(out/'manifest.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256((src/'qualified_rules_taxonomy.csv.gz').read_bytes()).hexdigest(),qualified_rows=len(q),retained_rows=len(x),removed_rows=len(q)-len(x),checks='partition reconciled; all retained rules have >=2 l2; original metrics and ordering preserved'),indent=2),encoding='utf-8')
print(counts[counts.method.ne('R')].to_string(index=False));print('ALL',len(q),'CROSS',len(x))
