import sqlite3, csv, io, json, os
from flask import Flask, g, render_template, request, jsonify, send_file, redirect, url_for
from pathlib import Path
from datetime import datetime, date, timedelta

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / 'expense.db'

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

# ---------- DB helpers ----------
def get_db():
    db = getattr(g, '_db', None)
    if db is None:
        need_init = not DB_PATH.exists()
        db = g._db = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        db.row_factory = sqlite3.Row
        if need_init:
            init_db(db)
    return db

def init_db(db):
    c = db.cursor()
    c.executescript("""
    CREATE TABLE expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,          -- 'expense' or 'income'
        title TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT,
        date TEXT NOT NULL,          -- YYYY-MM-DD
        notes TEXT,
        receipt TEXT,                -- filename (optional)
        created_at TEXT
    );
    CREATE TABLE recurring (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT,
        kind TEXT NOT NULL, -- expense|income
        cadence TEXT NOT NULL, -- monthly/weekly
        next_date TEXT NOT NULL,
        active INTEGER DEFAULT 1
    );
    CREATE TABLE settings (
        k TEXT PRIMARY KEY,
        v TEXT
    );
    """)
    # seed categories & sample data
    sample = [
        ('expense','Lunch',120.0,'Food', (date.today()-timedelta(days=2)).isoformat(), 'breakfast', None, datetime.now().isoformat()),
        ('expense','Bus pass',600.0,'Transport', (date.today()-timedelta(days=7)).isoformat(), '', None, datetime.now().isoformat()),
        ('income','Stipend',5000.0,'Income', (date.today()-timedelta(days=20)).isoformat(), 'monthly stipend', None, datetime.now().isoformat()),
    ]
    c.executemany('INSERT INTO expenses (kind,title,amount,category,date,notes,receipt,created_at) VALUES (?,?,?,?,?,?,?,?)', sample)
    # default budget (monthly)
    c.execute('INSERT INTO settings (k,v) VALUES (?,?)', ('monthly_budget', '10000'))
    db.commit()

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, '_db', None)
    if db: db.close()

# ---------- Utilities ----------
def row_to_dict(r):
    return {k: (r[k] if not isinstance(r[k], bytes) else r[k].decode()) for k in r.keys()}

# Simple auto-category mapping (can be extended)
CATEGORY_MAP = {
    'pizza': 'Food', 'burger':'Food','cafe':'Food','lunch':'Food','dinner':'Food',
    'uber':'Transport','bus':'Transport','cab':'Transport','train':'Transport',
    'grocery':'Groceries','supermarket':'Groceries','flipkart':'Shopping','amazon':'Shopping',
    'rent':'Rent','salary':'Income','stipend':'Income','subscription':'Bills','netflix':'Entertainment'
}

def auto_category(title):
    t = title.lower()
    for k,v in CATEGORY_MAP.items():
        if k in t:
            return v
    return 'Other'

# ---------- API / Pages ----------
@app.route('/')
def index():
    return render_template('index.html')

# Create / Read / Update / Delete expenses
@app.route('/api/expenses', methods=['GET'])
def api_list_expenses():
    # supports filters: q, from, to, category, kind (expense/income), limit
    q = request.args.get('q','').strip()
    dfrom = request.args.get('from')
    dto = request.args.get('to')
    category = request.args.get('category','').strip()
    kind = request.args.get('kind','').strip()
    limit = int(request.args.get('limit', 500))
    db = get_db()
    sql = 'SELECT * FROM expenses WHERE 1=1'
    params = []
    if q:
        sql += ' AND (title LIKE ? OR notes LIKE ?)'
        params += [f'%{q}%', f'%{q}%']
    if dfrom:
        sql += ' AND date >= ?'; params.append(dfrom)
    if dto:
        sql += ' AND date <= ?'; params.append(dto)
    if category:
        sql += ' AND category = ?'; params.append(category)
    if kind:
        sql += ' AND kind = ?'; params.append(kind)
    sql += ' ORDER BY date DESC, id DESC LIMIT ?'; params.append(limit)
    rows = db.execute(sql, params).fetchall()
    return jsonify([row_to_dict(r) for r in rows])

@app.route('/api/expenses', methods=['POST'])
def api_add_expense():
    payload = request.get_json() or {}
    title = payload.get('title','').strip()
    amount = float(payload.get('amount') or 0)
    kind = payload.get('kind','expense')
    category = payload.get('category') or auto_category(title)
    d = payload.get('date') or date.today().isoformat()
    notes = payload.get('notes','')
    if not title or amount == 0:
        return jsonify({'error':'title and amount required'}), 400
    db = get_db()
    cur = db.execute('INSERT INTO expenses (kind,title,amount,category,date,notes,created_at) VALUES (?,?,?,?,?,?,?)',
                     (kind,title,amount,category,d,notes, datetime.now().isoformat()))
    db.commit()
    return jsonify({'id': cur.lastrowid}), 201

