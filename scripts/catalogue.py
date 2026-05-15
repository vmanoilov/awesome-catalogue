"""
Awesome-List Catalogue Manager
Core SQLite database for the unified awesome-list catalogue.
Handles: create, import, score, search, purge, export.
"""
import sqlite3
import json
import os
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = os.environ.get("AWESOME_DB", "/work/skills/awesome_catalogue/data/catalogue.db")


def get_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Get database connection, creating schema if needed."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    
    db.executescript("""
        CREATE TABLE IF NOT EXISTS repos (
            repo_key TEXT PRIMARY KEY,       -- owner/name (lowercase)
            name TEXT NOT NULL,
            owner TEXT NOT NULL,
            description TEXT DEFAULT '',
            url TEXT NOT NULL,
            ecosystems_url TEXT DEFAULT '',
            stars INTEGER DEFAULT 0,
            forks INTEGER DEFAULT 0,
            projects INTEGER DEFAULT 0,       -- ecosyste.ms indexed project count
            topics TEXT DEFAULT '[]',          -- JSON array
            last_updated TEXT,                 -- repo last push/update date
            
            -- Scoring fields
            freshness_status TEXT DEFAULT 'unknown',  -- active/stale/abandoned/unknown
            popularity_tier TEXT DEFAULT 'unknown',    -- mega/high/mid/low/micro/unknown
            breadth_tier TEXT DEFAULT 'unknown',       -- massive/large/medium/small/tiny/unknown
            quality_score REAL DEFAULT 0.0,            -- 0-100 composite
            
            -- Lifecycle
            alive INTEGER DEFAULT 1,
            archived INTEGER DEFAULT 0,
            purged INTEGER DEFAULT 0,
            purge_reason TEXT,
            
            -- Metadata
            first_seen TEXT NOT NULL,
            last_checked TEXT NOT NULL,
            last_scraped TEXT NOT NULL,
            check_count INTEGER DEFAULT 1,
            
            -- Derived
            primary_topic TEXT DEFAULT '',
            domain_category TEXT DEFAULT ''
        );
        
        CREATE TABLE IF NOT EXISTS update_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,      -- scrape, purge, score, check_alive
            repos_added INTEGER DEFAULT 0,
            repos_updated INTEGER DEFAULT 0,
            repos_purged INTEGER DEFAULT 0,
            details TEXT DEFAULT '',
            changelog TEXT DEFAULT ''   -- JSON list of specific repo changes
        );
        
        CREATE INDEX IF NOT EXISTS idx_repos_stars ON repos(stars DESC);
        CREATE INDEX IF NOT EXISTS idx_repos_quality ON repos(quality_score DESC);
        CREATE INDEX IF NOT EXISTS idx_repos_freshness ON repos(freshness_status);
        CREATE INDEX IF NOT EXISTS idx_repos_popularity ON repos(popularity_tier);
        CREATE INDEX IF NOT EXISTS idx_repos_purged ON repos(purged);
        CREATE INDEX IF NOT EXISTS idx_repos_primary_topic ON repos(primary_topic);
    """)
    
    return db


