"""System monitoring and metrics dashboard."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from integrations.supabase_client import query

router = APIRouter(prefix="/monitor", tags=["monitoring"])


@router.get("/stats")
def stats():
    leads     = query("leads", limit=1000)
    customers = query("customers", {"is_active": True}, limit=500)
    affiliates = query("affiliates", {"is_active": True}, limit=200)
    orders    = query("orders", {"status": "paid"}, limit=500)
    alerts    = query("alerts", limit=50)

    revenue = sum(float(o.get("amount_aud", 0)) for o in orders)
    lead_tiers = {"basic": 0, "standard": 0, "premium": 0}
    for l in leads:
        lead_tiers[l.get("tier", "basic")] = lead_tiers.get(l.get("tier", "basic"), 0) + 1

    return {
        "leads": {
            "total":    len(leads),
            "by_tier":  lead_tiers,
            "avg_score": round(sum(float(l.get("intent_score", 0)) for l in leads) / max(len(leads), 1), 2),
        },
        "customers":   {"active": len(customers)},
        "affiliates":  {"active": len(affiliates)},
        "revenue_aud": round(revenue, 2),
        "recent_alerts": alerts[:10],
    }


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FractalMesh Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0d1117; color: #e6edf3; padding: 24px; }
  h1 { font-size: 1.5rem; margin-bottom: 24px; color: #58a6ff; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
  .card h3 { font-size: 0.75rem; text-transform: uppercase; color: #8b949e; margin-bottom: 8px; }
  .card .value { font-size: 2rem; font-weight: 700; color: #58a6ff; }
  .card .sub { font-size: 0.8rem; color: #8b949e; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; background: #161b22;
          border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }
  th { background: #21262d; padding: 10px 16px; text-align: left; font-size: 0.75rem;
       text-transform: uppercase; color: #8b949e; }
  td { padding: 10px 16px; border-top: 1px solid #21262d; font-size: 0.85rem; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; }
  .premium { background: #1f6feb33; color: #58a6ff; }
  .standard { background: #388bfd33; color: #79c0ff; }
  .basic { background: #30363d; color: #8b949e; }
  .info { color: #3fb950; } .warn { color: #d29922; } .error { color: #f85149; }
</style>
</head>
<body>
<h1>⚡ FractalMesh Intelligence Dashboard</h1>
<div class="grid" id="stats"></div>
<h2 style="margin-bottom:16px;font-size:1rem;color:#8b949e">Recent Leads</h2>
<table id="leads-table">
  <thead><tr><th>Title</th><th>Score</th><th>Tier</th><th>Source</th></tr></thead>
  <tbody id="leads-body"></tbody>
</table>
<script>
async function load() {
  const s = await fetch('/monitor/stats').then(r=>r.json());
  const l = await fetch('/leads').then(r=>r.json());
  document.getElementById('stats').innerHTML = [
    ['Total Leads', s.leads.total, `Avg score: ${s.leads.avg_score}`],
    ['Premium Leads', s.leads.by_tier.premium, 'High-value'],
    ['Active Customers', s.customers.active, 'Subscribers'],
    ['Active Affiliates', s.affiliates.active, 'Partners'],
    ['Revenue AUD', '$' + s.revenue_aud.toFixed(2), 'Total paid'],
  ].map(([h,v,sub]) =>
    `<div class="card"><h3>${h}</h3><div class="value">${v}</div><div class="sub">${sub}</div></div>`
  ).join('');
  const rows = (l.data||[]).slice(0,20).map(r =>
    `<tr><td><a href="${r.url||'#'}" target="_blank" style="color:#58a6ff;text-decoration:none">${r.title||''}</a></td>
     <td>${(r.intent_score||0).toFixed(1)}</td>
     <td><span class="badge ${r.tier||'basic'}">${r.tier||'basic'}</span></td>
     <td style="color:#8b949e;font-size:0.75rem">${(r.source_feed||'').replace('https://','').split('/')[0]}</td></tr>`
  ).join('');
  document.getElementById('leads-body').innerHTML = rows || '<tr><td colspan="4" style="color:#8b949e">No leads yet</td></tr>';
}
load(); setInterval(load, 30000);
</script>
</body>
</html>"""
