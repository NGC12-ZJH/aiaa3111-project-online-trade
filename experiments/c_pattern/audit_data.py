from pathlib import Path
import sys
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parents[1]/'src'))
from online_trade.data import config,policy_audit,time_conflicts,validation
config.OUTPUT_DIR=root/'processed'
policy_audit.main()
time_conflicts.main()
sys.argv=[sys.argv[0],'--output-dir',str(config.OUTPUT_DIR)]
raise SystemExit(validation.main())
