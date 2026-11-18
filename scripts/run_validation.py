"""Run D's comparison-only Validation from the repository root."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from online_trade.evaluation.validation import main

if __name__ == '__main__':
    main(ROOT)