@app.route('/api/expenses/<int:eid>', methods=['PUT'])
def api_update_expense(eid):
    payload = request.get_json() or {}
    title = payload.get('title','').strip()
    amount = float(payload.get('amount') or 0)
    kind = payload.get('kind','expense')
    category = payload.get('category') or auto_category(title)
    d = payload.get('date') or date.today().isoformat()
    notes = payload.get('notes','')
    db = get_db()
    db.execute('UPDATE expenses SET kind=?,title=?,amount=?,category=?,date=?,notes=? WHERE id=?',
               (kind,title,amount,category,d,notes,eid))
    db.commit()
    return jsonify({'status':'ok'})

@app.route('/api/expenses/<int:eid>', methods=['DELETE'])
def api_delete_expense(eid):
    db = get_db()
    db.execute('DELETE FROM expenses WHERE id=?', (eid,))
    db.commit()
    return jsonify({'status':'deleted'})

# Recurring templates
@app.route('/api/recurring', methods=['GET','POST'])
def api_recurring():
    db = get_db()
    if request.method == 'GET':
        rows = db.execute('SELECT * FROM recurring WHERE active=1').fetchall()
        return jsonify([row_to_dict(r) for r in rows])
    payload = request.get_json() or {}
    title = payload.get('title'); amount = float(payload.get('amount') or 0)
    cadence = payload.get('cadence','monthly')  # monthly/weekly
    kind = payload.get('kind','expense'); category = payload.get('category') or auto_category(title)
    next_date = payload.get('next_date') or date.today().isoformat()
    cur = db.execute('INSERT INTO recurring (title,amount,category,kind,cadence,next_date,active) VALUES (?,?,?,?,?,?,1)',
                     (title, amount, category, kind, cadence, next_date))
    db.commit()
    return jsonify({'id': cur.lastrowid}), 201

# Apply recurring: create due expenses up to today and advance next_date
@app.route('/api/run-recurring', methods=['POST'])
def api_run_recurring():
    db = get_db()
    rows = db.execute('SELECT * FROM recurring WHERE active=1').fetchall()
    created = []
    for r in rows:
        next_d = datetime.strptime(r['next_date'], '%Y-%m-%d').date()
        while next_d <= date.today():
            # create expense/income
            db.execute('INSERT INTO expenses (kind,title,amount,category,date,notes,created_at) VALUES (?,?,?,?,?,?,?)',
                       (r['kind'], r['title'], r['amount'], r['category'], next_d.isoformat(), 'recurring', datetime.now().isoformat()))
            created.append(next_d.isoformat())
            # advance
            if r['cadence'] == 'weekly':
                next_d += timedelta(weeks=1)
            else:
                # monthly: naive approach: add 1 month
                m = next_d.month + 1
                y = next_d.year + (m-1)//12
                m = ((m-1)%12) + 1
                day = min(next_d.day, 28)
                next_d = date(y,m,day)
        # write back new next_date
        db.execute('UPDATE recurring SET next_date=? WHERE id=?', (next_d.isoformat(), r['id']))
    db.commit()
    return jsonify({'created_dates': created})

# Settings: monthly budget
@app.route('/api/settings', methods=['GET','POST'])
def api_settings():
    db = get_db()
    if request.method == 'GET':
        rows = db.execute('SELECT * FROM settings').fetchall()
        return jsonify({r['k']: r['v'] for r in rows})
    payload = request.get_json() or {}
    for k,v in payload.items():
        db.execute('INSERT OR REPLACE INTO settings (k,v) VALUES (?,?)', (k,str(v)))
    db.commit()
    return jsonify({'status':'ok'})

# Summary + analytics endpoints
@app.route('/api/summary', methods=['GET'])
def api_summary():
    db = get_db()
    # date range optional: default this month
    year = int(request.args.get('y', date.today().year))
    month = int(request.args.get('m', date.today().month))
    start = date(year, month, 1)
    # end is last day of month
    next_month = start.replace(day=28) + timedelta(days=4)
    end = (next_month - timedelta(days=next_month.day)).isoformat()
    start_s = start.isoformat()
    # total expense/income for month
    rows = db.execute('SELECT kind, SUM(amount) as sum FROM expenses WHERE date >= ? AND date <= ? GROUP BY kind', (start_s, end)).fetchall()
    totals = {'expense':0.0, 'income':0.0}
    for r in rows:
        totals[r['kind']] = r['sum'] or 0.0
    # category breakdown
    cats = db.execute('SELECT category, SUM(amount) as sum FROM expenses WHERE date >= ? AND date <= ? AND kind="expense" GROUP BY category', (start_s,end)).fetchall()
    cat_break = [{ 'category': r['category'] or 'Other', 'amount': r['sum'] or 0.0 } for r in cats]
    # monthly trend (last 6 months)
    trend = []
    for i in range(5, -1, -1):
        d = (start.replace(day=1) - timedelta(days=30*i))
        y,m = d.year, d.month
        s = date(y,m,1).isoformat()
        nm = date(y,m,28) + timedelta(days=4)
        e = (nm - timedelta(days=nm.day)).isoformat()
        ssum = db.execute('SELECT SUM(amount) as s FROM expenses WHERE date >= ? AND date <= ? AND kind="expense"', (s,e)).fetchone()['s'] or 0
        trend.append({'y':y,'m':m,'amount': ssum})
    # budget
    res = db.execute('SELECT v FROM settings WHERE k=?', ('monthly_budget',)).fetchone()
    budget = float(res['v']) if res else 0.0
    return jsonify({'month': f"{year}-{month:02d}", 'totals':totals, 'categories':cat_break, 'trend':trend, 'budget': budget})

