(() => {
  const dateTitle = document.querySelector('#date-title');
  const fullDate = document.querySelector('#full-date');
  const list = document.querySelector('#task-list');
  const loginScreen = document.querySelector('#login-screen');
  const loginError = document.querySelector('#login-error');
  const plannerView = document.querySelector('#planner-view');
  const weightView = document.querySelector('#weight-view');
  const stepsView = document.querySelector('#steps-view');
  const healthView = document.querySelector('#health-view');
  const importView = document.querySelector('#import-view');
  const weightList = document.querySelector('#weight-list');
  const stepsList = document.querySelector('#steps-list');
  const healthList = document.querySelector('#health-list');
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  let shown = new Date(today);
  let tasks = [];
  const key = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const days = ['sekmadienis', 'pirmadienis', 'antradienis', 'trečiadienis', 'ketvirtadienis', 'penktadienis', 'šeštadienis'];
  const fmt = new Intl.DateTimeFormat('lt-LT', { year: 'numeric', month: 'long', day: 'numeric' });
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  async function api(path, options = {}) {
    const headers = { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) };
    const response = await fetch(path, { ...options, headers, credentials: 'same-origin' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 && path !== '/api/login') showLogin();
      throw new Error(payload.error || 'Nepavyko atlikti veiksmo.');
    }
    return payload;
  }

  function showLogin() {
    loginScreen.hidden = false;
    document.querySelector('#password').focus();
  }

  function render() {
    const currentDate = key(shown);
    dateTitle.textContent = fmt.format(shown);
    fullDate.textContent = `${days[shown.getDay()]} · ${fmt.format(shown)}`;
    document.querySelector('#greeting').textContent = currentDate === key(today)
      ? 'Sveiki atvykę į savo dieną'
      : `Jūsų planas · ${days[shown.getDay()]}`;
    document.querySelector('#task-count').textContent = `${tasks.length} ${tasks.length === 1 ? 'užduotis' : (tasks.length % 10 >= 2 && tasks.length % 10 <= 9 && Math.floor(tasks.length / 10) % 10 !== 1 ? 'užduotys' : 'užduočių')}`;
    if (!tasks.length) {
      list.innerHTML = '<div class="empty">Kol kas planas tuščias. Pridėkite pirmą užduotį aukščiau.</div>';
    } else {
      list.innerHTML = tasks.map(t => `<div class="task ${t.done ? 'done' : ''}"><input class="check" type="checkbox" data-id="${t.id}" ${t.done ? 'checked' : ''} aria-label="Pažymėti atlikta"><div class="task-content"><div class="task-name">${esc(t.text)}</div><div class="task-meta">${t.time ? `<span class="task-time">${esc(t.time)}</span>` : ''}<span class="tag">${esc(t.category)}</span></div></div><button class="delete" data-del="${t.id}" aria-label="Ištrinti užduotį">×</button></div>`).join('');
    }
    const done = tasks.filter(t => t.done).length;
    const pct = tasks.length ? Math.round(done / tasks.length * 100) : 0;
    document.querySelector('#progress-count').textContent = `${done} / ${tasks.length}`;
    document.querySelector('#progress-label').textContent = tasks.length ? (pct === 100 ? 'Puikiai, viskas atlikta!' : `Atlikta ${pct}%`) : 'Dar nepradėta';
    document.querySelector('#progress-bar').style.width = `${pct}%`;
  }

  async function loadTasks() {
    list.innerHTML = '<div class="empty">Kraunamos užduotys…</div>';
    try {
      const result = await api(`/api/tasks?date=${encodeURIComponent(key(shown))}`);
      tasks = result.tasks;
      render();
    } catch (error) {
      list.innerHTML = `<div class="empty">${esc(error.message)}</div>`;
    }
  }

  async function loadWeights() {
    weightList.innerHTML = '<div class="weight-empty">Kraunami įrašai…</div>';
    try {
      const result = await api('/api/weights');
      if (!result.weights.length) {
        weightList.innerHTML = '<div class="weight-empty">Svorio įrašų dar nėra.</div>';
        return;
      }
      weightList.innerHTML = result.weights.map(entry => {
        const date = new Intl.DateTimeFormat('lt-LT', { year: 'numeric', month: 'long', day: 'numeric' })
          .format(new Date(`${entry.date}T00:00:00`));
        const weight = Number(entry.weight).toLocaleString('lt-LT', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
        return `<div class="weight-entry"><span>${esc(date)}</span><strong>${esc(weight)} kg</strong><button class="delete" data-weight-del="${esc(entry.date)}" aria-label="Ištrinti svorio įrašą">×</button></div>`;
      }).join('');
    } catch (error) {
      weightList.innerHTML = `<div class="weight-empty">${esc(error.message)}</div>`;
    }
  }

  async function loadSteps() {
    stepsList.innerHTML = '<div class="weight-empty">Kraunami įrašai…</div>';
    try {
      const result = await api('/api/steps');
      if (!result.steps.length) {
        stepsList.innerHTML = '<div class="weight-empty">Žingsnių įrašų dar nėra.</div>';
        return;
      }
      stepsList.innerHTML = result.steps.map(entry => {
        const date = new Intl.DateTimeFormat('lt-LT', { year: 'numeric', month: 'long', day: 'numeric' })
          .format(new Date(`${entry.date}T00:00:00`));
        const count = Number(entry.count).toLocaleString('lt-LT');
        return `<div class="weight-entry"><span>${esc(date)}</span><strong>${esc(count)} žingsn.</strong><button class="delete" data-steps-del="${esc(entry.date)}" aria-label="Ištrinti žingsnių įrašą">×</button></div>`;
      }).join('');
    } catch (error) {
      stepsList.innerHTML = `<div class="weight-empty">${esc(error.message)}</div>`;
    }
  }

  async function loadHealth() {
    healthList.innerHTML = '<div class="weight-empty">Kraunami įrašai…</div>';
    try {
      const result = await api('/api/vitals');
      if (!result.vitals.length) {
        healthList.innerHTML = '<div class="weight-empty">Matavimų dar nėra.</div>';
        return;
      }
      healthList.innerHTML = result.vitals.map(entry => {
        const date = new Intl.DateTimeFormat('lt-LT', { year: 'numeric', month: 'long', day: 'numeric' })
          .format(new Date(`${entry.date}T00:00:00`));
        return `<div class="weight-entry"><span>${esc(date)}</span><strong>Pulsas ${esc(entry.pulse)} · ${esc(entry.systolic)}/${esc(entry.diastolic)} mmHg</strong><button class="delete" data-health-del="${esc(entry.date)}" aria-label="Ištrinti matavimą">×</button></div>`;
      }).join('');
    } catch (error) {
      healthList.innerHTML = `<div class="weight-empty">${esc(error.message)}</div>`;
    }
  }

  function showView(view) {
    const showWeights = view === 'weight';
    const showSteps = view === 'steps';
    const showHealth = view === 'health';
    const showImport = view === 'import';
    plannerView.hidden = showWeights || showSteps || showHealth || showImport;
    weightView.hidden = !showWeights;
    stepsView.hidden = !showSteps;
    healthView.hidden = !showHealth;
    importView.hidden = !showImport;
    document.querySelector('#menu-planner').classList.toggle('active', !showWeights && !showSteps && !showHealth && !showImport);
    document.querySelector('#menu-weight').classList.toggle('active', showWeights);
    document.querySelector('#menu-steps').classList.toggle('active', showSteps);
    document.querySelector('#menu-health').classList.toggle('active', showHealth);
    document.querySelector('#menu-import').classList.toggle('active', showImport);
    if (showWeights) loadWeights();
    if (showSteps) loadSteps();
    if (showHealth) loadHealth();
  }

  document.querySelector('#menu-planner').addEventListener('click', () => showView('planner'));
  document.querySelector('#menu-weight').addEventListener('click', () => showView('weight'));
  document.querySelector('#menu-steps').addEventListener('click', () => showView('steps'));
  document.querySelector('#menu-health').addEventListener('click', () => showView('health'));
  document.querySelector('#menu-import').addEventListener('click', () => showView('import'));

  let importData = null;
  const importText = document.querySelector('#import-text');
  const importError = document.querySelector('#import-error');
  const importPreview = document.querySelector('#import-preview');
  const importSave = document.querySelector('#save-import');
  const validDate = value => {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const parsed = new Date(`${value}T00:00:00Z`);
    return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
  };
  function parsePlannerImport(raw) {
    const result = { tasks: [], weights: [], steps: [], vitals: [] };
    const categories = ['Darbas', 'Asmeniniai', 'Sveikata', 'Kita'];
    const lines = raw.split(/\r?\n/).map(line => line.trim().replace(/^(?:[-*]\s+|\d+[.)]\s+)/, '')).filter(Boolean);
    if (!lines.length) throw new Error('Įklijuok ChatGPT paruoštas eilutes.');
    const number = (value, label) => {
      const parsed = Number(value.trim().replace(/\s/g, '').replace(',', '.').replace(/\s*kg$/i, ''));
      if (!Number.isFinite(parsed)) throw new Error(`Neteisinga reikšmė: ${label}.`);
      return parsed;
    };
    lines.forEach((line, index) => {
      const fields = line.split('|').map(field => field.trim());
      const type = fields[0].toLocaleLowerCase('lt-LT');
      const lineError = message => { throw new Error(`Eilutė ${index + 1}: ${message}`); };
      if (type === 'užduotis' || type === 'uzduotis') {
        const [, date, time, category, ...text] = fields;
        const title = text.join(' | ').trim();
        if (!validDate(date)) lineError('data turi būti YYYY-MM-DD formatu.');
        if (time !== '-' && time !== '' && !/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) lineError('laikas turi būti HH:MM arba -.');
        if (!categories.includes(category)) lineError('kategorija turi būti Darbas, Asmeniniai, Sveikata arba Kita.');
        if (!title || title.length > 120) lineError('trūksta užduoties teksto arba jis per ilgas.');
        result.tasks.push({ date, text: title, category, time: time === '-' ? '' : time });
      } else if (type === 'svoris') {
        const [, date, rawWeight] = fields;
        if (!validDate(date)) lineError('data turi būti YYYY-MM-DD formatu.');
        const weight = number(rawWeight || '', 'svoris');
        if (fields.length !== 3 || weight < 1 || weight > 500) lineError('naudok „Svoris | data | kg“ (1–500).');
        result.weights.push({ date, weight });
      } else if (type === 'žingsniai' || type === 'zingsniai') {
        const [, date, rawCount] = fields;
        if (!validDate(date)) lineError('data turi būti YYYY-MM-DD formatu.');
        const count = number(rawCount || '', 'žingsnių skaičius');
        if (fields.length !== 3 || !Number.isInteger(count) || count < 0 || count > 200000) lineError('naudok „Žingsniai | data | skaičius“ (0–200 000).');
        result.steps.push({ date, count });
      } else if (type === 'sveikata') {
        const [, date, rawPulse, rawSystolic, rawDiastolic] = fields;
        if (!validDate(date)) lineError('data turi būti YYYY-MM-DD formatu.');
        const pulse = number(rawPulse || '', 'pulsas');
        const systolic = number(rawSystolic || '', 'viršutinis spaudimas');
        const diastolic = number(rawDiastolic || '', 'apatinis spaudimas');
        if (fields.length !== 5 || ![pulse, systolic, diastolic].every(Number.isInteger) || pulse < 20 || pulse > 250 || systolic < 40 || systolic > 300 || diastolic < 20 || diastolic > 200 || systolic <= diastolic) lineError('naudok „Sveikata | data | pulsas | viršutinis | apatinis“.');
        result.vitals.push({ date, pulse, systolic, diastolic });
      } else {
        lineError('įrašo tipas turi būti Užduotis, Svoris, Žingsniai arba Sveikata.');
      }
    });
    if (lines.length > 100) throw new Error('Galima įkelti iki 100 eilučių vienu kartu.');
    if (!result.tasks.length && !result.weights.length && !result.steps.length && !result.vitals.length) {
      throw new Error('Nerasta planuoklio įrašų.');
    }
    return result;
  }
  function renderImportPreview(data) {
    const lines = [];
    data.tasks.forEach(item => lines.push(`Užduotis · ${item.date}${item.time ? ` ${item.time}` : ''} · ${item.category} · ${item.text}`));
    data.weights.forEach(item => lines.push(`Svoris · ${item.date} · ${item.weight} kg`));
    data.steps.forEach(item => lines.push(`Žingsniai · ${item.date} · ${item.count}`));
    data.vitals.forEach(item => lines.push(`Sveikata · ${item.date} · pulsas ${item.pulse}, kraujospūdis ${item.systolic}/${item.diastolic} mmHg`));
    importPreview.innerHTML = `<strong>Bus išsaugota (${lines.length} įraš.):</strong><ul>${lines.map(line => `<li>${esc(line)}</li>`).join('')}</ul><small>Jei tai datai jau yra svorio, žingsnių ar sveikatos įrašas, jis bus atnaujintas.</small>`;
  }
  document.querySelector('#copy-import-prompt').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(document.querySelector('#import-prompt').textContent);
      importError.textContent = 'Nurodymas nukopijuotas. Įklijuok jį ChatGPT pokalbyje.';
    } catch (_) { importError.textContent = 'Nepavyko nukopijuoti automatiškai. Pažymėk ir nukopijuok nurodymo tekstą.'; }
  });
  document.querySelector('#preview-import').addEventListener('click', () => {
    importError.textContent = '';
    importSave.disabled = true;
    importPreview.textContent = '';
    try {
      importData = parsePlannerImport(importText.value);
      renderImportPreview(importData);
      importSave.disabled = false;
    } catch (error) { importData = null; importError.textContent = error instanceof SyntaxError ? 'Nepavyko perskaityti JSON. Nukopijuok visą ChatGPT pateiktą objektą.' : error.message; }
  });
  importText.addEventListener('input', () => {
    importData = null;
    importSave.disabled = true;
    importPreview.textContent = '';
    importError.textContent = '';
  });
  importSave.addEventListener('click', async () => {
    if (!importData) return;
    importSave.disabled = true;
    importError.textContent = 'Išsaugoma…';
    try {
      const result = await api('/api/import', { method: 'POST', body: JSON.stringify(importData) });
      const total = result.counts.tasks + result.counts.weights + result.counts.steps + result.counts.vitals;
      importError.textContent = `Išsaugota į planuoklį: ${total} įraš.`;
      importText.value = '';
      importPreview.textContent = '';
      importData = null;
      if (result.counts.weights) loadWeights();
      if (result.counts.steps) loadSteps();
      if (result.counts.vitals) loadHealth();
      if (result.counts.tasks && result.tasks_dates.includes(key(shown))) loadTasks();
    } catch (error) { importError.textContent = error.message; importSave.disabled = false; }
  });
  document.querySelector('#weight-date').value = key(today);
  document.querySelector('#steps-date').value = key(today);
  document.querySelector('#health-date').value = key(today);

  document.querySelector('#weight-form').addEventListener('submit', async event => {
    event.preventDefault();
    const date = document.querySelector('#weight-date').value;
    const weight = Number(document.querySelector('#weight-value').value);
    try {
      await api('/api/weights', { method: 'POST', body: JSON.stringify({ date, weight }) });
      document.querySelector('#weight-value').value = '';
      await loadWeights();
    } catch (error) {
      window.alert(error.message);
    }
  });

  weightList.addEventListener('click', async event => {
    const button = event.target.closest('[data-weight-del]');
    if (!button) return;
    try {
      await api(`/api/weights/${encodeURIComponent(button.dataset.weightDel)}`, { method: 'DELETE' });
      await loadWeights();
    } catch (error) {
      window.alert(error.message);
    }
  });

  document.querySelector('#steps-form').addEventListener('submit', async event => {
    event.preventDefault();
    const date = document.querySelector('#steps-date').value;
    const count = Number(document.querySelector('#steps-count').value);
    try {
      await api('/api/steps', { method: 'POST', body: JSON.stringify({ date, count }) });
      document.querySelector('#steps-count').value = '';
      await loadSteps();
    } catch (error) {
      window.alert(error.message);
    }
  });

  stepsList.addEventListener('click', async event => {
    const button = event.target.closest('[data-steps-del]');
    if (!button) return;
    try {
      await api(`/api/steps/${encodeURIComponent(button.dataset.stepsDel)}`, { method: 'DELETE' });
      await loadSteps();
    } catch (error) {
      window.alert(error.message);
    }
  });

  document.querySelector('#health-form').addEventListener('submit', async event => {
    event.preventDefault();
    const data = {
      date: document.querySelector('#health-date').value,
      pulse: Number(document.querySelector('#health-pulse').value),
      systolic: Number(document.querySelector('#health-systolic').value),
      diastolic: Number(document.querySelector('#health-diastolic').value),
    };
    try {
      await api('/api/vitals', { method: 'POST', body: JSON.stringify(data) });
      document.querySelector('#health-pulse').value = '';
      document.querySelector('#health-systolic').value = '';
      document.querySelector('#health-diastolic').value = '';
      await loadHealth();
    } catch (error) {
      window.alert(error.message);
    }
  });

  healthList.addEventListener('click', async event => {
    const button = event.target.closest('[data-health-del]');
    if (!button) return;
    try {
      await api(`/api/vitals/${encodeURIComponent(button.dataset.healthDel)}`, { method: 'DELETE' });
      await loadHealth();
    } catch (error) {
      window.alert(error.message);
    }
  });

  document.querySelector('#login-form').addEventListener('submit', async event => {
    event.preventDefault();
    loginError.textContent = '';
    try {
      await api('/api/login', { method: 'POST', body: JSON.stringify({ password: document.querySelector('#password').value }) });
      document.querySelector('#password').value = '';
      loginScreen.hidden = true;
      await loadTasks();
    } catch (error) {
      loginError.textContent = error.message;
    }
  });

  document.querySelector('#logout').addEventListener('click', async () => {
    try { await api('/api/logout', { method: 'POST', body: '{}' }); } catch (_) { /* Show login even if the session expired. */ }
    showLogin();
  });

  document.querySelector('#task-form').addEventListener('submit', async event => {
    event.preventDefault();
    const input = document.querySelector('#task-input');
    const text = input.value.trim();
    if (!text) return;
    try {
      await api('/api/tasks', { method: 'POST', body: JSON.stringify({
        date: key(shown), text, category: document.querySelector('#category').value,
        time: document.querySelector('#task-time').value,
      }) });
      input.value = '';
      document.querySelector('#task-time').value = '';
      await loadTasks();
      input.focus();
    } catch (error) { window.alert(error.message); }
  });

  list.addEventListener('change', async event => {
    if (!event.target.matches('.check')) return;
    try {
      await api(`/api/tasks/${event.target.dataset.id}`, { method: 'PATCH', body: JSON.stringify({ done: event.target.checked }) });
      await loadTasks();
    } catch (error) { window.alert(error.message); }
  });

  list.addEventListener('click', async event => {
    const button = event.target.closest('[data-del]');
    if (!button) return;
    try {
      await api(`/api/tasks/${button.dataset.del}`, { method: 'DELETE' });
      await loadTasks();
    } catch (error) { window.alert(error.message); }
  });

  document.querySelector('#prev').onclick = async () => { shown.setDate(shown.getDate() - 1); await loadTasks(); };
  document.querySelector('#next').onclick = async () => { shown.setDate(shown.getDate() + 1); await loadTasks(); };
  document.querySelector('#today').onclick = async () => { shown = new Date(today); await loadTasks(); };

  api('/api/session').then(async state => {
    if (state.authenticated) { loginScreen.hidden = true; await loadTasks(); }
    else showLogin();
  }).catch(showLogin);
  render();
})();
