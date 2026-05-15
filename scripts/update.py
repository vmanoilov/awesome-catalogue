"""
Auto-Update Script for Awesome-List Catalogue
Runs as a daily cron: scrape → import → score → purge → export → report
"""
import json
import sys
import os
import time
import random
from datetime import datetime, timezone

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from scraper import scrape_all, check_repo_alive
from catalogue import (
    get_db, import_scraped, compute_scores, auto_purge,
    get_stats, export_json, export_csv, DB_PATH
)


def spot_check_alive(sample_size: int = 20, db_path: str = DB_PATH):
    """Spot-check a random sample of repos for liveness."""
    db = get_db(db_path)
    rows = db.execute("""
        SELECT repo_key FROM repos WHERE purged = 0 
        ORDER BY RANDOM() LIMIT ?
    """, (sample_size,)).fetchall()
    db.close()
    
    dead = 0
    archived = 0
    checked = 0
    
    for row in rows:
        key = row["repo_key"]
        result = check_repo_alive(key)
        checked += 1
        
        db = get_db(db_path)
        if not result["alive"]:
            db.execute("UPDATE repos SET alive = 0 WHERE repo_key = ?", (key,))
            dead += 1
            print(f"  DEAD: {key}")
        elif result["archived"]:
            db.execute("UPDATE repos SET archived = 1 WHERE repo_key = ?", (key,))
            archived += 1
            print(f"  ARCHIVED: {key}")
        else:
            # Update with fresh GitHub data
            if result.get("stars"):
                db.execute("""
                    UPDATE repos SET stars = ?, forks = ?, alive = 1
                    WHERE repo_key = ?
                """, (result["stars"], result["forks"], key))
            if result.get("pushed_at"):
                pushed = result["pushed_at"][:10]  # YYYY-MM-DD
                db.execute("UPDATE repos SET last_updated = ? WHERE repo_key = ?", (pushed, key))
        
        db.commit()
        db.close()
        time.sleep(0.5)  # Rate limit
    
    print(f"  Spot-checked {checked}: {dead} dead, {archived} archived")
    return {"checked": checked, "dead": dead, "archived": archived}


def full_update(db_path: str = DB_PATH):
    """Run a full update cycle."""
    print(f"=== Awesome-List Catalogue Update: {datetime.now(timezone.utc).isoformat()} ===\n")
    
    # Step 1: Scrape fresh data
    print("Step 1/5: Scraping Ecosyste.ms...")
    repos = scrape_all(delay=0.8)
    
    # Step 2: Import into DB
    print("\nStep 2/5: Importing into catalogue...")
    result = import_scraped(repos, db_path)
    print(f"  Added: {result['added']}, Updated: {result['updated']}")
    
    # Step 3: Spot-check liveness
    print("\nStep 3/5: Spot-checking repo liveness...")
    alive_result = spot_check_alive(sample_size=15, db_path=db_path)
    
    # Step 4: Compute scores
    print("\nStep 4/5: Computing quality scores...")
    compute_scores(db_path)
    
    # Step 5: Auto-purge
    print("\nStep 5/5: Auto-purging bad data...")
    purge_result = auto_purge(db_path)
    print(f"  Purged: {purge_result['purged']} ({purge_result['reasons']})")
    
    # Export
    print("\nExporting catalogue...")
    json_path = export_json(db_path)
    csv_path = export_csv(db_path)
    print(f"  JSON: {json_path}")
    print(f"  CSV: {csv_path}")
    
    # Stats
    stats = get_stats(db_path)
    print(f"\n=== Catalogue Stats ===")
    print(f"  Active repos: {stats['total_active']}")
    print(f"  Purged repos: {stats['total_purged']}")
    print(f"  Freshness: {stats['freshness']}")
    print(f"  Popularity: {stats['popularity']}")
    
    return {
        "scrape_count": len(repos),
        "import": result,
        "alive_check": alive_result,
        "purge": purge_result,
        "stats": stats,
    }


if __name__ == "__main__":
    result = full_update()
    print(f"\n=== Update Complete ===")
    print(json.dumps(result, indent=2, default=str))
