const profileSelect = document.getElementById('profileSelect');
const profileEditor = document.getElementById('profileEditor');
const profileModal = document.getElementById('profileModal');
const profileModalTitle = document.getElementById('profileModalTitle');
const closeProfileModalBtn = document.getElementById('closeProfileModalBtn');
const editProfileBtn = document.getElementById('editProfileBtn');
const saveProfileBtn = document.getElementById('saveProfileBtn');
const saveAsNameInput = document.getElementById('saveAsNameInput');
const saveAsProfileBtn = document.getElementById('saveAsProfileBtn');
const statusLine = document.getElementById('statusLine');

const stateVal = document.getElementById('stateVal');
const elapsedVal = document.getElementById('elapsedVal');
const stageVal = document.getElementById('stageVal');
const stageElapsedVal = document.getElementById('stageElapsedVal');
const tempVal = document.getElementById('tempVal');
const targetVal = document.getElementById('targetVal');
const rorVal = document.getElementById('rorVal');

const ctx = document.getElementById('roastChart');
const stageEvents = [];
const seenEventKeys = new Set();
const UI_UPDATE_INTERVAL_MS = 1000;
let lastUiUpdateMs = 0;
let profileModalFile = '';
let beanDropElapsed = null;
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
  const whole = Math.floor(Number(seconds) || 0);
  const minutes = Math.floor(whole / 60);
  const secs = whole % 60;
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function setStatus(text, isError = false) {
  statusLine.textContent = text;
  statusLine.style.color = isError ? '#a43f2e' : '#2b2419';
}

function updateChartXAxisTitle() {
  roastChart.options.scales.x.title.text = beanDropElapsed == null ? 'Elapsed (s)' : 'Time from Bean Drop (s)';
}

function toChartTime(elapsedSeconds) {
  const t = Number(elapsedSeconds || 0);
  return beanDropElapsed == null ? t : (t - beanDropElapsed);
}

function setBeanDropOrigin(elapsedSeconds) {
  const origin = Number(elapsedSeconds);
  if (!Number.isFinite(origin) || beanDropElapsed != null) {
    return;
  }
  beanDropElapsed = origin;
  chartData.datasets.forEach((dataset) => {
    dataset.data = dataset.data.map((point) => ({ x: point.x - origin, y: point.y }));
  });
  stageEvents.forEach((evt) => {
    evt.t -= origin;
  });
  updateChartXAxisTitle();
}

function saveGraphSnapshot() {
  const nowIso = new Date().toISOString().replace(/[:.]/g, '-');
  const profileName = (profileSelect.value || 'profile')
    .replace(/\.json$/i, '')
    .replace(/[^a-z0-9_-]+/gi, '_')
    .replace(/^_+|_+$/g, '') || 'profile';
  const filename = `${profileName}-${nowIso}-graph.png`;

  roastChart.update('none');
  const link = document.createElement('a');
  link.href = roastChart.toBase64Image('image/png', 1);
  link.download = filename;
  link.click();
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
  const selectedBeforeRefresh = profileSelect.value;
  const profiles = await api('/api/profiles');
  profileSelect.innerHTML = '';
  let restoredSelection = false;
  for (const p of profiles) {
    const opt = document.createElement('option');
    opt.value = p.file;
    opt.textContent = `${p.name} (${p.file})`;
    if (p.file === selectedBeforeRefresh) {
      opt.selected = true;
      restoredSelection = true;
    }
    profileSelect.appendChild(opt);
  }
  if (!restoredSelection && profileSelect.options.length > 0) {
    profileSelect.selectedIndex = 0;
  }
}

async function previewSelectedProfile() {
  const profileFile = profileSelect.value;
  if (!profileFile) {
    profileEditor.value = '';
    throw new Error('No profile selected');
  }
  const payload = await api(`/api/profiles/${encodeURIComponent(profileFile)}`);
  profileEditor.value = payload.content || '';
  return payload.file || profileFile;
}

function setProfileEditMode(editEnabled) {
  profileEditor.readOnly = !editEnabled;
  saveProfileBtn.disabled = !editEnabled;
  editProfileBtn.disabled = editEnabled;
  profileModalTitle.textContent = editEnabled ? `Edit Profile: ${profileModalFile}` : `Profile Preview: ${profileModalFile}`;
}

function defaultSaveAsName(profileFile) {
  if (!profileFile) {
    return 'new_profile.json';
  }
  const base = profileFile.replace(/\.json$/i, '');
  return `${base}_copy.json`;
}

function openProfileModal(fileName) {
  profileModalFile = fileName;
  setProfileEditMode(false);
  saveAsNameInput.value = defaultSaveAsName(fileName);
  profileModal.hidden = false;
  profileModal.classList.remove('hidden');
}

