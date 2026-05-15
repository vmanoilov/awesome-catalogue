"""
Daily cron script for auto-updating the awesome-list catalogue.
Runs as a script cron — no AI agent needed.
Steps: scrape → validate → import → liveness spot-check → score → purge → rebuild HTML → export
Exits with code 1 on failure for monitoring.
"""
import sys
import os
import json
import time
from datetime import datetime, timezone

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(__file__))

from scraper import scrape_all, check_repo_alive
from catalogue import (
    get_db, import_scraped, compute_scores, auto_purge,
    get_stats, export_json, export_csv, DB_PATH
)
from build_html import build_html


def spot_check_alive(sample_size: int = 15, db_path: str = DB_PATH):
    """Spot-check a random sample of repos for liveness via GitHub API."""
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
            print(f"    DEAD: {key}")
        elif result["archived"]:
            db.execute("UPDATE repos SET archived = 1 WHERE repo_key = ?", (key,))
            archived += 1
            print(f"    ARCHIVED: {key}")
        else:
            # Update with fresh GitHub data if available
            if result.get("stars"):
                db.execute("""
                    UPDATE repos SET stars = ?, forks = ?, alive = 1
                    WHERE repo_key = ?
                """, (result["stars"], result["forks"], key))
            if result.get("pushed_at"):
                pushed = result["pushed_at"][:10]
                db.execute("UPDATE repos SET last_updated = ? WHERE repo_key = ?", (pushed, key))
        
        db.commit()
        db.close()
        time.sleep(0.5)  # Stay within rate limits
    
    print(f"  Spot-checked {checked}: {dead} dead, {archived} archived")
    return {"checked": checked, "dead": dead, "archived": archived}


def main():
    start = time.time()
    now = datetime.now(timezone.utc)
    print(f"=== Awesome-List Catalogue Daily Update: {now.isoformat()} ===\n")
    
    errors = []
    
    try:
        # Step 1: Scrape
        print("Step 1/7: Scraping Ecosyste.ms...")
        repos = scrape_all(delay=0.8)
        print(f"  Scraped {len(repos)} repos\n")
        
        # Safety: if scraper returned empty (HTML structure changed), abort
        if len(repos) == 0:
            msg = "ABORT: Scraper returned 0 repos — possible HTML structure change. Skipping import to preserve existing data."
            print(f"  !!! {msg}")
            errors.append(msg)
            # Still rebuild HTML from existing data
            print("\nRebuilding HTML from existing data...")
            build_html()
            _print_summary(start, errors)
            sys.exit(1)
        
        # Step 2: Import
        print("Step 2/7: Importing...")
        result = import_scraped(repos)
        print(f"  Added: {result['added']}, Updated: {result['updated']}, Un-purged: {result.get('unpurged', 0)}\n")
        
        # Step 3: Spot-check liveness
        print("Step 3/7: Spot-checking repo liveness (15 random)...")
        try:
            alive_result = spot_check_alive(sample_size=15)
        except Exception as e:
            print(f"  Liveness check failed (non-fatal): {e}")
            errors.append(f"Liveness check failed: {e}")
        
        # Step 4: Score
        print("\nStep 4/7: Scoring...")
        compute_scores()
        
        # Step 5: Purge
        print("\nStep 5/7: Auto-purging...")
        purge = auto_purge()
        print(f"  Purged: {purge['purged']} — {purge['reasons']}\n")
        
        # Step 6: Rebuild HTML
        print("Step 6/7: Building HTML viewer...")
        build_html()
        
        # Step 7: Export
        print("\nStep 7/7: Exporting...")
        export_json()
        export_csv()
        
        _print_summary(start, errors)
        
    except Exception as e:
        print(f"\n!!! Update FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _print_summary(start: float, errors: list):
    """Print update summary."""
    stats = get_stats()
    elapsed = time.time() - start
    print(f"\n=== Update Complete ({elapsed:.0f}s) ===")
    print(f"  Active: {stats['total_active']}")
    print(f"  Purged: {stats['total_purged']}")
    print(f"  Freshness: {stats['freshness']}")
    if errors:
        print(f"\n  ⚠️  Warnings ({len(errors)}):")
        for e in errors:
            print(f"    - {e}")


if __name__ == "__main__":
    main()
