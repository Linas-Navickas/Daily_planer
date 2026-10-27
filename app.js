(() => {
  const dateTitle = document.querySelector('#date-title');
  const fullDate = document.querySelector('#full-date');
  const list = document.querySelector('#task-list');
  const loginScreen = document.querySelector('#login-screen');
  const loginError = document.querySelector('#login-error');
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
