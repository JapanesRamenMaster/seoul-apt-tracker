"""
geocode.py 결과를 Leaflet.js HTML 지도로 변환.
산출물: map/index.html (JSON 임베딩, 서버 없이 브라우저에서 바로 열기 가능)
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAP_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "map", "index.html")


def parse_budget_diff(val: str) -> float:
    """'↑1.5억' → 1.5, '↓2.0억' → -2.0, '-' → 0"""
    if not val or val == "-":
        return 0.0
    m = re.match(r"([↑↓])([\d.]+)억", val)
    if not m:
        return 0.0
    sign = 1.0 if m.group(1) == "↑" else -1.0
    return sign * float(m.group(2))


def diff_color(diff: float) -> str:
    if diff <= -2.0:
        return "#16a34a"   # 짙은 초록: 예산보다 2억+ 저렴
    elif diff <= 0.0:
        return "#86efac"   # 연두: 예산 이하
    elif diff <= 1.0:
        return "#fbbf24"   # 노랑: 1억 이내 초과
    elif diff <= 3.0:
        return "#f97316"   # 주황: 1~3억 초과
    else:
        return "#ef4444"   # 빨강: 3억+ 초과


def build_html(complexes: list) -> str:
    # 지도에 올릴 단지 (좌표 있는 것만)
    markers = []
    for c in complexes:
        if not c.get("lat") or not c.get("lon"):
            continue
        diff = parse_budget_diff(c.get("budget_diff", ""))
        markers.append({
            "name": c["name"],
            "gu": c["gu"],
            "area": c["area"],
            "current": c["current_price"],
            "proj": c["proj_price"],
            "diff": c["budget_diff"],
            "diff_val": diff,
            "units": c["units"],
            "built": c["built"],
            "cagr": c["cagr"],
            "kapt": c["kapt_link"],
            "color": diff_color(diff),
            "lat": c["lat"],
            "lon": c["lon"],
        })

    total = len(complexes)
    mapped = len(markers)
    gu_list = sorted({c["gu"] for c in complexes if c.get("lat")})

    markers_json = json.dumps(markers, ensure_ascii=False)
    gu_options = "\n".join(f'<option value="{g}">{g}</option>' for g in gu_list)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>서울 아파트 지도 — 2028년 예산 범위</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, 'Apple SD Gothic Neo', sans-serif; background: #0f172a; color: #e2e8f0; height: 100vh; display: flex; flex-direction: column; }}
#header {{ background: #1e293b; padding: 12px 16px; border-bottom: 1px solid #334155; display: flex; align-items: center; gap: 16px; flex-shrink: 0; }}
#header h1 {{ font-size: 15px; font-weight: 700; color: #f1f5f9; }}
#header .subtitle {{ font-size: 12px; color: #94a3b8; }}
#main {{ flex: 1; display: flex; overflow: hidden; }}
#sidebar {{ width: 280px; background: #1e293b; border-right: 1px solid #334155; overflow-y: auto; padding: 12px; flex-shrink: 0; }}
#map {{ flex: 1; }}
.filter-section {{ margin-bottom: 14px; }}
.filter-label {{ font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 6px; }}
select {{ width: 100%; background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 6px 8px; border-radius: 6px; font-size: 13px; }}
.legend {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 10px 12px; margin-bottom: 14px; }}
.legend-row {{ display: flex; align-items: center; gap: 8px; font-size: 12px; margin-bottom: 5px; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }}
.stats {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 10px 12px; }}
.stat-row {{ display: flex; justify-content: space-between; font-size: 12px; padding: 3px 0; border-bottom: 1px solid #1e293b; }}
.stat-row:last-child {{ border-bottom: none; }}
.stat-val {{ color: #60a5fa; font-weight: 600; }}
#count-badge {{ background: #1e40af; color: #bfdbfe; font-size: 11px; padding: 2px 8px; border-radius: 9999px; margin-left: auto; }}
</style>
</head>
<body>
<div id="header">
  <h1>서울 아파트 — 2028년 예산 지도</h1>
  <div class="subtitle">예산 16억 기준 · 2028-02 예상가 12~20억 범위</div>
  <div id="count-badge">{mapped}/{total} 표시</div>
</div>
<div id="main">
  <div id="sidebar">
    <div class="filter-section">
      <div class="filter-label">구 필터</div>
      <select id="gu-filter">
        <option value="">전체</option>
        {gu_options}
      </select>
    </div>
    <div class="filter-section">
      <div class="filter-label">면적</div>
      <select id="area-filter">
        <option value="">전체</option>
        <option value="59㎡이하">59㎡ 이하</option>
        <option value="60~84㎡">60~84㎡</option>
        <option value="85~114㎡">85~114㎡</option>
        <option value="115㎡이상">115㎡ 이상</option>
      </select>
    </div>
    <div class="filter-section">
      <div class="filter-label">예산 대비</div>
      <select id="diff-filter">
        <option value="">전체</option>
        <option value="under">예산 이하 (↓)</option>
        <option value="over1">±1억 이내</option>
        <option value="over3">1~3억 초과</option>
        <option value="over3plus">3억+ 초과</option>
      </select>
    </div>
    <div class="legend">
      <div class="legend-row"><div class="legend-dot" style="background:#16a34a"></div> 2억+ 저렴</div>
      <div class="legend-row"><div class="legend-dot" style="background:#86efac"></div> 예산 이하</div>
      <div class="legend-row"><div class="legend-dot" style="background:#fbbf24"></div> 1억 이내 초과</div>
      <div class="legend-row"><div class="legend-dot" style="background:#f97316"></div> 1~3억 초과</div>
      <div class="legend-row"><div class="legend-dot" style="background:#ef4444"></div> 3억+ 초과</div>
    </div>
    <div class="stats" id="stats-box">
      <div class="stat-row"><span>표시 단지</span><span class="stat-val" id="s-total">{mapped}</span></div>
      <div class="stat-row"><span>예산 이하</span><span class="stat-val" id="s-under">-</span></div>
      <div class="stat-row"><span>±1억 이내</span><span class="stat-val" id="s-near">-</span></div>
      <div class="stat-row"><span>1억+ 초과</span><span class="stat-val" id="s-over">-</span></div>
    </div>
  </div>
  <div id="map"></div>
</div>
<script>
const DATA = {markers_json};

const map = L.map('map', {{ center: [37.5665, 126.978], zoom: 12 }});
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
}}).addTo(map);

let layerGroup = L.layerGroup().addTo(map);

function makeMarker(c) {{
  return L.circleMarker([c.lat, c.lon], {{
    radius: 7, fillColor: c.color, color: '#fff', weight: 1.5,
    opacity: 1, fillOpacity: 0.88
  }}).bindPopup(`
    <div style="font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;min-width:200px">
      <div style="font-weight:700;font-size:14px;margin-bottom:6px">${{c.name}}</div>
      <table style="font-size:12px;width:100%;border-collapse:collapse">
        <tr><td style="color:#666;padding:2px 0">구</td><td style="font-weight:600">${{c.gu}}</td></tr>
        <tr><td style="color:#666;padding:2px 0">면적</td><td>${{c.area}}</td></tr>
        <tr><td style="color:#666;padding:2px 0">현재가</td><td style="font-weight:600">${{c.current}}</td></tr>
        <tr><td style="color:#666;padding:2px 0">2028 예상</td><td style="font-weight:600">${{c.proj}}</td></tr>
        <tr><td style="color:#666;padding:2px 0">예산 대비</td><td style="font-weight:700;color:${{c.diff_val <= 0 ? '#16a34a' : '#ef4444'}}">${{c.diff}}</td></tr>
        <tr><td style="color:#666;padding:2px 0">세대수</td><td>${{c.units}}</td></tr>
        <tr><td style="color:#666;padding:2px 0">5년 CAGR</td><td>${{c.cagr}}</td></tr>
      </table>
      ${{c.kapt && c.kapt !== '-' ? `<a href="${{c.kapt}}" target="_blank" style="display:block;margin-top:8px;font-size:11px;color:#2563eb">K-APT 단지정보 →</a>` : ''}}
    </div>
  `);
}}

function filterAndRender() {{
  const guVal = document.getElementById('gu-filter').value;
  const areaVal = document.getElementById('area-filter').value;
  const diffVal = document.getElementById('diff-filter').value;

  layerGroup.clearLayers();
  let under = 0, near = 0, over = 0, shown = 0;

  DATA.forEach(c => {{
    if (guVal && c.gu !== guVal) return;
    if (areaVal && c.area !== areaVal) return;
    if (diffVal === 'under' && c.diff_val > 0) return;
    if (diffVal === 'over1' && Math.abs(c.diff_val) > 1) return;
    if (diffVal === 'over3' && (c.diff_val <= 1 || c.diff_val > 3)) return;
    if (diffVal === 'over3plus' && c.diff_val <= 3) return;

    makeMarker(c).addTo(layerGroup);
    shown++;
    if (c.diff_val <= 0) under++;
    else if (c.diff_val <= 1) near++;
    else over++;
  }});

  document.getElementById('s-total').textContent = shown;
  document.getElementById('s-under').textContent = under;
  document.getElementById('s-near').textContent = near;
  document.getElementById('s-over').textContent = over;
}}

document.getElementById('gu-filter').addEventListener('change', filterAndRender);
document.getElementById('area-filter').addEventListener('change', filterAndRender);
document.getElementById('diff-filter').addEventListener('change', filterAndRender);
filterAndRender();
</script>
</body>
</html>"""


if __name__ == "__main__":
    from scripts.geocode import geocode_all

    print("데이터 로딩 및 geocoding...")
    result = geocode_all()
    complexes = result["complexes"]

    os.makedirs(os.path.dirname(MAP_OUT), exist_ok=True)
    html = build_html(complexes)
    with open(MAP_OUT, "w", encoding="utf-8") as f:
        f.write(html)

    mapped = sum(1 for c in complexes if c.get("lat"))
    print(f"\nmap/index.html 생성 완료 ({mapped}/{len(complexes)}개 표시)")
    print(f"경로: {MAP_OUT}")
