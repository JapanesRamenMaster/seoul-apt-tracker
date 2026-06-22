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
DOCS_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "index.html")


def parse_budget_diff(val: str) -> float:
    if not val or val == "-":
        return 0.0
    m = re.match(r"([↑↓])([\d.]+)억", val)
    if not m:
        return 0.0
    return float(m.group(2)) * (1.0 if m.group(1) == "↑" else -1.0)


def parse_units(val: str) -> int:
    v = val.replace(",", "").strip()
    try:
        return int(v)
    except Exception:
        return 0


def diff_color(diff: float) -> str:
    if diff <= -2.0:
        return "#16a34a"
    elif diff <= 0.0:
        return "#86efac"
    elif diff <= 1.0:
        return "#fbbf24"
    elif diff <= 3.0:
        return "#f97316"
    else:
        return "#ef4444"


def build_html(complexes: list) -> str:
    markers = []
    for c in complexes:
        if not c.get("lat") or not c.get("lon"):
            continue
        diff = parse_budget_diff(c.get("budget_diff", ""))
        units_val = parse_units(c.get("units", ""))
        markers.append({
            "name": c["name"],
            "gu": c["gu"],
            "area": c["area"],
            "current": c["current_price"],
            "proj": c["proj_price"],
            "diff": c["budget_diff"],
            "diff_val": diff,
            "units": c["units"],
            "units_val": units_val,
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

    gu_checkboxes = "\n".join(
        f'<label class="cb-item"><input type="checkbox" name="gu" value="{g}"><span>{g}</span></label>'
        for g in gu_list
    )

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
#header {{ background: #1e293b; padding: 10px 16px; border-bottom: 1px solid #334155; display: flex; align-items: center; gap: 12px; flex-shrink: 0; }}
#header h1 {{ font-size: 14px; font-weight: 700; color: #f1f5f9; }}
#header .subtitle {{ font-size: 11px; color: #94a3b8; }}
#count-badge {{ background: #1e40af; color: #bfdbfe; font-size: 11px; padding: 2px 8px; border-radius: 9999px; margin-left: auto; white-space: nowrap; }}
#main {{ flex: 1; display: flex; overflow: hidden; }}
#sidebar {{ width: 260px; background: #1e293b; border-right: 1px solid #334155; overflow-y: auto; padding: 10px; flex-shrink: 0; display: flex; flex-direction: column; gap: 10px; }}
#map {{ flex: 1; }}

/* 필터 섹션 */
.filter-section {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; overflow: hidden; }}
.filter-header {{ display: flex; align-items: center; justify-content: space-between; padding: 7px 10px; cursor: pointer; user-select: none; }}
.filter-header .label {{ font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: .5px; }}
.filter-header .badge {{ font-size: 10px; background: #1e40af; color: #bfdbfe; padding: 1px 6px; border-radius: 9999px; display: none; }}
.filter-header .badge.active {{ display: inline; }}
.filter-header .arrow {{ font-size: 10px; color: #475569; transition: transform .2s; }}
.filter-header.open .arrow {{ transform: rotate(180deg); }}
.filter-body {{ padding: 6px 10px 8px; border-top: 1px solid #1e293b; }}
.filter-body.collapsed {{ display: none; }}

/* 구 체크박스 목록 */
.gu-list {{ max-height: 160px; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; }}
.gu-list .cb-item {{ display: flex; align-items: center; gap: 6px; padding: 3px 2px; font-size: 12px; cursor: pointer; border-radius: 4px; }}
.gu-list .cb-item:hover {{ background: #1e293b; }}
.gu-list .cb-item input {{ accent-color: #60a5fa; width: 13px; height: 13px; flex-shrink: 0; cursor: pointer; }}
.gu-list .cb-item span {{ color: #cbd5e1; }}
.gu-list .cb-item input:checked + span {{ color: #f1f5f9; font-weight: 600; }}
.select-all {{ font-size: 11px; color: #60a5fa; cursor: pointer; margin-bottom: 5px; }}
.select-all:hover {{ text-decoration: underline; }}

/* Pill 체크박스 */
.pill-group {{ display: flex; flex-wrap: wrap; gap: 5px; }}
.pill-group label {{ cursor: pointer; }}
.pill-group input {{ display: none; }}
.pill-group span {{
  display: inline-block; padding: 3px 9px; border-radius: 9999px;
  font-size: 11px; border: 1px solid #334155; color: #94a3b8;
  transition: all .15s;
}}
.pill-group input:checked + span {{ background: #1e40af; border-color: #3b82f6; color: #bfdbfe; }}
.pill-group span:hover {{ border-color: #64748b; color: #cbd5e1; }}

/* 범례 */
.legend {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 8px 10px; }}
.legend-row {{ display: flex; align-items: center; gap: 7px; font-size: 11px; color: #94a3b8; margin-bottom: 4px; }}
.legend-row:last-child {{ margin-bottom: 0; }}
.legend-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}

/* 통계 */
.stats {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 8px 10px; }}
.stat-row {{ display: flex; justify-content: space-between; font-size: 11px; padding: 2px 0; border-bottom: 1px solid #1e293b; }}
.stat-row:last-child {{ border-bottom: none; }}
.stat-val {{ color: #60a5fa; font-weight: 600; }}
</style>
</head>
<body>
<div id="header">
  <h1>서울 아파트 — 2028년 예산 지도</h1>
  <div class="subtitle">예산 16억 기준 · 2028-02 예상가 12~20억</div>
  <div id="count-badge">{mapped}/{total} 단지</div>
</div>
<div id="main">
  <div id="sidebar">

    <!-- 구 필터 -->
    <div class="filter-section">
      <div class="filter-header open" onclick="toggleSection(this)">
        <span class="label">구</span>
        <span class="badge" id="badge-gu"></span>
        <span class="arrow">▼</span>
      </div>
      <div class="filter-body">
        <div class="select-all" onclick="toggleAll('gu')">전체 선택/해제</div>
        <div class="gu-list">
          {gu_checkboxes}
        </div>
      </div>
    </div>

    <!-- 면적 필터 -->
    <div class="filter-section">
      <div class="filter-header open" onclick="toggleSection(this)">
        <span class="label">면적</span>
        <span class="badge" id="badge-area"></span>
        <span class="arrow">▼</span>
      </div>
      <div class="filter-body">
        <div class="pill-group">
          <label><input type="checkbox" name="area" value="59㎡이하"><span>59㎡ 이하</span></label>
          <label><input type="checkbox" name="area" value="60~84㎡"><span>60~84㎡</span></label>
          <label><input type="checkbox" name="area" value="85~114㎡"><span>85~114㎡</span></label>
          <label><input type="checkbox" name="area" value="115㎡이상"><span>115㎡ 이상</span></label>
        </div>
      </div>
    </div>

    <!-- 세대수 필터 -->
    <div class="filter-section">
      <div class="filter-header open" onclick="toggleSection(this)">
        <span class="label">세대수</span>
        <span class="badge" id="badge-units"></span>
        <span class="arrow">▼</span>
      </div>
      <div class="filter-body">
        <div class="pill-group">
          <label><input type="checkbox" name="units" value="~300"><span>~300세대</span></label>
          <label><input type="checkbox" name="units" value="300~500"><span>300~500</span></label>
          <label><input type="checkbox" name="units" value="500~1000"><span>500~1000</span></label>
          <label><input type="checkbox" name="units" value="1000~2000"><span>1000~2000</span></label>
          <label><input type="checkbox" name="units" value="2000~"><span>2000+</span></label>
        </div>
      </div>
    </div>

    <!-- 예산 대비 필터 -->
    <div class="filter-section">
      <div class="filter-header open" onclick="toggleSection(this)">
        <span class="label">예산 대비</span>
        <span class="badge" id="badge-diff"></span>
        <span class="arrow">▼</span>
      </div>
      <div class="filter-body">
        <div class="pill-group">
          <label><input type="checkbox" name="diff" value="under2"><span>2억+ 저렴</span></label>
          <label><input type="checkbox" name="diff" value="under0"><span>예산 이하</span></label>
          <label><input type="checkbox" name="diff" value="over1"><span>1억 이내 초과</span></label>
          <label><input type="checkbox" name="diff" value="over3"><span>1~3억 초과</span></label>
          <label><input type="checkbox" name="diff" value="over3plus"><span>3억+ 초과</span></label>
        </div>
      </div>
    </div>

    <!-- 범례 -->
    <div class="legend">
      <div class="legend-row"><div class="legend-dot" style="background:#16a34a"></div> 2억+ 저렴</div>
      <div class="legend-row"><div class="legend-dot" style="background:#86efac"></div> 예산 이하</div>
      <div class="legend-row"><div class="legend-dot" style="background:#fbbf24"></div> 1억 이내 초과</div>
      <div class="legend-row"><div class="legend-dot" style="background:#f97316"></div> 1~3억 초과</div>
      <div class="legend-row"><div class="legend-dot" style="background:#ef4444"></div> 3억+ 초과</div>
    </div>

    <!-- 통계 -->
    <div class="stats">
      <div class="stat-row"><span>표시</span><span class="stat-val" id="s-total">-</span></div>
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
        <tr><td style="color:#666;padding:2px 0;width:60px">구</td><td style="font-weight:600">${{c.gu}}</td></tr>
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

function getChecked(name) {{
  return new Set([...document.querySelectorAll(`input[name="${{name}}"]:checked`)].map(b => b.value));
}}

function unitsInBucket(uval, bucket) {{
  if (bucket === '~300')      return uval < 300;
  if (bucket === '300~500')   return uval >= 300 && uval < 500;
  if (bucket === '500~1000')  return uval >= 500 && uval < 1000;
  if (bucket === '1000~2000') return uval >= 1000 && uval < 2000;
  if (bucket === '2000~')     return uval >= 2000;
  return false;
}}

function diffInBucket(dval, bucket) {{
  if (bucket === 'under2')    return dval <= -2;
  if (bucket === 'under0')    return dval > -2 && dval <= 0;
  if (bucket === 'over1')     return dval > 0 && dval <= 1;
  if (bucket === 'over3')     return dval > 1 && dval <= 3;
  if (bucket === 'over3plus') return dval > 3;
  return false;
}}

function updateBadge(name) {{
  const checked = getChecked(name);
  const badge = document.getElementById('badge-' + name);
  if (badge) {{
    badge.textContent = checked.size > 0 ? checked.size : '';
    badge.classList.toggle('active', checked.size > 0);
  }}
}}

function filterAndRender() {{
  const guSet    = getChecked('gu');
  const areaSet  = getChecked('area');
  const unitsSet = getChecked('units');
  const diffSet  = getChecked('diff');

  ['gu','area','units','diff'].forEach(updateBadge);

  layerGroup.clearLayers();
  let under = 0, near = 0, over = 0, shown = 0;

  DATA.forEach(c => {{
    if (guSet.size    > 0 && !guSet.has(c.gu)) return;
    if (areaSet.size  > 0 && !areaSet.has(c.area)) return;
    if (unitsSet.size > 0 && ![...unitsSet].some(b => unitsInBucket(c.units_val, b))) return;
    if (diffSet.size  > 0 && ![...diffSet].some(b => diffInBucket(c.diff_val, b))) return;

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
  document.getElementById('count-badge').textContent = shown + '/{total} 단지';
}}

function toggleSection(header) {{
  header.classList.toggle('open');
  const body = header.nextElementSibling;
  body.classList.toggle('collapsed');
}}

function toggleAll(name) {{
  const boxes = document.querySelectorAll(`input[name="${{name}}"]`);
  const allChecked = [...boxes].every(b => b.checked);
  boxes.forEach(b => b.checked = !allChecked);
  filterAndRender();
}}

document.querySelectorAll('input[type="checkbox"]').forEach(cb => {{
  cb.addEventListener('change', filterAndRender);
}});

filterAndRender();
</script>
</body>
</html>"""


if __name__ == "__main__":
    from scripts.geocode import geocode_all

    print("데이터 로딩 및 geocoding...")
    result = geocode_all()
    complexes = result["complexes"]

    html = build_html(complexes)
    for out_path in [MAP_OUT, DOCS_OUT]:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

    mapped = sum(1 for c in complexes if c.get("lat"))
    print(f"\nmap/index.html + docs/index.html 생성 완료 ({mapped}/{len(complexes)}개 표시)")
