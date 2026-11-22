from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

R=Path(__import__('os').environ.get('PATTERN_PROJECT_ROOT', str(Path(__file__).resolve().parent)));O=R/'customer_behavior_profile';O.mkdir(exist_ok=True)
labels=pd.read_csv(R/'labels/customer_clusters.csv',dtype={'customer_id':str,'cluster_id':str})
orders=pd.read_csv(R/'processed/orders.csv.gz',dtype={'basket_id':str,'customer_id':str})
orders=orders[(orders.split=='profile')&(orders.is_valid_order==1)&orders.customer_id.isin(labels.customer_id)].copy()
assert orders.basket_id.is_unique
use=['invoice_id','stock_code','quantity','line_amount','split','is_valid_basket_item']
chunks=[]
for z in pd.read_csv(R/'processed/clean_transactions.csv.gz',usecols=use,dtype={'invoice_id':str,'stock_code':str},chunksize=100000):
 chunks.append(z[(z.split=='profile')&(z.is_valid_basket_item==1)&z.invoice_id.isin(orders.basket_id)])
lines=pd.concat(chunks,ignore_index=True)
assert (lines.quantity>0).all()
sku=lines.groupby(['invoice_id','stock_code'],as_index=False).agg(quantity=('quantity','sum'),amount=('line_amount','sum'))
tax=pd.read_csv(R/'taxonomy_analysis/item_taxonomy_v1.csv',dtype=str)
assert tax.stock_code.is_unique
sku['l2_id']=sku.stock_code.map(tax.set_index('stock_code').l2_id)
sku['known_l2']=sku.l2_id.notna() & ~sku.l2_id.str.lower().str.contains('other',na=False)
stats=sku.groupby('invoice_id').agg(total_units=('quantity','sum'),median_units_per_sku=('quantity','median'),distinct_skus=('stock_code','size'),product_amount=('amount','sum'),known_skus=('known_l2','sum'))
cat=sku[sku.known_l2].groupby(['invoice_id','l2_id']).size().rename('sku_count').reset_index()
catstats=cat.groupby('invoice_id').agg(distinct_l2=('l2_id','size'),mean_skus_per_l2=('sku_count','mean'),max_skus_per_l2=('sku_count','max'))
catstats['multi_sku_l2_share']=cat.assign(multi=cat.sku_count>=2).groupby('invoice_id').multi.mean()
order=orders.merge(stats,left_on='basket_id',right_index=True,validate='one_to_one').merge(catstats,left_on='basket_id',right_index=True,how='left',validate='one_to_one')
order.distinct_l2=order.distinct_l2.fillna(0)
assert len(order)==len(orders)
assert (order.distinct_skus==order.basket_size).all()
assert np.allclose(order.product_amount,order.gross_purchase_amount,atol=.011)
threshold=float(order.total_units.quantile(.9));order['large_quantity']=order.total_units>=threshold
order['timestamp']=pd.to_datetime(order.invoice_datetime)
itemsets=sku.groupby('invoice_id').stock_code.agg(set).to_dict()
order['repeat_sku_share']=np.nan;order['repeat_skus']=np.nan;order['eligible_repeat_skus']=np.nan
# Use strictly earlier order timestamps; simultaneous invoices cannot create artificial repeat evidence.
for customer,ix in order.groupby('customer_id').groups.items():
 seen=set()
 for t,z in order.loc[ix].sort_values('timestamp').groupby('timestamp',sort=True):
  update=set()
  for i,row in z.iterrows():
   items=itemsets[row.basket_id]
   if seen:
    repeated=len(items&seen);order.loc[i,['repeat_sku_share','repeat_skus','eligible_repeat_skus']]=[repeated/len(items),repeated,len(items)]
   update|=items
  seen|=update
order=order.merge(labels[['customer_id','cluster_id']],on='customer_id',validate='many_to_one')
features=order.groupby('customer_id').agg(n_orders=('basket_id','size'),median_order_units=('total_units','median'),median_units_per_sku=('median_units_per_sku','median'),large_quantity_order_share=('large_quantity','mean'),n_large_quantity_orders=('large_quantity','sum'),median_distinct_skus=('distinct_skus','median'),median_distinct_l2=('distinct_l2','median'),median_mean_skus_per_l2=('mean_skus_per_l2','median'),median_max_skus_per_l2=('max_skus_per_l2','median'),median_multi_sku_l2_share=('multi_sku_l2_share','median'),median_order_amount=('gross_purchase_amount','median'),total_amount=('gross_purchase_amount','sum'),median_repeat_sku_share=('repeat_sku_share','median'))
features['repeat_sku_share_weighted']=order.groupby('customer_id').repeat_skus.sum(min_count=1)/order.groupby('customer_id').eligible_repeat_skus.sum(min_count=1)
features['median_interorder_days']=order.sort_values(['customer_id','timestamp']).groupby('customer_id').timestamp.diff().dt.total_seconds().div(86400).groupby(order.sort_values(['customer_id','timestamp']).customer_id).median()
features['purchase_days']=order.assign(day=order.timestamp.dt.date).groupby('customer_id').day.nunique()
features=labels.merge(features,on='customer_id',how='left',validate='one_to_one')
assert len(features)==2684 and features.n_orders.notna().all()
assert (features.n_orders==features.frequency).all()
assert np.allclose(features.total_amount,features.monetary,atol=.011)
fields={'median_order_units':'每单总件数中位数','median_units_per_sku':'订单内单SKU件数中位数的客户中位数','large_quantity_order_share':'大数量订单占比','median_distinct_skus':'每单不同SKU数中位数','median_distinct_l2':'每单不同子类数中位数','median_mean_skus_per_l2':'每单每子类SKU数均值的客户中位数','median_max_skus_per_l2':'每单同子类最大SKU数的客户中位数','median_multi_sku_l2_share':'每单多SKU子类占比的客户中位数','repeat_sku_share_weighted':'后续订单SKU中此前买过的比例','median_order_amount':'每单金额中位数GBP','n_orders':'Profile订单数','median_interorder_days':'相邻订单间隔中位数天'}
summary=[]
for g,z in [('ALL',features)]+list(features.groupby('cluster_id')):
 for f,label in fields.items():
  v=z[f].dropna();summary.append(dict(group=g,feature=f,label=label,customers=len(z),estimable=len(v),missing=int(z[f].isna().sum()),p25=v.quantile(.25),median=v.median(),p75=v.quantile(.75),mean=v.mean()))
