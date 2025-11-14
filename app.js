// Shared helper
async function api(path, opts={}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || 'API error');
  }
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  return res.text();
}

/* ---------- Utilities ---------- */
function formatCurrency(n){ return Number(n || 0).toLocaleString('en-IN', {maximumFractionDigits:2}); }
function $(sel){ return document.querySelector(sel); }
function clearForm(form){ form.querySelectorAll('input,textarea').forEach(i=>i.value=''); }

async function loadCategories(){
  try{
    const cats = await api('/api/categories');
    const sel = $('#filterCat');
    sel.innerHTML = '<option value="">All categories</option>';
    cats.forEach(c => { const o = document.createElement('option'); o.value=c; o.textContent=c; sel.appendChild(o); });
  }catch(e){ console.warn(e); }
}

/* ---------- Summary & Charts ---------- */
let catChart, trendChart;
async function loadSummary(y,m){
  const params = new URLSearchParams();
  if (y) params.set('y', y);
  if (m) params.set('m', m);
  const s = await api('/api/summary?' + params.toString());
  $('#totalExpense').innerText = formatCurrency(s.totals.expense);
  $('#totalIncome').innerText = formatCurrency(s.totals.income);
  $('#budgetVal').innerText = formatCurrency(s.budget);
  // budget alert
  if (s.totals.expense > s.budget && s.budget > 0) {
    $('#budgetAlert').style.display='block';
    $('#budgetAlert').innerText = `Warning: You exceeded your monthly budget by ₹ ${formatCurrency(s.totals.expense - s.budget)}`;
  } else { $('#budgetAlert').style.display='none'; }
  // category pie
  const labels = s.categories.map(c=>c.category);
  const data = s.categories.map(c=>c.amount);
  const ctx = document.getElementById('catChart').getContext('2d');
  if (catChart) catChart.destroy();
  catChart = new Chart(ctx, {type:'pie', data:{labels,datasets:[{data}]}, options:{plugins:{legend:{position:'bottom'}}}});
  // trend
  const tlabels = s.trend.map(t=>`${t.y}-${String(t.m).padStart(2,'0')}`);
  const tdata = s.trend.map(t=>t.amount);
  const c2 = document.getElementById('trendChart').getContext('2d');
  if (trendChart) trendChart.destroy();
  trendChart = new Chart(c2, {type:'bar', data:{labels:tlabels,datasets:[{label:'Expense',data:tdata}]}, options:{plugins:{legend:{display:false}}}});
}

/* populate month selector */
function populateMonthSelect(){
  const sel = document.getElementById('selectMonth');
  const today = new Date();
  for(let i=0;i<12;i++){
    const d = new Date(today.getFullYear(), today.getMonth()-i, 1);
    const opt = document.createElement('option');
    opt.value = `${d.getFullYear()}-${d.getMonth()+1}`;
    opt.textContent = d.toLocaleString('default',{month:'short',year:'numeric'});
    sel.appendChild(opt);
  }
  sel.selectedIndex = 0;
}

