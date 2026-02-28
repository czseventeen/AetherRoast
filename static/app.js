const profileSelect = document.getElementById('profileSelect');
const statusLine = document.getElementById('statusLine');

const stateVal = document.getElementById('stateVal');
const elapsedVal = document.getElementById('elapsedVal');
const stageVal = document.getElementById('stageVal');
const tempVal = document.getElementById('tempVal');
const targetVal = document.getElementById('targetVal');
const rorVal = document.getElementById('rorVal');

const ctx = document.getElementById('roastChart');
const stageEvents = [];
const seenEventKeys = new Set();
const chartData = {
  datasets: [
    { label: 'Temperature (C)', data: [], borderColor: '#c14f2a', yAxisID: 'yTemp', tension: 0.2, pointRadius: 0 },
    { label: 'RoR (C/min)', data: [], borderColor: '#1d6b5f', yAxisID: 'yRor', tension: 0.2, pointRadius: 0 }
  ]
};

const stageMarkerPlugin = {
  id: 'stageMarkerPlugin',
  afterDatasetsDraw(chart) {
    const { ctx: canvasCtx, chartArea, scales } = chart;
    const xScale = scales.x;
    if (!xScale || stageEvents.length === 0) {
      return;
    }

    canvasCtx.save();
    canvasCtx.strokeStyle = '#7f5539';
    canvasCtx.fillStyle = '#7f5539';
    canvasCtx.lineWidth = 1;
    canvasCtx.font = '11px Segoe UI';

    for (const evt of stageEvents) {
      const x = xScale.getPixelForValue(evt.t);
      if (x < chartArea.left || x > chartArea.right) {
        continue;
      }
      canvasCtx.beginPath();
      canvasCtx.moveTo(x, chartArea.top);
      canvasCtx.lineTo(x, chartArea.bottom);
      canvasCtx.stroke();

      canvasCtx.save();
      canvasCtx.translate(x + 3, chartArea.top + 8);
      canvasCtx.rotate(-Math.PI / 2);
      canvasCtx.fillText(`${evt.label} (${evt.deltaLabel})`, 0, 0);
      canvasCtx.restore();
    }
    canvasCtx.restore();
  }
};

const roastChart = new Chart(ctx, {
  type: 'line',
  data: chartData,
  plugins: [stageMarkerPlugin],
  options: {
    responsive: true,
    animation: false,
    scales: {
      x: { type: 'linear', title: { display: true, text: 'Elapsed (s)' } },
      yTemp: { type: 'linear', position: 'left', title: { display: true, text: 'Temp C' } },
      yRor: { type: 'linear', position: 'right', title: { display: true, text: 'RoR C/min' }, grid: { drawOnChartArea: false } }
    }
  }
});

function formatElapsed(seconds) {
  const whole = Math.floor(seconds || 0);
  const ms = Math.floor(((seconds || 0) % 1) * 1000);
  const m = Math.floor(whole / 60);
  const s = whole % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
}

function setStatus(text, isError = false) {
  statusLine.textContent = text;
  statusLine.style.color = isError ? '#a43f2e' : '#2b2419';
}