summary=pd.DataFrame(summary)
mix=features.groupby('cluster_id').agg(customers=('customer_id','size'),single_order_customers=('n_orders',lambda s:int((s==1).sum())),large_order_customers=('n_large_quantity_orders',lambda s:int((s>=1).sum())),repeated_large_order_customers=('n_large_quantity_orders',lambda s:int((s>=2).sum())),repeat_estimable_customers=('repeat_sku_share_weighted','count'))
for col in ['single_order_customers','large_order_customers','repeated_large_order_customers']:mix[col+'_share']=mix[col]/mix.customers
features.to_csv(O/'customer_features.csv',index=False);summary.to_csv(O/'group_feature_summary.csv',index=False);mix.to_csv(O/'group_behavior_counts.csv')
order.drop(columns='timestamp').to_csv(O/'profile_order_features.csv.gz',index=False,compression='gzip')
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False})
chosen=['median_order_units','median_units_per_sku','median_distinct_skus','median_distinct_l2','median_mean_skus_per_l2','repeat_sku_share_weighted','median_order_amount','n_orders','median_interorder_days']
fig,axes=plt.subplots(3,3,figsize=(14,12))
for ax,f in zip(axes.flat,chosen):
 vals=[features.loc[features.cluster_id==g,f].dropna().to_numpy() for g in ['0','1','2']]
 ax.boxplot(vals,tick_labels=['C0','C1','C2'],showfliers=False)
 ax.set_title(fields[f],fontsize=10);ax.grid(axis='y',alpha=.2)
 if f in ['median_order_units','median_units_per_sku','median_order_amount','n_orders']:ax.set_yscale('log')
 for i,v in enumerate(vals,1):ax.text(i,.96,f'n={len(v)}',ha='center',va='top',transform=ax.get_xaxis_transform(),fontsize=8)
fig.suptitle('Profile客户行为分布：客户等权；箱体为25%–75%，中线为中位数\n隐藏离群点仅为显示；部分坐标为对数；n为可估客户数',fontsize=13)
fig.tight_layout(rect=[0,0,1,.95]);fig.savefig(O/'customer_behavior_distributions.png',dpi=160);plt.close(fig)
protocol={'period':'2009-12-01 inclusive to 2010-06-01 exclusive','customers':len(features),'orders':len(order),'large_quantity_threshold_units':threshold,'large_quantity_definition':'Profile eligible order total quantity >= pooled order 90th percentile; include ties; descriptive not identity label','large_quantity_order_count':int(order.large_quantity.sum()),'repeat_definition':'Number of order-SKU occurrences bought at strictly earlier timestamps / order-SKU occurrences in orders with earlier history; first timestamp excluded; no earlier history => NA','interval_definition':'Adjacent invoice timestamp differences in days; simultaneous orders may yield zero; one order => NA','category_definition':'Existing taxonomy_v1; missing and other excluded only from category features; SKU quantity and money retained','unknown_or_other_sku_occurrences':int((~sku.known_l2).sum()),'customer_weighting':'Customer feature medians and IQR, one customer one vote','limitations':['No wholesale/retail ground truth or classification accuracy','RFM frequency and monetary are reused; their separation is expected, not independent validation','Replenishment observation opportunity differs with order frequency; first purchase is left-censored by Profile boundary','Same-subcategory SKUs are assortment proxies, not verified model/color variants','Taxonomy_v1 retrospectively applied; taxonomy built later, not a prospectively frozen Profile-only labeling experiment','No downstream Discovery/Validation/Test transactions used for feature values; no future validation performed','Outliers preserved under upstream cleaning; medians/IQR used; returns excluded so amounts are gross purchases'], 'checks':{'sku_counts_match_existing_baskets':True,'amounts_match_existing_orders':True,'customer_frequency_matches_RFM':True,'customer_monetary_matches_RFM':True},'inputs_sha256':{f:hashlib.sha256((R/f).read_bytes()).hexdigest() for f in ['processed/clean_transactions.csv.gz','processed/orders.csv.gz','labels/customer_clusters.csv','taxonomy_analysis/item_taxonomy_v1.csv']}}
(O/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
report='客户采购行为画像（Profile期探索性分析）\n\n'+json.dumps(protocol,ensure_ascii=False,indent=2)+'\n\n群体中位数：\n'+summary.pivot(index='label',columns='group',values='median').to_string()+'\n\n行为计数：\n'+mix.to_string()+'\n\n所有特征为行为描述，不代表真实批发商/散客身份。单次购买不能判断补货倾向；不同群购买频次不同，不可直接把复购比例差解释为身份差。\n'
(O/'客户行为画像说明.txt').write_text(report,encoding='utf-8')
print(json.dumps({k:v for k,v in protocol.items() if k in ['customers','orders','large_quantity_threshold_units','large_quantity_order_count','unknown_or_other_sku_occurrences','checks']},ensure_ascii=False,indent=2))
print(summary.pivot(index='feature',columns='group',values='median').to_string());print(mix.to_string())