def import_scraped(repos: list[dict], db_path: str = DB_PATH) -> dict:
    """Import scraped repos into database. Merges with existing data."""
    db = get_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    updated = 0
    unpurged = 0
    
    for repo in repos:
        key = repo["repo_key"].lower()
        existing = db.execute("SELECT * FROM repos WHERE repo_key = ?", (key,)).fetchone()
        
        if existing:
            # Un-purge if repo reappears in scrape with signs of life
            was_purged = existing["purged"]
            should_unpurge = (
                was_purged and 
                repo["stars"] > 0 and 
                repo.get("last_updated")  # has recent activity
            )
            
            # Update with fresh data
            db.execute("""
                UPDATE repos SET
                    stars = ?, forks = ?, projects = ?,
                    description = CASE WHEN ? != '' THEN ? ELSE description END,
                    topics = ?, last_updated = ?,
                    last_scraped = ?, last_checked = ?,
                    check_count = check_count + 1,
                    purged = CASE WHEN ? THEN 0 ELSE purged END,
                    purge_reason = CASE WHEN ? THEN NULL ELSE purge_reason END,
                    alive = CASE WHEN ? THEN 1 ELSE alive END
                WHERE repo_key = ?
            """, (
                repo["stars"], repo["forks"], repo["projects"],
                repo.get("description", ""), repo.get("description", ""),
                json.dumps(repo.get("topics", [])),
                repo.get("last_updated"),
                now, now,
                should_unpurge, should_unpurge, should_unpurge,
                key
            ))
            if should_unpurge:
                unpurged += 1
            updated += 1
        else:
            # Insert new
            db.execute("""
                INSERT INTO repos (
                    repo_key, name, owner, description, url, ecosystems_url,
                    stars, forks, projects, topics, last_updated,
                    first_seen, last_checked, last_scraped
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                key,
                repo["name"],
                repo.get("owner", key.split("/")[0] if "/" in key else ""),
                repo.get("description", ""),
                repo.get("url", f"https://github.com/{key}"),
                repo.get("ecosystems_url", ""),
                repo["stars"], repo["forks"], repo.get("projects", 0),
                json.dumps(repo.get("topics", [])),
                repo.get("last_updated"),
                now, now, now
            ))
            added += 1
    
    db.execute("""
        INSERT INTO update_log (timestamp, action, repos_added, repos_updated, details)
        VALUES (?, 'scrape', ?, ?, ?)
    """, (now, added, updated, json.dumps({
        "total_input": len(repos),
        "added": added,
        "updated": updated,
        "unpurged": unpurged,
    })))
    
    db.commit()
    db.close()
    
    return {"added": added, "updated": updated, "unpurged": unpurged, "total_input": len(repos)}


def compute_scores(db_path: str = DB_PATH):
    """Compute freshness, popularity, breadth, quality scores for all repos."""
    db = get_db(db_path)
    now = datetime.now(timezone.utc)
    rows = db.execute("SELECT * FROM repos WHERE purged = 0").fetchall()
    
    # Get max values for normalization
    max_stars = max((r["stars"] for r in rows), default=1) or 1
    max_forks = max((r["forks"] for r in rows), default=1) or 1
    max_projects = max((r["projects"] for r in rows), default=1) or 1
    
    for row in rows:
        key = row["repo_key"]
        
        # --- Freshness ---
        freshness = "unknown"
        if row["last_updated"]:
            try:
                lu = datetime.strptime(row["last_updated"], "%Y-%m-%d")
                days_ago = (now - lu.replace(tzinfo=timezone.utc)).days
                if days_ago <= 90:
                    freshness = "active"
                elif days_ago <= 365:
                    freshness = "stale"
                else:
                    freshness = "abandoned"
            except ValueError:
                pass
        
        # --- Popularity tier ---
        s = row["stars"]
        if s >= 50000:
            pop = "mega"
        elif s >= 10000:
            pop = "high"
        elif s >= 1000:
            pop = "mid"
        elif s >= 100:
            pop = "low"
        else:
            pop = "micro"
        
        # --- Breadth tier ---
        p = row["projects"]
        if p >= 500:
            breadth = "massive"
        elif p >= 100:
            breadth = "large"
        elif p >= 30:
            breadth = "medium"
        elif p >= 5:
            breadth = "small"
        else:
            breadth = "tiny"
        
        # --- Quality score (0-100) ---
        # Weighted: log(stars) 45%, freshness 25%, forks 10%, projects 10%, topics 10%
        star_score = (math.log1p(s) / math.log1p(max_stars)) * 45
        
        fresh_map = {"active": 25, "stale": 12, "abandoned": 3, "unknown": 8}
        fresh_score = fresh_map.get(freshness, 8)
        
        proj_score = (math.log1p(row["projects"]) / math.log1p(max_projects)) * 10
        fork_score = (math.log1p(row["forks"]) / math.log1p(max_forks)) * 10
        
        topics = json.loads(row["topics"]) if row["topics"] else []
        topic_score = min(len(topics), 10) / 10 * 10
        
        quality = round(star_score + fresh_score + proj_score + fork_score + topic_score, 2)
        
        # --- Primary topic ---
        skip_topics = {"awesome-list", "awesome", "list", "lists", "resources", "resource", "curated-list"}
        primary = ""
        for t in topics:
            if t.lower() not in skip_topics:
                primary = t
                break
        
        # --- Domain category ---
        topic_set = {t.lower() for t in topics}
        domain = categorize_domain(topic_set, row["description"].lower() if row["description"] else "")
        
        db.execute("""
            UPDATE repos SET
                freshness_status = ?, popularity_tier = ?, breadth_tier = ?,
                quality_score = ?, primary_topic = ?, domain_category = ?
            WHERE repo_key = ?
        """, (freshness, pop, breadth, quality, primary, domain, key))
    
    db.execute("""
        INSERT INTO update_log (timestamp, action, details)
        VALUES (?, 'score', ?)
    """, (now.isoformat(), f"Scored {len(rows)} repos"))
    
    db.commit()
    db.close()
    print(f"Scored {len(rows)} repos")


def _word_match(keyword: str, text: str) -> bool:
    """Check if keyword appears as a whole word in text (not as a substring).
    Uses regex word boundaries to avoid 'ai' matching 'maintaining' etc.
    """
    import re
    # Escape the keyword for regex safety, then wrap in word boundaries
    pattern = r'\b' + re.escape(keyword) + r'\b'
    return bool(re.search(pattern, text))


def categorize_domain(topics: set, desc: str) -> str:
    """Categorize a repo into a broad domain based on topics and description.
    
    Rules are ordered from most specific to most generic. 
    Programming Languages is checked LAST as a fallback since many repos 
    have language tags but are really about a specific domain.
    
    Description matching uses word-boundary regex to prevent false positives
    (e.g. "ai" won't match "maintaining", "ml" won't match "html").
    """
    # Specific domains first (high priority)
    specific_rules = [
        ({"security", "cybersecurity", "hacking", "pentesting", "ctf", "privacy",
          "encryption", "infosec", "vulnerability", "malware", "osint", "forensics",
          "reverse-engineering", "bug-bounty", "pentest"}, "Security"),
        ({"ai", "machine-learning", "ml", "deep-learning", "llm", "nlp", "gpt", 
          "artificial-intelligence", "neural-network", "computer-vision", "data-science",
          "chatgpt", "openai", "transformers", "generative-ai", "langchain", "rag",
          "stable-diffusion", "llms", "ai-agents", "mcp"}, "AI & ML"),
        ({"devops", "docker", "kubernetes", "ci-cd", "infrastructure", "cloud",
          "aws", "terraform", "ansible", "sre", "monitoring", "observability",
          "cicd", "helm", "k8s", "serverless"}, "DevOps & Infrastructure"),
        ({"blockchain", "web3", "crypto", "ethereum", "solidity", "defi",
          "bitcoin", "nft", "smart-contracts", "cryptocurrency"}, "Web3 & Crypto"),
        ({"self-hosted", "selfhosted", "homelab", "self-hosting"}, "Self-Hosted"),
        ({"game", "gaming", "gamedev", "unity", "unreal", "godot",
          "game-development"}, "Gaming"),
        ({"education", "learning", "tutorial", "course", "interview",
          "coding-interview", "algorithms", "leetcode", "study"}, "Education & Learning"),
        ({"data", "database", "sql", "nosql", "postgresql", "mongodb",
          "data-engineering", "big-data", "apache-spark", "etl"}, "Data & Databases"),
        ({"design", "ui", "ux", "figma", "creative", "icons", "fonts",
          "typography", "color"}, "Design"),
        ({"android", "ios", "mobile", "flutter", "react-native", "swift",
          "kotlin"}, "Mobile"),
        ({"api", "rest", "graphql", "microservices", "grpc"}, "APIs & Services"),
        ({"linux", "macos", "windows", "cli", "terminal", "shell", "bash",
          "zsh", "dotfiles", "command-line"}, "OS & CLI Tools"),
        ({"robotics", "iot", "hardware", "raspberry-pi", "arduino", "embedded",
          "3d-printing", "home-automation", "sensor"}, "Robotics & Hardware"),
        ({"testing", "developer-tools", "devtools", "vscode", "git", "ide",
          "debugging", "linting", "documentation"}, "Developer Tools"),
        ({"books", "reading", "writing", "blogging", "blog", "content",
          "publishing", "journalism", "podcast"}, "Media & Content"),
        ({"startups", "marketing", "productivity", "leadership", "management",
          "business", "finance", "saas", "remote-work"}, "Business & Startups"),
        ({"networking", "network", "protocol", "http", "dns", "proxy",
          "vpn", "p2p", "distributed-systems"}, "Networking"),
        ({"music", "audio", "video", "media", "streaming", "ffmpeg",
          "image-processing", "photography"}, "Audio & Video"),
    ]
    
    # Check specific domains first (topic match — exact set intersection, always safe)
    for keywords, category in specific_rules:
        if topics & keywords:
            return category
    
    # Check specific domains by description (word-boundary match to prevent false positives)
    # Hyphenated topic keywords like "machine-learning" also match space-separated "machine learning"
    for keywords, category in specific_rules:
        for kw in keywords:
            if _word_match(kw, desc):
                return category
            # Also try space variant of hyphenated keywords
            if "-" in kw and _word_match(kw.replace("-", " "), desc):
                return category
    
    # Web Development (broader, checked after specifics)
    web_kw = {"web", "frontend", "backend", "css", "html", "react", "vue", "angular",
              "nextjs", "web-development", "javascript", "typescript", "nodejs",
              "tailwindcss", "svelte", "webpack"}
    if topics & web_kw:
        return "Web Development"
    for kw in web_kw:
        if _word_match(kw, desc):
            return "Web Development"
    
    # Programming Languages (most generic - last resort before Other)
    lang_kw = {"python", "java", "rust", "go", "golang", "cpp", "ruby", "php",
               "scala", "elixir", "haskell", "lua", "perl", "r-programming",
               "c-sharp", "csharp", "dotnet"}
    if topics & lang_kw:
        return "Programming Languages"
    
    return "Other"


def auto_purge(db_path: str = DB_PATH, dry_run: bool = False) -> dict:
    """Auto-purge dead, archived, and long-abandoned repos."""
    db = get_db(db_path)
    now = datetime.now(timezone.utc)
    purged = 0
    reasons = {}
    
    rows = db.execute("SELECT * FROM repos WHERE purged = 0").fetchall()
    purged_names = []
    
    for row in rows:
        reason = None
        
        # Dead repos (confirmed not alive)
        if not row["alive"]:
            reason = "dead_404"
        
        # Archived repos
        elif row["archived"]:
            reason = "archived"
        
        # Zero-value: no stars, no forks, negligible projects
        elif row["stars"] == 0 and row["forks"] == 0 and row["projects"] < 5:
            reason = "zero_value"
        
        # Abandoned: no update in 3+ years AND very low stars
        elif row["freshness_status"] == "abandoned" and row["stars"] < 50:
            reason = "abandoned_low_value"
        
        if reason and not dry_run:
            db.execute("""
                UPDATE repos SET purged = 1, purge_reason = ? WHERE repo_key = ?
            """, (reason, row["repo_key"]))
            purged += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            purged_names.append(row["repo_key"])
        elif reason:
            purged += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            purged_names.append(row["repo_key"])
    
    if not dry_run:
        db.execute("""
            INSERT INTO update_log (timestamp, action, repos_purged, details, changelog)
            VALUES (?, 'purge', ?, ?, ?)
        """, (now.isoformat(), purged, json.dumps(reasons),
              json.dumps(purged_names[:200])))  # cap at 200 to avoid huge entries
        db.commit()
    
    db.close()
    return {"purged": purged, "reasons": reasons, "purged_names": purged_names, "dry_run": dry_run}


def search(query: str = "", topic: str = "", domain: str = "", 
           freshness: str = "", popularity: str = "",
           min_stars: int = 0, limit: int = 50, offset: int = 0,
           sort: str = "quality_score", order: str = "DESC",
           db_path: str = DB_PATH) -> list[dict]:
    """Search the catalogue with filters."""
    db = get_db(db_path)
    
    where = ["purged = 0"]
    params = []
    
    if query:
        where.append("(name LIKE ? OR description LIKE ? OR topics LIKE ?)")
        q = f"%{query}%"
        params.extend([q, q, q])
    
    if topic:
        where.append("topics LIKE ?")
        params.append(f'%"{topic}"%')
    
    if domain:
        where.append("domain_category = ?")
        params.append(domain)
    
    if freshness:
        where.append("freshness_status = ?")
        params.append(freshness)
    
    if popularity:
        where.append("popularity_tier = ?")
        params.append(popularity)
    
    if min_stars > 0:
        where.append("stars >= ?")
        params.append(min_stars)
    
    # Validate sort column
    valid_sorts = {"quality_score", "stars", "forks", "projects", "last_updated", "name"}
    if sort not in valid_sorts:
        sort = "quality_score"
    order = "DESC" if order.upper() == "DESC" else "ASC"
    
    sql = f"""
        SELECT * FROM repos 
        WHERE {' AND '.join(where)}
        ORDER BY {sort} {order}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    
    rows = db.execute(sql, params).fetchall()
    db.close()
    
    return [dict(r) for r in rows]


def get_stats(db_path: str = DB_PATH) -> dict:
    """Get catalogue statistics."""
    db = get_db(db_path)
    
    total = db.execute("SELECT COUNT(*) FROM repos WHERE purged = 0").fetchone()[0]
    purged = db.execute("SELECT COUNT(*) FROM repos WHERE purged = 1").fetchone()[0]
    
    # By freshness
    freshness = {}
    for row in db.execute("SELECT freshness_status, COUNT(*) as c FROM repos WHERE purged = 0 GROUP BY freshness_status"):
        freshness[row[0]] = row[1]
    
    # By popularity
    popularity = {}
    for row in db.execute("SELECT popularity_tier, COUNT(*) as c FROM repos WHERE purged = 0 GROUP BY popularity_tier"):
        popularity[row[0]] = row[1]
    
    # By domain
    domains = {}
    for row in db.execute("SELECT domain_category, COUNT(*) as c FROM repos WHERE purged = 0 GROUP BY domain_category ORDER BY c DESC"):
        domains[row[0]] = row[1]
    
    # Top topics
    all_topics = {}
    for row in db.execute("SELECT topics FROM repos WHERE purged = 0"):
        for t in json.loads(row[0] or "[]"):
            tl = t.lower()
            if tl not in {"awesome-list", "awesome", "list", "lists"}:
                all_topics[tl] = all_topics.get(tl, 0) + 1
    top_topics = sorted(all_topics.items(), key=lambda x: -x[1])[:30]
    
    # Last update
    last_log = db.execute("SELECT timestamp, action FROM update_log ORDER BY id DESC LIMIT 1").fetchone()
    
    db.close()
    
    return {
        "total_active": total,
        "total_purged": purged,
        "freshness": freshness,
        "popularity": popularity,
        "domains": domains,
        "top_topics": top_topics,
        "last_update": dict(last_log) if last_log else None,
    }


def export_json(db_path: str = DB_PATH, output: str = None, include_purged: bool = False) -> str:
    """Export catalogue to JSON file."""
    db = get_db(db_path)
    where = "" if include_purged else "WHERE purged = 0"
    rows = db.execute(f"SELECT * FROM repos {where} ORDER BY quality_score DESC").fetchall()
    db.close()
    
    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total": len(rows),
        "repos": [dict(r) for r in rows],
    }
    
    if not output:
        output = db_path.replace(".db", "_export.json")
    
    with open(output, "w") as f:
        json.dump(data, f, indent=2)
    
    return output