function closeProfileModal() {
  profileModal.hidden = true;
  profileModal.classList.add('hidden');
  profileModalFile = '';
  profileEditor.value = '';
  saveAsNameInput.value = '';
}

async function saveSelectedProfile() {
  const profileFile = profileModalFile || profileSelect.value;
  if (!profileFile) {
    throw new Error('No profile selected');
  }
  const res = await api(`/api/profiles/${encodeURIComponent(profileFile)}`, 'PUT', {
    content: profileEditor.value
  });
  await loadProfiles();
  profileSelect.value = profileFile;
  await previewSelectedProfile();
  return res;
}

async function saveProfileAs() {
  const fileName = (saveAsNameInput.value || '').trim();
  if (!fileName) {
    throw new Error('Please enter a new profile file name');
  }
  const res = await api('/api/profiles/save-as', 'POST', {
    file_name: fileName,
    content: profileEditor.value
  });
  const newFile = res.file || fileName;
  await loadProfiles();
  profileSelect.value = newFile;
  const loadedFile = await previewSelectedProfile();
  openProfileModal(loadedFile);
  return res;
}

function pushChartPoint(snapshot) {
  const t = toChartTime(snapshot.session_elapsed_s);
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
  const rawT = Number(elapsedSeconds);
  const key = `${marker}@${rawT.toFixed(2)}`;
  if (seenEventKeys.has(key)) {
    return;
  }
  seenEventKeys.add(key);
  const t = toChartTime(rawT);
  const prev = stageEvents.length ? stageEvents[stageEvents.length - 1].t : null;
  const delta = prev == null ? t : (t - prev);
  stageEvents.push({
    t,
    label: stageKeyToLabel(marker),
    deltaLabel: formatElapsed(delta)
  });
}

function updateSnapshot(snapshot, force = false) {
  const nowMs = Date.now();
  if (!force && nowMs - lastUiUpdateMs < UI_UPDATE_INTERVAL_MS) {
    return;
  }
  lastUiUpdateMs = nowMs;

  if (snapshot.bean_drop_elapsed_s != null) {
    setBeanDropOrigin(snapshot.bean_drop_elapsed_s);
  }

  stateVal.textContent = snapshot.state;
  const elapsedForDisplay = snapshot.roast_elapsed_s != null
    ? Number(snapshot.roast_elapsed_s)
    : Number(snapshot.session_elapsed_s ?? 0);
  elapsedVal.textContent = formatElapsed(elapsedForDisplay);
  stageVal.textContent = snapshot.stage_label;
  stageElapsedVal.textContent = formatElapsed(snapshot.stage_elapsed_s);
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
      beanDropElapsed = null;
      updateChartXAxisTitle();
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

  document.getElementById('saveGraphBtn').addEventListener('click', () => {
    try {
      saveGraphSnapshot();
      setStatus('Graph snapshot saved');
    } catch (err) {
      setStatus(`Failed to save graph snapshot: ${err.message}`, true);
    }
  });

  document.getElementById('previewProfileBtn').addEventListener('click', async () => {
    try {
      const fileName = await previewSelectedProfile();
      openProfileModal(fileName);
      setStatus(`Profile loaded: ${fileName}`);
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  saveProfileBtn.addEventListener('click', async () => {
    try {
      const res = await saveSelectedProfile();
      setProfileEditMode(false);
      setStatus(res.message || 'Profile saved');
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  saveAsProfileBtn.addEventListener('click', async () => {
    try {
      const res = await saveProfileAs();
      setStatus(res.message || 'Profile saved as new file');
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  editProfileBtn.addEventListener('click', () => {
    if (!profileModalFile) {
      setStatus('No profile loaded for edit', true);
      return;
    }
    setProfileEditMode(true);
    profileEditor.focus();
  });

  closeProfileModalBtn.addEventListener('click', () => {
    closeProfileModal();
    setStatus('Profile preview closed');
  });

  document.addEventListener('click', (event) => {
    if (profileModal.hidden) {
      return;
    }
    if (!profileModal.contains(event.target) && event.target.id !== 'previewProfileBtn') {
      closeProfileModal();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !profileModal.hidden) {
      closeProfileModal();
      setStatus('Profile preview closed');
    }
  });

  profileSelect.addEventListener('change', async () => {
    if (!profileModal.hidden) {
      closeProfileModal();
    }
    setStatus(`Profile selected: ${profileSelect.value}`);
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
    updateChartXAxisTitle();
    await loadProfiles();
    const snapshot = await api('/api/session');
    updateSnapshot(snapshot, true);
  } catch (err) {
    setStatus(err.message, true);
  }
  connectWs();
})();