/* ---------- Transactions table ---------- */
async function loadTransactions(){
  const q = $('#q').value.trim();
  const from = $('#from').value;
  const to = $('#to').value;
  const cat = $('#filterCat').value;
  const kind = $('#filterKind').value;
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (from) params.set('from', from);
  if (to) params.set('to', to);
  if (cat) params.set('category', cat);
  if (kind) params.set('kind', kind);
  const rows = await api('/api/expenses?' + params.toString());
  const tbody = document.querySelector('#txTable tbody');
  tbody.innerHTML = '';
  rows.forEach(r=>{
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${r.date}</td><td>${r.title}</td><td>${r.category}</td><td>${r.kind}</td><td class="amount">₹ ${formatCurrency(r.amount)}</td>
      <td><button class="btn small delete" data-id="${r.id}">Delete</button></td>`;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll('button.delete').forEach(b=> b.addEventListener('click', async (e)=>{
    if(!confirm('Delete transaction?')) return;
    await api('/api/expenses/' + e.currentTarget.dataset.id, {method:'DELETE'});
    await loadTransactions(); await loadSummaryFromSelect();
  }));
}

/* ---------- Add transaction ---------- */
$('#addForm') && $('#addForm').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const payload = {
    kind: $('#kind').value,
    title: $('#title').value.trim(),
    amount: $('#amount').value,
    category: $('#category').value.trim(),
    date: $('#date').value || new Date().toISOString().slice(0,10),
    notes: $('#notes').value.trim()
  };
  try {
    await api('/api/expenses', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    clearForm(document.getElementById('addForm'));
    await loadTransactions(); await loadSummaryFromSelect(); loadCategories();
  } catch (err) { alert('Failed: ' + err.message); }
});

/* ---------- Recurring ---------- */
$('#recForm') && $('#recForm').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const payload = {
    title: $('#r_title').value.trim(),
    amount: $('#r_amount').value,
    category: $('#r_category').value.trim(),
    cadence: $('#r_cadence').value,
    next_date: $('#r_next').value || new Date().toISOString().slice(0,10),
    kind: 'expense'
  };
  try{
    await api('/api/recurring', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    clearForm(document.getElementById('recForm'));
    alert('Recurring added');
  }catch(err){ alert('Failed: '+err.message); }
});
$('#runRecurring') && $('#runRecurring').addEventListener('click', async ()=>{
  try{ const res = await api('/api/run-recurring',{method:'POST'}); alert('Recurring run. Added dates: ' + res.created_dates.join(',')); await loadTransactions(); await loadSummaryFromSelect(); }catch(e){ alert(e.message); }
});

/* ---------- Export / Import / Backup / Restore ---------- */
$('#exportCSV') && $('#exportCSV').addEventListener('click', ()=>{
  // use current filters
  const q = $('#q').value.trim(); const from = $('#from').value; const to = $('#to').value; const cat = $('#filterCat').value; const kind = $('#filterKind').value;
  const params = new URLSearchParams();
  if(q) params.set('q',q); if(from) params.set('from',from); if(to) params.set('to',to); if(cat) params.set('category',cat); if(kind) params.set('kind',kind);
  window.location = '/api/export-csv?' + params.toString();
});
$('#importCSV') && $('#importCSV').addEventListener('change', async (e)=>{
  const f = e.target.files[0]; if(!f) return;
  const fd = new FormData(); fd.append('file', f);
  try{ const res = await fetch('/api/import-csv', {method:'POST', body: fd}); const j = await res.json(); alert('Imported: ' + j.inserted); await loadTransactions(); }catch(err){ alert('Import failed'); }
});
$('#backupJson') && $('#backupJson').addEventListener('click', ()=> window.location = '/api/backup-json');
$('#restoreJSON') && $('#restoreJSON').addEventListener('change', async (e)=> {
  const f = e.target.files[0]; if(!f) return;
  const fd = new FormData(); fd.append('file', f);
  try{ const res = await fetch('/api/restore-json', {method:'POST', body: fd}); const j = await res.json(); alert('Restored: ' + j.inserted); await loadTransactions(); await loadSummaryFromSelect(); }catch(err){ alert('Restore failed'); }
});

/* ---------- Budget setting ---------- */
$('#saveBudget') && $('#saveBudget').addEventListener('click', async ()=>{
  const v = $('#monthlyBudget').value || 0;
  await api('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({monthly_budget: v})});
  alert('Budget saved'); await loadSummaryFromSelect();
});

/* ---------- Helper: load from selected month ---------- */
function loadSummaryFromSelect(){
  const val = $('#selectMonth').value;
  if(!val) return loadSummary();
  const [y,m] = val.split('-').map(Number);
  return loadSummary(y,m);
}

/* ---------- Theme toggle ---------- */
$('#toggleTheme') && $('#toggleTheme').addEventListener('click', ()=>{
  document.documentElement.classList.toggle('dark-mode');
});

/* ---------- Filters and init ---------- */
$('#filterBtn') && $('#filterBtn').addEventListener('click', ()=>{ loadTransactions(); });

function init(){
  populateMonthSelect();
  loadCategories();
  loadTransactions();
  loadSummaryFromSelect();
  $('#selectMonth').addEventListener('change', loadSummaryFromSelect);
  $('#refreshSummary') && $('#refreshSummary').addEventListener('click', loadSummaryFromSelect);
}
window.addEventListener('load', init);
