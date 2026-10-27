"""Send daily strategy ranking summary to TG."""
import os
try:  # the token may have been rotated; the file wins over the env
    from tg_token import get_token as _tg_token
except ImportError:  # not running from the scripts directory
    def _tg_token() -> str:
        return os.environ.get("TELEGRAM_BOT_TOKEN", "")
import requests
from pathlib import Path
import json
from datetime import datetime, timezone, timedelta

HKT = timezone(timedelta(hours=8))
today = datetime.now(HKT).strftime('%Y-%m-%d')

# Load latest ranking
ranking_dir = Path('automation/reports/strategy_ranking')
ranking_files = sorted(ranking_dir.glob(f'ranking_{today}*.md'))
if not ranking_files:
    print('No ranking file')
    exit(0)

ranking_text = ranking_files[0].read_text()

# Find best/worst
lines = ranking_text.split('\n')
table_rows = [l for l in lines if l.startswith('|') and 'Strategy' not in l and '---' not in l]
top3 = '\n'.join(table_rows[:3])

msg = (
    f'🏆 Daily Strategy Ranking — {today}\n\n'
    f'Top 3 (best PF):\n{top3}\n\n'
    f'Full report: github.com/yip-lgtm/YW-concept-ki7409/tree/main/automation/reports/strategy_ranking'
)

r = requests.post(
    f'https://api.telegram.org/bot{_tg_token()}/sendMessage',
    json={'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'text': msg},
    timeout=15,
)
print(f'TG: HTTP {r.status_code}')
