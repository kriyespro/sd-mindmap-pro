import sqlite3
import os
from functools import wraps
from datetime import date, datetime
from flask import Flask, render_template, request, g, make_response, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super-secret-key-for-dev'
DATABASE = 'todo.db'

# Auto-initialize DB on first startup
with app.app_context():
    _db = sqlite3.connect(DATABASE)
    _db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    _db.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    _db.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id   INTEGER  REFERENCES tasks(id) ON DELETE CASCADE,
            author_id   INTEGER  REFERENCES users(id) ON DELETE CASCADE,
            title       TEXT     NOT NULL,
            due_date    TEXT,
            assignee    TEXT,
            is_completed INTEGER  DEFAULT 0
        )
    ''')
    # Try adding author_id to existing DB safely
    try:
        _db.execute('ALTER TABLE tasks ADD COLUMN author_id INTEGER REFERENCES users(id) ON DELETE CASCADE')
    except sqlite3.OperationalError:
        pass # Column already exists
    _db.commit()
    _db.close()


# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response


def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id   INTEGER  REFERENCES tasks(id) ON DELETE CASCADE,
                author_id   INTEGER  REFERENCES users(id) ON DELETE CASCADE,
                title       TEXT     NOT NULL,
                due_date    TEXT,
                assignee    TEXT,
                is_completed INTEGER  DEFAULT 0
            )
        ''')
        try:
            db.execute('ALTER TABLE tasks ADD COLUMN author_id INTEGER REFERENCES users(id) ON DELETE CASCADE')
        except sqlite3.OperationalError:
            pass
        db.commit()


# ── Tree builder ───────────────────────────────────────────────────────────────

def count_all_descendants(node):
    """Recursively count all descendants and how many are done."""
    total, done = 0, 0
    for child in node.get('children', []):
        total += 1
        if child['is_completed']:
            done += 1
        child_total, child_done = count_all_descendants(child)
        total += child_total
        done += child_done
    return total, done


def build_task_tree(tasks, parent_id=None):
    tree = []
    siblings = [task for task in tasks if task['parent_id'] == parent_id]
    siblings.sort(key=lambda t: t['id'], reverse=(parent_id is None))

    for task in siblings:
        node = dict(task)
        node['due_state'] = 'none'
        if node.get('due_date'):
            try:
                due_date = datetime.strptime(node['due_date'], '%Y-%m-%d').date()
                today = date.today()
                if due_date < today:
                    node['due_state'] = 'overdue'
                elif due_date == today:
                    node['due_state'] = 'today'
                else:
                    node['due_state'] = 'upcoming'
            except ValueError:
                node['due_state'] = 'none'
        node['children'] = build_task_tree(tasks, task['id'])
        sub_total, sub_done = count_all_descendants(node)
        node['subtask_total'] = sub_total
        node['subtask_done'] = sub_done
        node['percent'] = round((sub_done / sub_total) * 100) if sub_total > 0 else (100 if node['is_completed'] else 0)
        tree.append(node)
    return tree


# Shared CTE: tasks the current user may see (authored, assigned, or in same subtree / ancestor chain).
_VISIBILITY_CTE = '''
WITH RECURSIVE
  base AS (
    SELECT id FROM tasks WHERE author_id = ? OR assignee = ?
  ),
  descendants AS (
    SELECT id, parent_id FROM tasks WHERE id IN (SELECT id FROM base)
    UNION
    SELECT t.id, t.parent_id FROM tasks t INNER JOIN descendants d ON t.parent_id = d.id
  ),
  ancestors AS (
    SELECT id, parent_id FROM tasks WHERE id IN (SELECT id FROM base)
    UNION
    SELECT t.id, t.parent_id FROM tasks t INNER JOIN ancestors a ON t.id = a.parent_id
  ),
  visible AS (
    SELECT id FROM descendants UNION SELECT id FROM ancestors
  )
'''


def get_visible_tasks(db):
    if not getattr(g, 'user', None):
        return []
    query = _VISIBILITY_CTE + 'SELECT * FROM tasks WHERE id IN (SELECT id FROM visible) ORDER BY id'
    return db.execute(query, (g.user['id'], g.user['username'])).fetchall()


def is_task_visible(db, task_id):
    """True if this task is in the current user's visible set (same rules as the task tree)."""
    if not getattr(g, 'user', None):
        return False
    row = db.execute(
        _VISIBILITY_CTE
        + 'SELECT 1 FROM tasks WHERE id = ? AND id IN (SELECT id FROM visible) LIMIT 1',
        (g.user['id'], g.user['username'], task_id),
    ).fetchone()
    return row is not None


def get_stats(db):
    rows = get_visible_tasks(db)
    roots = [r for r in rows if r['parent_id'] is None]
    total = len(roots)
    done  = sum(1 for r in roots if r['is_completed'])
    return total, done


# ── Auth & Decorators ──────────────────────────────────────────────────────────

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        db = get_db()
        g.user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/signup', methods=('GET', 'POST'))
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        error = None

        if not username:
            error = 'Username is required.'
        elif not password:
            error = 'Password is required.'

        if error is None:
            try:
                db.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                           (username, generate_password_hash(password)))
                db.commit()
                # Auto login
                user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
                session.clear()
                session['user_id'] = user['id']
                return redirect(url_for('index'))
            except sqlite3.IntegrityError:
                error = f"User {username} is already registered."
        flash(error)
    return render_template('auth.html', is_signup=True)

