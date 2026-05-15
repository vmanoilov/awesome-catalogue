"""
Build a standalone HTML viewer for the awesome-list catalogue.
Single file, works offline, mobile-responsive.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from catalogue import get_db, get_stats, DB_PATH


def build_html(db_path: str = DB_PATH, output: str = None) -> str:
    """Build standalone HTML viewer with embedded data."""
    db = get_db(db_path)
    rows = db.execute("""
        SELECT repo_key, name, owner, description, url, ecosystems_url,
               stars, forks, projects, topics, last_updated,
               freshness_status, popularity_tier, breadth_tier,
               quality_score, primary_topic, domain_category
        FROM repos WHERE purged = 0 
        ORDER BY quality_score DESC
    """).fetchall()
    db.close()
    
    repos_json = json.dumps([dict(r) for r in rows])
    stats = get_stats(db_path)
    stats_json = json.dumps(stats, default=str)
    
    if not output:
        output = os.path.join(os.path.dirname(db_path), "awesome_catalogue.html")
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Awesome-List Catalogue</title>
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --surface2: #21262d; --border: #30363d;
    --text: #e6edf3; --text2: #8b949e; --accent: #58a6ff; --green: #3fb950;
    --yellow: #d29922; --red: #f85149; --purple: #bc8cff;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ 
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.5;
    min-height: 100vh;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 16px; }}
  
  /* Header */
  .header {{ 
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 20px 0; margin-bottom: 20px; position: sticky; top: 0; z-index: 100;
  }}
  .header h1 {{ font-size: 1.4rem; display: flex; align-items: center; gap: 8px; }}
  .header h1 span {{ font-size: 1.8rem; }}
  .header .subtitle {{ color: var(--text2); font-size: 0.85rem; margin-top: 4px; }}
  
  /* Stats bar */
  .stats-bar {{ 
    display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px;
    padding: 12px; background: var(--surface); border-radius: 8px; border: 1px solid var(--border);
  }}
  .stat {{ text-align: center; flex: 1; min-width: 80px; }}
  .stat .num {{ font-size: 1.4rem; font-weight: 700; color: var(--accent); }}
  .stat .label {{ font-size: 0.7rem; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; }}
  
  /* Filters */
  .filters {{
    display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px;
    padding: 12px; background: var(--surface); border-radius: 8px; border: 1px solid var(--border);
  }}
  .filters input, .filters select {{
    background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    padding: 8px 12px; border-radius: 6px; font-size: 0.9rem; outline: none;
  }}
  .filters input {{ flex: 1; min-width: 200px; }}
  .filters input:focus, .filters select:focus {{ border-color: var(--accent); }}
  .filters select {{ min-width: 130px; cursor: pointer; }}
  
  /* Results info */
  .results-info {{ 
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 0; color: var(--text2); font-size: 0.85rem; margin-bottom: 8px;
  }}
  
  /* Repo cards */
  .repo-list {{ display: flex; flex-direction: column; gap: 8px; }}
  .repo-card {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 14px 16px; transition: border-color 0.15s;
    display: grid; grid-template-columns: 1fr auto; gap: 8px;
  }}
  .repo-card:hover {{ border-color: var(--accent); }}
  .repo-name {{ font-weight: 600; color: var(--accent); text-decoration: none; font-size: 0.95rem; }}
  .repo-name:hover {{ text-decoration: underline; }}
  .repo-owner {{ color: var(--text2); font-size: 0.8rem; }}
  .repo-desc {{ color: var(--text2); font-size: 0.85rem; margin: 4px 0; line-height: 1.4; }}
  .repo-meta {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-top: 6px; }}
  .repo-meta span {{ font-size: 0.78rem; color: var(--text2); display: flex; align-items: center; gap: 3px; }}
  .repo-score {{ 
    font-size: 1.1rem; font-weight: 700; text-align: right; 
    display: flex; flex-direction: column; align-items: flex-end; justify-content: center;
  }}
  .repo-score .score-num {{ color: var(--green); }}
  .repo-score .score-label {{ font-size: 0.65rem; color: var(--text2); text-transform: uppercase; }}
  
  /* Tags */
  .tags {{ display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px; }}
  .tag {{
    background: var(--surface2); border: 1px solid var(--border); border-radius: 12px;
    padding: 2px 8px; font-size: 0.7rem; color: var(--text2); cursor: pointer;
  }}
  .tag:hover {{ border-color: var(--accent); color: var(--accent); }}
  .tag.domain {{ background: rgba(88,166,255,0.1); border-color: rgba(88,166,255,0.3); color: var(--accent); }}
  
  /* Badges */
  .badge {{
    display: inline-block; padding: 1px 6px; border-radius: 10px;
    font-size: 0.7rem; font-weight: 600;
  }}
  .badge.active {{ background: rgba(63,185,80,0.15); color: var(--green); }}
  .badge.stale {{ background: rgba(210,153,34,0.15); color: var(--yellow); }}
  .badge.abandoned {{ background: rgba(248,81,73,0.15); color: var(--red); }}
  .badge.mega {{ background: rgba(188,140,255,0.15); color: var(--purple); }}
  .badge.high {{ background: rgba(63,185,80,0.15); color: var(--green); }}
  
  /* Pagination */
  .pagination {{
    display: flex; justify-content: center; gap: 8px; margin: 20px 0; flex-wrap: wrap;
  }}
  .pagination button {{
    background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 0.85rem;
  }}
  .pagination button:hover {{ border-color: var(--accent); }}
  .pagination button.active {{ background: var(--accent); color: var(--bg); border-color: var(--accent); }}
  .pagination button:disabled {{ opacity: 0.3; cursor: default; }}
  
  /* Export bar */
  .export-bar {{ 
    display: flex; gap: 8px; padding: 12px; margin-top: 16px;
    background: var(--surface); border-radius: 8px; border: 1px solid var(--border);
  }}
  .export-bar button {{
    background: var(--surface2); border: 1px solid var(--border); color: var(--accent);
    padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 0.85rem;
  }}
  .export-bar button:hover {{ background: var(--accent); color: var(--bg); }}
  
  /* Footer */
  .footer {{ text-align: center; padding: 20px; color: var(--text2); font-size: 0.75rem; }}
  
  /* Mobile */
  @media (max-width: 640px) {{
    .repo-card {{ grid-template-columns: 1fr; }}
    .repo-score {{ flex-direction: row; gap: 6px; align-items: center; }}
    .filters {{ flex-direction: column; }}
    .filters input, .filters select {{ min-width: 100%; }}
    .stats-bar {{ gap: 6px; }}
    .stat .num {{ font-size: 1.1rem; }}
  }}
</style>
</head>
<body>

<div class="header">
  <div class="container">
    <h1><span>📚</span> Awesome-List Catalogue</h1>
    <div class="subtitle" id="subtitle">Loading...</div>
  </div>
</div>

<div class="container">
  <div class="stats-bar" id="stats-bar"></div>
  
  <div class="filters">
    <input type="text" id="search" placeholder="🔍 Search repos, topics, descriptions..." autocomplete="off">
    <select id="filter-domain"><option value="">All Domains</option></select>
    <select id="filter-freshness">
      <option value="">All Freshness</option>
      <option value="active">🟢 Active</option>
      <option value="stale">🟡 Stale</option>
      <option value="abandoned">🔴 Abandoned</option>
    </select>
    <select id="filter-popularity">
      <option value="">All Popularity</option>
      <option value="mega">🏆 Mega (50K+)</option>
      <option value="high">⭐ High (10K+)</option>
      <option value="mid">📈 Mid (1K+)</option>
      <option value="low">📊 Low (100+)</option>
      <option value="micro">🔬 Micro (&lt;100)</option>
    </select>
    <select id="sort-by">
      <option value="quality_score">Sort: Quality</option>
      <option value="stars">Sort: Stars</option>
      <option value="projects">Sort: Projects</option>
      <option value="last_updated">Sort: Recently Updated</option>
      <option value="name">Sort: Name</option>
    </select>
  </div>
  
  <div class="results-info" id="results-info"></div>
  <div class="repo-list" id="repo-list"></div>
  <div class="pagination" id="pagination"></div>
  
  <div class="export-bar">
    <button onclick="exportFiltered('json')">📥 Export JSON</button>
    <button onclick="exportFiltered('csv')">📥 Export CSV</button>
    <button onclick="copyToClipboard()">📋 Copy to Clipboard</button>
  </div>
</div>

<div class="footer">
  Awesome-List Catalogue · Data from <a href="https://awesome.ecosyste.ms" style="color:var(--accent)">Ecosyste.ms</a> · Built by Viktor
</div>

<script>
const ALL_REPOS = {repos_json};
const STATS = {stats_json};
const PAGE_SIZE = 50;
let filtered = ALL_REPOS;
let currentPage = 1;

function init() {{
  document.getElementById('subtitle').textContent = 
    ALL_REPOS.length.toLocaleString() + ' awesome lists · Auto-updated daily';
  
  renderStats();
  populateDomainFilter();
  applyFilters();
  
  document.getElementById('search').addEventListener('input', debounce(applyFilters, 200));
  ['filter-domain','filter-freshness','filter-popularity','sort-by'].forEach(id => {{
    document.getElementById(id).addEventListener('change', applyFilters);
  }});
}}

function renderStats() {{
  const s = STATS;
  const bar = document.getElementById('stats-bar');
  bar.innerHTML = `
    <div class="stat"><div class="num">${{s.total_active.toLocaleString()}}</div><div class="label">Active Repos</div></div>
    <div class="stat"><div class="num">${{(s.freshness.active||0).toLocaleString()}}</div><div class="label">🟢 Active</div></div>
    <div class="stat"><div class="num">${{(s.freshness.stale||0).toLocaleString()}}</div><div class="label">🟡 Stale</div></div>
    <div class="stat"><div class="num">${{(s.freshness.abandoned||0).toLocaleString()}}</div><div class="label">🔴 Abandoned</div></div>
    <div class="stat"><div class="num">${{(s.popularity.mega||0)+(s.popularity.high||0)}}</div><div class="label">⭐ 10K+ Stars</div></div>
    <div class="stat"><div class="num">${{Object.keys(s.domains).length}}</div><div class="label">Domains</div></div>
  `;
}}

function populateDomainFilter() {{
  const sel = document.getElementById('filter-domain');
  const domains = {{}};
  ALL_REPOS.forEach(r => {{ if(r.domain_category) domains[r.domain_category] = (domains[r.domain_category]||0)+1; }});
  Object.entries(domains).sort((a,b) => b[1]-a[1]).forEach(([d,c]) => {{
    const opt = document.createElement('option');
    opt.value = d; opt.textContent = `${{d}} (${{c}})`;
    sel.appendChild(opt);
  }});
}}

function applyFilters() {{
  const q = document.getElementById('search').value.toLowerCase().trim();
  const domain = document.getElementById('filter-domain').value;
  const freshness = document.getElementById('filter-freshness').value;
  const popularity = document.getElementById('filter-popularity').value;
  const sortBy = document.getElementById('sort-by').value;
  
  filtered = ALL_REPOS.filter(r => {{
    if(q) {{
      const hay = (r.name + ' ' + r.description + ' ' + r.topics + ' ' + r.owner + ' ' + r.primary_topic).toLowerCase();
      if(!hay.includes(q)) return false;
    }}
    if(domain && r.domain_category !== domain) return false;
    if(freshness && r.freshness_status !== freshness) return false;
    if(popularity && r.popularity_tier !== popularity) return false;
    return true;
  }});
  
  filtered.sort((a,b) => {{
    if(sortBy === 'name') return a.name.localeCompare(b.name);
    if(sortBy === 'last_updated') return (b.last_updated||'').localeCompare(a.last_updated||'');
    return (b[sortBy]||0) - (a[sortBy]||0);
  }});
  
  currentPage = 1;
  renderResults();
}}

function renderResults() {{
  const total = filtered.length;
  const pages = Math.ceil(total / PAGE_SIZE);
  const start = (currentPage - 1) * PAGE_SIZE;
  const slice = filtered.slice(start, start + PAGE_SIZE);
  
  document.getElementById('results-info').textContent = 
    `Showing ${{start+1}}-${{Math.min(start+PAGE_SIZE, total)}} of ${{total.toLocaleString()}} repos`;
  
  const list = document.getElementById('repo-list');
  list.innerHTML = slice.map(r => {{
    const topics = JSON.parse(r.topics || '[]').filter(t => !['awesome-list','awesome','list','lists'].includes(t.toLowerCase())).slice(0,6);
    const freshBadge = r.freshness_status === 'active' ? '<span class="badge active">active</span>' :
                       r.freshness_status === 'stale' ? '<span class="badge stale">stale</span>' :
                       r.freshness_status === 'abandoned' ? '<span class="badge abandoned">abandoned</span>' : '';
    const popBadge = r.popularity_tier === 'mega' ? '<span class="badge mega">mega</span>' :
                     r.popularity_tier === 'high' ? '<span class="badge high">high</span>' : '';
    
    return `<div class="repo-card">
      <div>
        <a class="repo-name" href="${{r.url}}" target="_blank" rel="noopener">${{esc(r.name)}}</a>
        <span class="repo-owner">${{esc(r.owner)}}</span>
        <div class="repo-desc">${{esc(r.description || 'No description')}}</div>
        <div class="repo-meta">
          <span>⭐ ${{r.stars.toLocaleString()}}</span>
          <span>🍴 ${{r.forks.toLocaleString()}}</span>
          <span>📦 ${{r.projects}} projects</span>
          ${{r.last_updated ? '<span>📅 '+r.last_updated+'</span>' : ''}}
          ${{freshBadge}} ${{popBadge}}
        </div>
        <div class="tags">
          ${{r.domain_category ? '<span class="tag domain" onclick="filterByDomain(\\''+esc(r.domain_category)+'\\')">'+esc(r.domain_category)+'</span>' : ''}}
          ${{topics.map(t => '<span class="tag" onclick="filterByTopic(\\''+esc(t)+'\\')">'+esc(t)+'</span>').join('')}}
        </div>
      </div>
      <div class="repo-score">
        <span class="score-num">${{r.quality_score.toFixed(0)}}</span>
        <span class="score-label">quality</span>
      </div>
    </div>`;
  }}).join('');
  
  renderPagination(pages);
}}

function renderPagination(pages) {{
  const el = document.getElementById('pagination');
  if(pages <= 1) {{ el.innerHTML = ''; return; }}
  
  let html = '';
  html += `<button ${{currentPage===1?'disabled':''}} onclick="goPage(${{currentPage-1}})">← Prev</button>`;
  
  const range = [];
  for(let i = Math.max(1, currentPage-2); i <= Math.min(pages, currentPage+2); i++) range.push(i);
  if(range[0] > 1) {{ html += `<button onclick="goPage(1)">1</button>`; if(range[0]>2) html += `<button disabled>...</button>`; }}
  range.forEach(p => {{ html += `<button class="${{p===currentPage?'active':''}}" onclick="goPage(${{p}})">${{p}}</button>`; }});
  if(range[range.length-1] < pages) {{ if(range[range.length-1]<pages-1) html += `<button disabled>...</button>`; html += `<button onclick="goPage(${{pages}})">${{pages}}</button>`; }}
  
  html += `<button ${{currentPage===pages?'disabled':''}} onclick="goPage(${{currentPage+1}})">Next →</button>`;
  el.innerHTML = html;
}}

function goPage(p) {{ currentPage = p; renderResults(); window.scrollTo(0, 300); }}

function filterByDomain(d) {{
  document.getElementById('filter-domain').value = d;
  applyFilters();
  window.scrollTo(0, 0);
}}

function filterByTopic(t) {{
  document.getElementById('search').value = t;
  applyFilters();
  window.scrollTo(0, 0);
}}

function exportFiltered(fmt) {{
  const data = filtered.map(r => ({{
    repo_key: r.repo_key, name: r.name, owner: r.owner, description: r.description,
    url: r.url, stars: r.stars, forks: r.forks, projects: r.projects,
    topics: r.topics, last_updated: r.last_updated, freshness: r.freshness_status,
    popularity: r.popularity_tier, quality: r.quality_score, domain: r.domain_category
  }}));
  
  let blob, filename;
  if(fmt === 'json') {{
    blob = new Blob([JSON.stringify(data, null, 2)], {{type: 'application/json'}});
    filename = 'awesome_catalogue.json';
  }} else {{
    const headers = Object.keys(data[0] || {{}});
    const csv = [headers.join(','), ...data.map(r => headers.map(h => '"'+(r[h]+'').replace(/"/g,'""')+'"').join(','))].join('\\n');
    blob = new Blob([csv], {{type: 'text/csv'}});
    filename = 'awesome_catalogue.csv';
  }}
  
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}}

function copyToClipboard() {{
  const text = filtered.slice(0, 100).map(r => `${{r.name}} (${{r.owner}}) - ⭐${{r.stars}} - ${{r.url}}`).join('\\n');
  navigator.clipboard.writeText(text).then(() => alert('Copied top 100 to clipboard!'));
}}

function esc(s) {{ 
  const d = document.createElement('div'); d.textContent = s||''; return d.innerHTML; 
}}

function debounce(fn, ms) {{
  let t; return (...a) => {{ clearTimeout(t); t = setTimeout(() => fn(...a), ms); }};
}}

init();
</script>
</body>
</html>"""
    
    with open(output, "w") as f:
        f.write(html)
    
    print(f"Built HTML viewer: {output} ({len(html):,} bytes)")
    return output


if __name__ == "__main__":
    build_html()
