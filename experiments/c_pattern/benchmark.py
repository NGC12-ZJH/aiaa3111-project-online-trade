import os
for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'): os.environ[k]='1'
import json,time,sys,hashlib,subprocess,platform,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results'; OUT.mkdir(exist_ok=True)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def worker(algorithm,support,length,target):
 import numpy as np,pandas as pd,psutil,threading
 from mlxtend.frequent_patterns import apriori,fpgrowth
 p=psutil.Process(); samples=[]; stop=threading.Event()
 def monitor():
  while not stop.wait(.005): samples.append(p.memory_info().rss)
 baseline=p.memory_info().rss; samples.append(baseline)
 thread=threading.Thread(target=monitor); thread.start()
 start=time.perf_counter()
 x=np.load(ROOT/'discovery.npy'); df=pd.DataFrame(x)
 ready=time.perf_counter(); before=p.memory_info().rss
 result=(apriori if algorithm=='apriori' else fpgrowth)(df,min_support=support,max_len=length,use_colnames=False)
 end=time.perf_counter(); mining_highwater=getattr(p.memory_info(),'peak_wset',p.memory_info().rss); samples.append(p.memory_info().rss); stop.set(); thread.join()
 counts={','.join(map(str,sorted(s))):int(round(v*len(x))) for v,s in zip(result.support,result.itemsets)}
 # Independently recount every returned itemset against the original boolean matrix.
 for key,count in counts.items():
  assert int(x[:,list(map(int,key.split(',')))].all(axis=1).sum())==count
 data={'algorithm':algorithm,'support':support,'max_len':length,'mining_s':end-ready,'load_encode_mine_s':end-start,'baseline_mib':baseline/2**20,'before_mining_mib':before/2**20,'sampled_peak_mib':max(samples)/2**20,'sampled_increment_mib':(max(samples)-baseline)/2**20,'process_peak_mib':mining_highwater/2**20,'n_itemsets':len(counts),'counts':counts}
 Path(target).write_text(json.dumps(data),encoding='utf-8')
def main():
 import pandas as pd,numpy as np,psutil,importlib.metadata as md
 from mlxtend.preprocessing import TransactionEncoder
 source=ROOT/'processed/baskets.csv.gz'
 b=pd.read_csv(source,dtype=str,keep_default_na=False)
 all_discovery=b[b.split.eq('discovery')]
 b=all_discovery[all_discovery.is_eligible_for_main_comparison.eq('1')].copy()
 assert len(b)>0 and b.basket_id.is_unique and b.customer_id.ne('').all()
 dates=pd.to_datetime(b.invoice_date); assert dates.ge('2010-06-01').all() and dates.lt('2010-12-01').all()
 baskets=b['items'].map(json.loads).tolist(); assert all(len(z)==len(set(z)) and len(z)>0 for z in baskets)
 enc=TransactionEncoder(); x=enc.fit(baskets).transform(baskets); np.save(ROOT/'discovery.npy',x)
 (ROOT/'items.json').write_text(json.dumps(enc.columns_),encoding='utf-8')
 b.to_csv(ROOT/'discovery_baskets.csv',index=False)
 manifest={'n_baskets':len(b),'all_discovery_baskets':len(all_discovery),'customers':b.customer_id.nunique(),'items':x.shape[1],'single_item_baskets':sum(len(z)==1 for z in baskets),'source_sha256':sha(source),'matrix_sha256':sha(ROOT/'discovery.npy'),'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT.parents[1],text=True).strip(),'python':sys.version,'platform':platform.platform(),'cpu':platform.processor(),'logical_cpus':psutil.cpu_count(),'ram_gib':psutil.virtual_memory().total/2**30,'versions':{k:md.version(k) for k in ['numpy','pandas','mlxtend','psutil']},'repeats':3,'supports':[.02,.01],'max_lengths':[2,3],'apriori_low_memory':False,'sampling_ms':5}
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
 rows=[]; comparisons=[]
 for support in [.02,.01]:
  for length in [2,3]:
   reference=None
   for repeat in range(3):
    results={}
    for algorithm in (['fpgrowth','apriori'] if repeat%2==0 else ['apriori','fpgrowth']):
     path=OUT/f'{algorithm}_{support}_{length}_{repeat}.json'
     print('RUN',algorithm,support,length,repeat,flush=True)
     subprocess.run([sys.executable,__file__,'worker',algorithm,str(support),str(length),str(path)],check=True,timeout=600)
     r=json.loads(path.read_text()); results[algorithm]=r.pop('counts'); r['repeat']=repeat; rows.append(r)
     pd.DataFrame(rows).to_csv(OUT/'runs.csv',index=False)
    assert results['apriori']==results['fpgrowth'], 'Algorithm mismatch'
    assert reference is None or reference==results['apriori'], 'Repeat mismatch'
    reference=results['apriori']; comparisons.append({'support':support,'max_len':length,'repeat':repeat,'exact_counts_equal':True,'independent_recount_passed':True,'n_itemsets':len(reference)})
    pd.DataFrame(comparisons).to_csv(OUT/'consistency.csv',index=False)
 summary=pd.DataFrame(rows).groupby(['support','max_len','algorithm']).agg(n_itemsets=('n_itemsets','first'),mining_median_s=('mining_s','median'),mining_min_s=('mining_s','min'),mining_max_s=('mining_s','max'),load_mine_median_s=('load_encode_mine_s','median'),peak_median_mib=('sampled_peak_mib','median'),increment_median_mib=('sampled_increment_mib','median')).reset_index()
 summary.to_csv(OUT/'summary.csv',index=False); print(summary.to_string(index=False),flush=True)
 import matplotlib; matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,col,title in zip(axes,['mining_median_s','peak_median_mib'],['Mining time (seconds)','Sampled process peak RSS (MiB)']):
  table=summary.assign(setting=summary.support.astype(str)+' / L'+summary.max_len.astype(str)).pivot(index='setting',columns='algorithm',values=col)
  table.plot.bar(ax=ax,rot=0); ax.set_title(title); ax.set_xlabel('Support / max itemset length')
 fig.tight_layout(); fig.savefig(OUT/'comparison.png',dpi=180)
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='worker': worker(sys.argv[2],float(sys.argv[3]),int(sys.argv[4]),sys.argv[5])
 else: main()
