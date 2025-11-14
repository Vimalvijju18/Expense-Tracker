# Expense Tracker (Flask + JSON)

Simple Expense Tracker to add/view/delete expenses and view category-wise summary.

## Files
- app.py — Flask backend
- expenses.json — data file (JSON)
- templates/index.html — frontend
- static/style.css, static/app.js — assets

## Run locally
1. Create venv:
   python -m venv venv
   source venv/bin/activate    # Windows: venv\Scripts\activate
2. Install:
   pip install -r requirements.txt
3. Start app:
   python app.py
4. Open http://127.0.0.1:5000

## Resume bullets (pick one)
- Built an **Expense Tracker** (Flask, JavaScript, Chart.js) with JSON persistence; implemented CRUD operations and dynamic category charts.
- Developed a lightweight financial assistant that records expenses, shows totals and category distributions, and provides a user-friendly web UI.

## 30–60s demo script (copy-paste)
1. Open the app home — point to the Add Expense form.  
2. Add an expense (title, amount, category) — show it appears in the table immediately.  
3. Show the Summary: total and the pie chart by category.  
4. Delete an expense to show CRUD works.  
5. Explain: backend is Flask storing data in a JSON file (easy to migrate to SQLite), frontend uses Chart.js to visualize categories.

## Next steps (if asked)
- Migrate JSON to SQLite/Postgres
- Add user authentication and per-user data
- Add monthly/weekly filters and CSV export
- Add mobile responsive improvements and deployment (Heroku / Railway / Render)