def export_csv(db_path: str = DB_PATH, output: str = None) -> str:
    """Export catalogue to CSV."""
    import csv
    db = get_db(db_path)
    rows = db.execute("SELECT * FROM repos WHERE purged = 0 ORDER BY quality_score DESC").fetchall()
    db.close()
    
    if not output:
        output = db_path.replace(".db", "_export.csv")
    
    fields = ["repo_key", "name", "owner", "description", "url", "stars", "forks", 
              "projects", "topics", "last_updated", "freshness_status", "popularity_tier",
              "breadth_tier", "quality_score", "primary_topic", "domain_category"]
    
    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    
    return output


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: catalogue.py [import|score|purge|search|stats|export_json|export_csv]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "import":
        raw_path = sys.argv[2] if len(sys.argv) > 2 else "/work/skills/awesome_catalogue/data/raw_scrape.json"
        with open(raw_path) as f:
            repos = json.load(f)
        result = import_scraped(repos)
        print(f"Import: {result}")
    
    elif cmd == "score":
        compute_scores()
    
    elif cmd == "purge":
        dry = "--dry-run" in sys.argv
        result = auto_purge(dry_run=dry)
        print(f"Purge: {result}")
    
    elif cmd == "search":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        results = search(query=q, limit=20)
        for r in results:
            print(f"  [{r['quality_score']:5.1f}] {r['repo_key']:40s} ★{r['stars']:>7,}  {r['freshness_status']:10s}  {r['domain_category']}")
    
    elif cmd == "stats":
        stats = get_stats()
        print(json.dumps(stats, indent=2))
    
    elif cmd == "export_json":
        path = export_json()
        print(f"Exported to {path}")
    
    elif cmd == "export_csv":
        path = export_csv()
        print(f"Exported to {path}")
    
    else:
        print(f"Unknown command: {cmd}")
