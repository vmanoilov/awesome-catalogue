# 📚 Awesome-List Catalogue

A self-updating, portable catalogue of **3,770+ awesome-list repositories** from [Ecosyste.ms](https://awesome.ecosyste.ms). Searchable, filterable, scored by quality, auto-categorized into 21 domains.

## Quick Start

### Just browse it
Open `data/awesome_catalogue.html` in any browser — works offline, mobile-friendly, no server needed.

### Run the updater
```bash
pip install beautifulsoup4 lxml
python scripts/daily_update_cron.py
```

This will:
1. Scrape fresh data from Ecosyste.ms (~42 pages, ~4,000 repos)
2. Import into SQLite (`data/catalogue.db`)
3. Spot-check 15 random repos via GitHub API for liveness
4. Compute quality scores (0-100)
5. Auto-purge dead, archived, and zero-value repos
6. Rebuild the HTML viewer
7. Re-export JSON and CSV

### Search from Python
```python
import sys; sys.path.insert(0, 'scripts')
from catalogue import search, get_stats

# Search by keyword
results = search(query="llm", limit=10)

# Filter by domain + freshness
results = search(domain="AI & ML", freshness="active", min_stars=1000)

# Get stats
stats = get_stats()
print(f"Active repos: {stats['total_active']}")
```

### Search from CLI
```bash
python scripts/catalogue.py search "security"
python scripts/catalogue.py stats
python scripts/catalogue.py export_json
python scripts/catalogue.py export_csv
```

## What's Inside

| File | Size | Description |
|------|------|-------------|
| `data/awesome_catalogue.html` | ~2.7MB | Standalone viewer — open in any browser |
| `data/catalogue_export.json` | ~4.1MB | Full JSON export of all active repos |
| `data/catalogue_export.csv` | ~1.4MB | CSV export for spreadsheets |
| `data/catalogue.db` | ~3.2MB | SQLite database (created on first run) |

## Quality Scoring

Each repo gets a 0-100 quality score:
- **Stars** (45%) — log-scaled, normalized against the dataset max
- **Freshness** (25%) — active (<90 days) = 25, stale (90-365 days) = 12, abandoned (>1yr) = 3
- **Forks** (10%) — log-scaled
- **Project breadth** (10%) — how many projects Ecosyste.ms has indexed from the list
- **Topic richness** (10%) — number of topic tags (up to 10)

## Domain Categories (21)

AI & ML · Security · DevOps & Infrastructure · Web3 & Crypto · Self-Hosted · Gaming · Education & Learning · Data & Databases · Design · Mobile · APIs & Services · OS & CLI Tools · Robotics & Hardware · Developer Tools · Media & Content · Business & Startups · Networking · Audio & Video · Web Development · Programming Languages · Other

## Auto-Purge Rules

Repos are automatically purged when:
- **Dead**: GitHub returns 404
- **Archived**: Marked as archived on GitHub
- **Zero-value**: 0 stars AND 0 forks AND <5 indexed projects
- **Abandoned + low-value**: No update in 3+ years AND <50 stars

Purged repos can be **un-purged** automatically if they reappear in a scrape with signs of life (>0 stars + recent activity).

## Automation

Set up a daily cron job:
```bash
# Run daily at 4:30 AM UTC
30 4 * * * cd /path/to/awesome-catalogue && python scripts/daily_update_cron.py >> logs/update.log 2>&1
```

The script includes:
- **Safety check**: If scraper returns 0 repos (HTML structure change), it aborts to preserve existing data
- **Liveness spot-checks**: Randomly verifies 15 repos against GitHub API each run
- **Structured logging**: Exit code 1 on failure for monitoring
- **Detailed changelog**: Tracks which repos were added/purged each run

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `repo_key` | TEXT PK | `owner/name` (lowercase) |
| `name` | TEXT | Repository name |
| `stars` | INT | GitHub stars |
| `forks` | INT | GitHub forks |
| `projects` | INT | Ecosyste.ms indexed project count |
| `quality_score` | REAL | 0-100 composite score |
| `freshness_status` | TEXT | active / stale / abandoned |
| `popularity_tier` | TEXT | mega / high / mid / low / micro |
| `domain_category` | TEXT | One of 21 domain categories |
| `purged` | INT | 1 if auto-purged |

## Requirements

- Python 3.10+
- `beautifulsoup4` + `lxml` (for scraping)
- No other dependencies — SQLite is built-in

## License

Data sourced from [Ecosyste.ms](https://awesome.ecosyste.ms) and GitHub. This tool is provided as-is for personal use.

---
Built by [Viktor](https://viktor.com)
