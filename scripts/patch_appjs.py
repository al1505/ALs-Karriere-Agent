import sys

APP_JS = '/home/al/projects/ALs-Haribo-Dashboard/public/app.js'

with open(APP_JS, 'r', encoding='utf-8') as f:
    js = f.read()

orig_len = len(js)
patches_ok = 0

def patch(name, old, new):
    global js, patches_ok
    if old in js:
        js = js.replace(old, new, 1)
        print(f'{name} OK')
        patches_ok += 1
    else:
        print(f'{name} MISS — target not found')

# PATCH 1: statusColors — add dashboard + paused
patch('P1-statusColors',
    "      hybrid: 'bg-violet-900 text-violet-300',\n      interactive: 'bg-blue-900 text-blue-300',\n    };",
    "      hybrid: 'bg-violet-900 text-violet-300',\n      interactive: 'bg-blue-900 text-blue-300',\n      dashboard: 'bg-emerald-900 text-emerald-300',\n      paused: 'bg-yellow-900 text-yellow-300',\n    };"
)

# PATCH 2: statusLabels — add dashboard + paused
patch('P2-statusLabels',
    "      hybrid: 'Hybrid-Bewerbung', interactive: 'Interaktive Bewerbung',\n    };",
    "      hybrid: 'Hybrid-Bewerbung', interactive: 'Interaktive Bewerbung',\n      dashboard: 'Dashboard aktiv', paused: 'Pausiert',\n    };"
)

# PATCH 3a: barColors
patch('P3a-barColors',
    "      hybrid:'#7c3aed', interactive:'#2563eb'\n    };",
    "      hybrid:'#7c3aed', interactive:'#2563eb',\n      dashboard:'#059669', paused:'#ca8a04'\n    };"
)

# PATCH 3b: barLabels
patch('P3b-barLabels',
    "      hybrid:'Hybrid-Bewerbung', interactive:'Interaktive Bewerbung'\n    };",
    "      hybrid:'Hybrid-Bewerbung', interactive:'Interaktive Bewerbung',\n      dashboard:'Dashboard aktiv', paused:'Pausiert'\n    };"
)

# PATCH 4: counts init
patch('P4-counts',
    "    var counts = {pending:0, sent:0, in_interview:0, in_vormerkung:0, absage:0, cancelled:0, hybrid:0, interactive:0};",
    "    var counts = {pending:0, sent:0, in_interview:0, in_vormerkung:0, absage:0, cancelled:0, hybrid:0, interactive:0, dashboard:0, paused:0};"
)

# PATCH 5: offen filter
patch('P5-offen-filter',
    "      apps = apps.filter(function(a) { return ['pending','sent','in_interview','in_vormerkung','hybrid','interactive'].indexOf(a.status) !== -1; });",
    "      apps = apps.filter(function(a) { return ['pending','sent','in_interview','in_vormerkung','hybrid','interactive','dashboard','paused'].indexOf(a.status) !== -1; });"
)

# PATCH 6: modal button — add Dashboard-Chat option
OLD6 = '''              <button data-mode="interactive" class="px-4 py-3 rounded-lg bg-slate-700 hover:bg-slate-600 text-white text-sm text-left">
                <div class="font-semibold"><span class="material-symbols-outlined icon-sm">smart_toy</span> Interaktiv</div>
                <div class="text-xs text-slate-400 mt-0.5">Briefing + Ordner vorbereiten, du startest danach selbst</div>
              </button>'''
NEW6 = OLD6 + '''
              <button data-mode="dashboard" class="px-4 py-3 rounded-lg bg-emerald-900 hover:bg-emerald-800 text-white text-sm text-left">
                <div class="font-semibold"><span class="material-symbols-outlined icon-sm">chat</span> Dashboard-Chat (NEU)</div>
                <div class="text-xs text-emerald-300 mt-0.5">Vollautomatisch mit Live-Chat &#8212; Fortschritt hier im Dashboard verfolgen</div>
              </button>'''
patch('P6-modal-btn', OLD6, NEW6)

# PATCH 7: handle dashboard mode in modal resolver
patch('P7-mode-handler',
    "      if (mode) doJobAction(jobId, 'bewerben', {mode});",
    "      if (mode === 'dashboard') {\n        startDashboardSession(jobId);\n      } else if (mode) {\n        doJobAction(jobId, 'bewerben', {mode});\n      }"
)

# PATCH 8: inject startDashboardSession function before submitAbsage
INJECT_FN = '''  async function startDashboardSession(jobId) {
    try {
      const resp = await fetch('http://192.168.15.30:7601/api/session/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({application_id: jobId})
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      const url = 'http://192.168.15.30:7601/detail.html?app=' + jobId + '&session=' + data.session_id;
      window.open(url, '_blank');
      if (typeof loadBewerbungen === 'function') setTimeout(() => loadBewerbungen(''), 1500);
    } catch(e) {
      showToast('Fehler beim Starten der Dashboard-Session: ' + e.message, 'error');
    }
  }

  async function submitAbsage() {'''
