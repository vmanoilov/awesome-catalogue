"""
Ecosyste.ms Awesome-List Scraper
Fetches all awesome-list repos from Ecosyste.ms, parses HTML cards,
returns structured data.
"""
import re
import time
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from html.parser import HTMLParser
from bs4 import BeautifulSoup


BASE_URL = "https://awesome.ecosyste.ms/lists"
DEFAULT_TOPIC = "awesome-list"
PER_PAGE = 100  # conservative to avoid rate limits
MAX_PAGES = 100  # safety cap


def fetch_page(topic: str, page: int, per_page: int = PER_PAGE) -> str:
    """Fetch a single HTML page from Ecosyste.ms."""
    url = f"{BASE_URL}?topic={topic}&page={page}&per_page={per_page}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "AwesomeCatalogue/1.0 (automated-catalogue-builder)",
        "Accept": "text/html",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} on page {page}")
        return ""
    except Exception as e:
        print(f"  Error fetching page {page}: {e}")
        return ""


def parse_cards(html: str) -> list[dict]:
    """Parse repo cards from Ecosyste.ms HTML page."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div.card")
    repos = []
    
    for card in cards:
        try:
            # Title and link
            title_link = card.select_one("h5.card-title a")
            if not title_link:
                continue
            
            name = title_link.get_text(strip=True)
            href = title_link.get("href", "")
            # href like /lists/owner%2Frepo
            repo_key = href.replace("/lists/", "").replace("%2F", "/") if href else ""
            
            # Description
            desc_el = card.select_one("p.card-subtitle.mb-2.text-muted")
            description = desc_el.get_text(strip=True) if desc_el else ""
            
            # Topics/badges
            topics = []
            badges = card.select("span.badge a")
            for badge in badges:
                t = badge.get_text(strip=True)
                if t:
                    topics.append(t)
            
            # Stars, forks, projects
            stats_els = card.select("p.card-subtitle i small")
            stars = 0
            forks = 0
            projects = 0
            last_updated = None
            
            for stat_el in stats_els:
                text = stat_el.get_text(strip=True)
                
                # Parse "485,939 stars"
                m = re.search(r"([\d,]+)\s*stars?", text)
                if m:
                    stars = int(m.group(1).replace(",", ""))
                
                m = re.search(r"([\d,]+)\s*forks?", text)
                if m:
                    forks = int(m.group(1).replace(",", ""))
                
                m = re.search(r"([\d,]+)\s*projects?", text)
                if m:
                    projects = int(m.group(1).replace(",", ""))
                
                # "Last updated: 04 Apr 2026"
                m = re.search(r"Last updated:\s*(.+)", text)
                if m:
                    try:
                        last_updated = datetime.strptime(m.group(1).strip(), "%d %b %Y").strftime("%Y-%m-%d")
                    except ValueError:
                        last_updated = m.group(1).strip()
            
            if not repo_key:
                continue
            
            owner = repo_key.split("/")[0] if "/" in repo_key else ""
            
            repos.append({
                "repo_key": repo_key,
                "name": name,
                "owner": owner,
                "description": description,
                "topics": topics,
                "stars": stars,
                "forks": forks,
                "projects": projects,
                "last_updated": last_updated,
                "url": f"https://github.com/{repo_key}",
                "ecosystems_url": f"https://awesome.ecosyste.ms/lists/{repo_key.replace('/', '%2F')}",
            })
        except Exception as e:
            continue
    
    return repos


def scrape_all(topic: str = DEFAULT_TOPIC, per_page: int = PER_PAGE, delay: float = 1.0) -> list[dict]:
    """Scrape all pages for a given topic. Returns deduplicated list of repos."""
    all_repos = {}
    page = 1
    empty_count = 0
    
    print(f"Scraping Ecosyste.ms awesome lists (topic={topic})...")
    
    while page <= MAX_PAGES:
        print(f"  Page {page}...", end=" ", flush=True)
        html = fetch_page(topic, page, per_page)
        
        if not html:
            empty_count += 1
            if empty_count >= 2:
                print("Two empty pages in a row, stopping.")
                break
            page += 1
            continue
        
        repos = parse_cards(html)
        print(f"{len(repos)} repos found")
        
        if len(repos) == 0:
            empty_count += 1
            if empty_count >= 2:
                break
            page += 1
            continue
        
        empty_count = 0
        
        for repo in repos:
            key = repo["repo_key"].lower()
            # Keep the entry with more data / higher stars if duplicate
            if key not in all_repos or repo["stars"] > all_repos[key]["stars"]:
                all_repos[key] = repo
        
        page += 1
        if delay > 0:
            time.sleep(delay)
    
    result = list(all_repos.values())
    print(f"\nTotal unique repos: {len(result)}")
    
    # Safety check: if we got suspiciously few results, the HTML structure may have changed
    if len(result) < 100 and page > 2:
        print(f"WARNING: Only {len(result)} repos found across {page} pages — HTML structure may have changed!")
        print("Returning empty to prevent overwriting good data with bad scrape.")
        return []
    
    return result


def check_repo_alive(repo_key: str) -> dict:
    """Quick check if a GitHub repo is still accessible. Uses GITHUB_TOKEN env var if available."""
    import os
    url = f"https://api.github.com/repos/{repo_key}"
    headers = {
        "User-Agent": "AwesomeCatalogue/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "alive": True,
                "archived": data.get("archived", False),
                "disabled": data.get("disabled", False),
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "pushed_at": data.get("pushed_at", ""),
                "description": data.get("description", ""),
                "topics": data.get("topics", []),
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"alive": False, "archived": False, "disabled": False}
        return {"alive": True, "archived": False, "disabled": False}  # rate limit etc
    except Exception:
        return {"alive": True, "archived": False, "disabled": False}


if __name__ == "__main__":
    repos = scrape_all()
    # Save raw JSON
    out_path = "/work/skills/awesome_catalogue/data/raw_scrape.json"
    with open(out_path, "w") as f:
        json.dump(repos, f, indent=2)
    print(f"Saved {len(repos)} repos to {out_path}")