@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        error = None
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user is None:
            error = 'Incorrect username.'
        elif not check_password_hash(user['password_hash'], password):
            error = 'Incorrect password.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            return redirect(url_for('index'))
        flash(error)
    return render_template('auth.html', is_signup=False)

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    db = get_db()
    all_tasks  = get_visible_tasks(db)
    task_tree  = build_task_tree(all_tasks)
    total_main, done_main = get_stats(db)
    
    # Fetch unread notifications for current user
    notifications = db.execute(
        'SELECT * FROM notifications WHERE user_id = ? AND is_read = 0 ORDER BY created_at DESC',
        (g.user['id'],)
    ).fetchall()
    
    return render_template(
        'index.html',
        task_tree=task_tree,
        total_main=total_main,
        done_main=done_main,
        notifications=notifications,
        user=g.user
    )


def _tree_response():
    """Return the task-tree partial HTML, plus HX-Trigger to refresh stats."""
    db = get_db()
    all_tasks = get_visible_tasks(db)
    task_tree = build_task_tree(all_tasks)
    html = render_template('task_tree.html', task_tree=task_tree)
    resp = make_response(html)
    resp.headers['HX-Trigger'] = 'updateStats'
    return resp


@app.route('/stats')
@login_required
def stats():
    db = get_db()
    total_main, done_main = get_stats(db)
    return render_template('stats.html', total_main=total_main, done_main=done_main)


@app.route('/tasks', methods=['POST'])
@login_required
def add_task():
    db         = get_db()
    title      = request.form.get('title', '').strip()
    due_date   = request.form.get('due_date') or None
    assignee   = request.form.get('assignee', '').strip() or None
    parent_id  = request.form.get('parent_id') or None

    if not title:
        return 'Title is required', 400

    if parent_id:
        try:
            pid = int(parent_id)
        except (TypeError, ValueError):
            return 'Invalid parent task', 400
        if not is_task_visible(db, pid):
            return 'Parent task not found', 404
        parent_id = pid
    else:
        parent_id = None

    db.execute(
        'INSERT INTO tasks (title, due_date, assignee, parent_id, author_id) VALUES (?,?,?,?,?)',
        (title, due_date, assignee, parent_id, g.user['id'])
    )
    
    # Notification logic on creation if assigned to someone else
    if assignee and assignee != g.user['username']:
        assigned_user = db.execute('SELECT id FROM users WHERE username = ?', (assignee,)).fetchone()
        if assigned_user:
            msg = f"{g.user['username']} assigned you to task '{title}'"
            db.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (assigned_user['id'], msg))

    db.commit()
    return _tree_response()


@app.route('/tasks/<int:task_id>/status', methods=['POST'])
@login_required
def toggle_status(task_id):
    db   = get_db()
    if not is_task_visible(db, task_id):
        return 'Not found', 404
    row  = db.execute('SELECT is_completed FROM tasks WHERE id=?', (task_id,)).fetchone()
    if row is None:
        return 'Not found', 404
    db.execute('UPDATE tasks SET is_completed=? WHERE id=?',
               (0 if row['is_completed'] else 1, task_id))
    db.commit()
    return _tree_response()


@app.route('/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    db = get_db()
    if not is_task_visible(db, task_id):
        return 'Not found', 404
    db.execute('DELETE FROM tasks WHERE id=?', (task_id,))
    db.commit()
    return _tree_response()


@app.route('/tasks/<int:task_id>/title', methods=['POST'])
@login_required
def rename_task(task_id):
    db = get_db()
    if not is_task_visible(db, task_id):
        return 'Not found', 404
    title = request.form.get('title', '').strip()
    if not title:
        return 'Title is required', 400
    db.execute('UPDATE tasks SET title=? WHERE id=?', (title, task_id))
    db.commit()
    return _tree_response()


@app.route('/tasks/<int:task_id>/meta', methods=['POST'])
@login_required
def update_task_meta(task_id):
    db = get_db()
    if not is_task_visible(db, task_id):
        return 'Not found', 404

    old_task = db.execute('SELECT assignee, title FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not old_task:
        return 'Not found', 404

    due_date_raw = request.form.get('due_date', '').strip()
    assignee_raw = request.form.get('assignee', '').strip()

    due_date = due_date_raw or None
    assignee = assignee_raw or None

    if due_date is not None:
        try:
            datetime.strptime(due_date, '%Y-%m-%d')
        except ValueError:
            return 'Invalid due date format', 400

    db.execute(
        'UPDATE tasks SET due_date=?, assignee=? WHERE id=?',
        (due_date, assignee, task_id)
    )
    
    # Notification logic: if assignee changed to someone else
    if assignee and assignee != g.user['username'] and assignee != old_task['assignee']:
        assigned_user = db.execute('SELECT id FROM users WHERE username = ?', (assignee,)).fetchone()
        if assigned_user:
            msg = f"{g.user['username']} assigned you to task '{old_task['title']}'"
            db.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (assigned_user['id'], msg))

    db.commit()
    return _tree_response()

@app.route('/notifications/read/<int:n_id>', methods=['POST'])
@login_required
def read_notification(n_id):
    db = get_db()
    db.execute('UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?', (n_id, g.user['id']))
    db.commit()
    return '', 200 # HTMX swap will remove the element if we return empty html or we can return updated bell



# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