# CSV export of filtered expenses
@app.route('/api/export-csv', methods=['GET'])
def api_export_csv():
    # supports same filters as list
    q = request.args.get('q','').strip()
    dfrom = request.args.get('from')
    dto = request.args.get('to')
    category = request.args.get('category','').strip()
    kind = request.args.get('kind','').strip()
    db = get_db()
    sql = 'SELECT * FROM expenses WHERE 1=1'
    params = []
    if q:
        sql += ' AND (title LIKE ? OR notes LIKE ?)'
        params += [f'%{q}%', f'%{q}%']
    if dfrom:
        sql += ' AND date >= ?'; params.append(dfrom)
    if dto:
        sql += ' AND date <= ?'; params.append(dto)
    if category:
        sql += ' AND category = ?'; params.append(category)
    if kind:
        sql += ' AND kind = ?'; params.append(kind)
    sql += ' ORDER BY date DESC'
    rows = db.execute(sql, params).fetchall()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['id','kind','title','amount','category','date','notes','created_at'])
    for r in rows:
        cw.writerow([r['id'], r['kind'], r['title'], r['amount'], r['category'], r['date'], r['notes'] or '', r['created_at']])
    mem = io.BytesIO()
    mem.write(si.getvalue().encode('utf-8'))
    mem.seek(0)
    fname = f"expenses_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return send_file(mem, as_attachment=True, download_name=fname, mimetype='text/csv')

# Import CSV (simple)
@app.route('/api/import-csv', methods=['POST'])
def api_import_csv():
    if 'file' not in request.files:
        return jsonify({'error':'file required'}), 400
    f = request.files['file']
    stream = io.StringIO(f.stream.read().decode('utf-8'))
    cr = csv.DictReader(stream)
    db = get_db()
    inserted = 0
    for row in cr:
        try:
            kind = row.get('kind','expense')
            title = row.get('title') or 'Imported'
            amount = float(row.get('amount') or 0)
            category = row.get('category') or auto_category(title)
            d = row.get('date') or date.today().isoformat()
            notes = row.get('notes','')
            db.execute('INSERT INTO expenses (kind,title,amount,category,date,notes,created_at) VALUES (?,?,?,?,?,?,?)',
                       (kind,title,amount,category,d,notes, datetime.now().isoformat()))
            inserted += 1
        except Exception:
            continue
    db.commit()
    return jsonify({'inserted': inserted})

# Backup / Restore JSON
@app.route('/api/backup-json', methods=['GET'])
def api_backup_json():
    db = get_db()
    rows = db.execute('SELECT * FROM expenses ORDER BY date DESC').fetchall()
    data = [row_to_dict(r) for r in rows]
    mem = io.BytesIO()
    mem.write(json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8'))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name='expenses_backup.json', mimetype='application/json')

@app.route('/api/restore-json', methods=['POST'])
def api_restore_json():
    if 'file' not in request.files:
        return jsonify({'error':'file required'}), 400
    f = request.files['file']
    data = json.load(f.stream)
    db = get_db()
    inserted = 0
    for rec in data:
        try:
            db.execute('INSERT INTO expenses (kind,title,amount,category,date,notes,created_at) VALUES (?,?,?,?,?,?,?)',
                       (rec.get('kind','expense'), rec.get('title','Imported'), float(rec.get('amount') or 0),
                        rec.get('category') or auto_category(rec.get('title','')), rec.get('date') or date.today().isoformat(),
                        rec.get('notes',''), datetime.now().isoformat()))
            inserted += 1
        except Exception:
            continue
    db.commit()
    return jsonify({'inserted': inserted})

# Basic list of categories (distinct)
@app.route('/api/categories', methods=['GET'])
def api_categories():
    db = get_db()
    rows = db.execute('SELECT DISTINCT category FROM expenses').fetchall()
    cats = [r['category'] or 'Other' for r in rows]
    return jsonify(sorted(set(cats)))

# ---------- Run ----------
if __name__ == '__main__':
    app.run(debug=True)