patch('P8-startDashboardSession',
    "  async function submitAbsage() {",
    INJECT_FN
)

# PATCH 9: "In Bearbeitung" section before status-bar
OLD9 = "    // Status-Verteilung (aus ALLEN gecachten Apps, nicht nur gefilterten)"
NEW9 = '''    // "In Bearbeitung" section — dashboard + paused apps shown at top
    var activeAgentApps = apps.filter(function(a) { return a.status === 'dashboard' || a.status === 'paused'; });
    var inBearbeitungHtml = '';
    if (activeAgentApps.length) {
      var activeRows = activeAgentApps.map(function(a) {
        var isActive = a.status === 'dashboard';
        var dot = isActive
          ? '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#34d399;margin-right:4px;animation:pulse-ring 2s infinite"></span>'
          : '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#fbbf24;margin-right:4px"></span>';
        var label = isActive ? 'Aktiv' : 'Pausiert';
        var pct = a.progress_pct || 0;
        var chatUrl = 'http://192.168.15.30:7601/detail.html?app=' + a.id;
        return '<div class="flex items-center justify-between py-2 px-1 border-b border-slate-700/30 last:border-0">'
          + '<div class="flex items-center gap-2 min-w-0">' + dot
          + '<span class="text-xs font-medium text-slate-200 truncate">' + escHtml(a.company || a.title || '#' + a.id) + '</span>'
          + '<span class="text-xs text-slate-500 truncate ml-1">' + escHtml(a.title || '') + '</span>'
          + '</div>'
          + '<div class="flex items-center gap-2 shrink-0 ml-2">'
          + (pct ? '<div style="width:48px;height:5px;background:#1e293b;border-radius:9999px;overflow:hidden"><div style="width:' + pct + '%;height:100%;background:#34d399;border-radius:9999px"></div></div>' : '')
          + '<span class="px-1.5 py-0.5 rounded text-xs ' + (isActive ? 'bg-emerald-900 text-emerald-300' : 'bg-yellow-900 text-yellow-300') + '">' + label + '</span>'
          + '<a href="' + chatUrl + '" target="_blank" class="px-1.5 py-0.5 rounded text-xs bg-slate-700 hover:bg-emerald-700 text-slate-300 hover:text-white" title="Dashboard-Chat öffnen" onclick="event.stopPropagation()"><span class="material-symbols-outlined" style="font-size:13px;vertical-align:-2px">chat</span></a>'
          + '</div></div>';
      }).join('');
      inBearbeitungHtml = '<div class="mb-4 bg-slate-800 border border-emerald-800/50 rounded-xl p-4">'
        + '<div class="text-xs text-emerald-400 uppercase tracking-widest mb-2"><span class="material-symbols-outlined" style="font-size:13px;vertical-align:-2px">play_circle</span> In Bearbeitung (' + activeAgentApps.length + ')</div>'
        + activeRows + '</div>';
    }

    // Status-Verteilung (aus ALLEN gecachten Apps, nicht nur gefilterten)'''
patch('P9-inBearbeitung', OLD9, NEW9)

# PATCH 10: include inBearbeitungHtml in rendered output
# barHtml is assembled and combined with rows — we need to prepend inBearbeitungHtml
# Find the container.innerHTML assignment and prepend
OLD10 = "    container.innerHTML = barHtml + `"
NEW10 = "    container.innerHTML = inBearbeitungHtml + barHtml + `"
if OLD10 in js:
    js = js.replace(OLD10, NEW10, 1)
    print('P10-inject OK')
    patches_ok += 1
else:
    print('P10-inject MISS — searching alternate...')
    # Maybe the var barHtml ends with `;` and container.innerHTML is elsewhere
    idx = js.find('container.innerHTML = `\n      <div class="overflow-x-auto bg-slate-800 rounded-xl border border-slate-700">')
    if idx != -1:
        js = js[:idx] + 'container.innerHTML = inBearbeitungHtml + `\n      <div class="overflow-x-auto bg-slate-800 rounded-xl border border-slate-700">' + js[idx + len('container.innerHTML = `\n      <div class="overflow-x-auto bg-slate-800 rounded-xl border border-slate-700">'):]
        print('P10-inject OK (alt)')
        patches_ok += 1
    else:
        print('P10-inject MISS — could not find container.innerHTML assignment')

print(f'\nTotal: {patches_ok} patches applied. Length: {orig_len} -> {len(js)}')

with open(APP_JS, 'w', encoding='utf-8') as f:
    f.write(js)
print('Saved.')