async function api(path, method = 'GET', body = null) {
  const resp = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : null
  });
  if (!resp.ok) {
    const payload = await resp.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${resp.status}`);
  }
  return resp.json().catch(() => ({}));
}

async function loadProfiles() {
  const profiles = await api('/api/profiles');
  profileSelect.innerHTML = '';
  for (const p of profiles) {
    const opt = document.createElement('option');
    opt.value = p.file;
    opt.textContent = `${p.name} (${p.file})`;
    profileSelect.appendChild(opt);
  }
}

function pushChartPoint(snapshot) {
  const t = Number(snapshot.elapsed_s || 0);
  const temp = Number(snapshot.actual_temp_c || 0);
  const ror = snapshot.ror_c_per_min == null ? null : Number(snapshot.ror_c_per_min);

  chartData.datasets[0].data.push({ x: t, y: temp });
  chartData.datasets[1].data.push({ x: t, y: ror });

  if (chartData.datasets[0].data.length > 4000) {
    chartData.datasets[0].data.shift();
    chartData.datasets[1].data.shift();
  }
}

function stageKeyToLabel(key) {
  const labels = {
    bean_drop: 'Bean Drop',
    dry_end: 'Dry End',
    maillard: 'Maillard',
    first_crack_start: '1C Start',
    first_crack_end: '1C End',
    second_crack_start: '2C Start',
    second_crack_end: '2C End',
    drop: 'Drop'
  };
  return labels[key] || key;
}

function registerStageEvent(marker, elapsedSeconds) {
  if (!marker || elapsedSeconds == null) {
    return;
  }
  const t = Number(elapsedSeconds);
  const key = `${marker}@${t.toFixed(2)}`;
  if (seenEventKeys.has(key)) {
    return;
  }
  seenEventKeys.add(key);
  const prev = stageEvents.length ? stageEvents[stageEvents.length - 1].t : null;
  const delta = prev == null ? t : (t - prev);
  stageEvents.push({
    t,
    label: stageKeyToLabel(marker),
    deltaLabel: formatElapsed(delta)
  });
}

function updateSnapshot(snapshot) {
  stateVal.textContent = snapshot.state;
  elapsedVal.textContent = formatElapsed(snapshot.elapsed_s);
  stageVal.textContent = snapshot.stage_label;
  tempVal.textContent = Number(snapshot.actual_temp_c || 0).toFixed(2);
  targetVal.textContent = Number(snapshot.target_temp_c || 0).toFixed(2);
  rorVal.textContent = snapshot.ror_c_per_min == null ? 'n/a' : Number(snapshot.ror_c_per_min).toFixed(2);

  if (snapshot.last_event_marker && snapshot.last_event_elapsed_s != null) {
    registerStageEvent(snapshot.last_event_marker, snapshot.last_event_elapsed_s);
  }

  if (snapshot.state === 'ROASTING' || snapshot.state === 'PREHEATING' || snapshot.state === 'READY_FOR_BEAN_DROP') {
    pushChartPoint(snapshot);
  }
  roastChart.update('none');
}

function wireButtons() {
  document.getElementById('refreshProfiles').addEventListener('click', async () => {
    try {
      await loadProfiles();
      setStatus('Profiles refreshed');
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  document.getElementById('startBtn').addEventListener('click', async () => {
    try {
      chartData.datasets[0].data = [];
      chartData.datasets[1].data = [];
      stageEvents.length = 0;
      seenEventKeys.clear();
      roastChart.update('none');
      const profile_file = profileSelect.value;
      const res = await api('/api/session/start', 'POST', { profile_file });
      setStatus(res.message);
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  document.getElementById('beanDropBtn').addEventListener('click', async () => {
    try {
      const res = await api('/api/session/bean-drop', 'POST');
      setStatus(res.message);
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  document.getElementById('stopBtn').addEventListener('click', async () => {
    try {
      const res = await api('/api/session/stop', 'POST');
      setStatus(res.message);
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  document.getElementById('emergencyStopBtn').addEventListener('click', async () => {
    try {
      const res = await api('/api/session/emergency-stop', 'POST');
      setStatus(res.message, !res.ok);
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  document.getElementById('downloadCsvBtn').addEventListener('click', () => {
    window.location.href = '/api/session/csv';
  });

  document.querySelectorAll('button[data-stage]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        const res = await api('/api/session/mark-stage', 'POST', { stage: btn.dataset.stage });
        setStatus(res.message);
      } catch (err) {
        setStatus(err.message, true);
      }
    });
  });

  document.querySelectorAll('button[data-fan]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        const res = await api('/api/session/fan', 'POST', { percent: Number(btn.dataset.fan) });
        setStatus(res.message);
      } catch (err) {
        setStatus(err.message, true);
      }
    });
  });

  document.querySelectorAll('button[data-delta]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        const res = await api('/api/session/temp-offset', 'POST', { delta_c: Number(btn.dataset.delta) });
        setStatus(res.message);
      } catch (err) {
        setStatus(err.message, true);
      }
    });
  });
}

function connectWs() {
  const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${wsProto}//${location.host}/ws/session`);

  ws.onopen = () => setStatus('Live telemetry connected');
  ws.onmessage = (event) => {
    try {
      updateSnapshot(JSON.parse(event.data));
    } catch (_) {
      // ignore malformed payloads
    }
  };
  ws.onclose = () => {
    setStatus('Telemetry disconnected, retrying...', true);
    setTimeout(connectWs, 1500);
  };
}

(async function bootstrap() {
  wireButtons();
  try {
    await loadProfiles();
    const snapshot = await api('/api/session');
    updateSnapshot(snapshot);
  } catch (err) {
    setStatus(err.message, true);
  }
  connectWs();
})();
