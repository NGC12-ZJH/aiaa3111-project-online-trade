from pathlib import Path
import subprocess,hashlib,json
import numpy as np,pandas as pd
from mlxtend.preprocessing import TransactionEncoder
ROOT=Path(__file__).resolve().parent; REPO=ROOT.parents[1]
COMMIT='2ae672b7ea6edb7f5e1561b6a64823004dea833e'
if subprocess.run(['git','cat-file','-e',COMMIT],cwd=REPO,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
 subprocess.run(['git','fetch','origin','a/online-retail-ii-data-snapshot'],cwd=REPO,check=True)
for folder,source,files in [('processed','A_data_preparation',['baskets.csv.gz','orders.csv.gz','clean_transactions.csv.gz']),('labels','B_customer_clustering',['customer_clusters.csv','random_groups.csv'])]:
 (ROOT/folder).mkdir(exist_ok=True)
 for name in files:
  data=subprocess.check_output(['git','show',COMMIT+':data/processed/'+source+'/'+name],cwd=REPO)
  if name=='baskets.csv.gz':assert hashlib.sha256(data).hexdigest()=='30aef702f812ab42224271871271daff5b4e37a594696eee82208252198367bf'
  (ROOT/folder/name).write_bytes(data)
b=pd.read_csv(ROOT/'processed/baskets.csv.gz',dtype=str,keep_default_na=False)
b=b[b.split.eq('discovery')&b.is_eligible_for_main_comparison.eq('1')].copy()
assert len(b)==7521 and b.basket_id.is_unique
b.to_csv(ROOT/'discovery_baskets.csv',index=False)
enc=TransactionEncoder();x=enc.fit(b['items'].map(json.loads).tolist()).transform(b['items'].map(json.loads).tolist())
np.save(ROOT/'discovery.npy',x);(ROOT/'items.json').write_text(json.dumps(enc.columns_),encoding='utf-8')
(ROOT/'labels/source.json').write_text(json.dumps({'snapshot_commit':COMMIT}),encoding='utf-8')
print('Prepared fixed-snapshot inputs:',x.shape)
