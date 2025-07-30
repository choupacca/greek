import json, pathlib, io, re, sqlite3, datetime
from collections.abc import Generator
from flask import (
    Flask, render_template, render_template_string,
    abort, request, send_file, g
)
from gtts import gTTS   # pip install gTTS

# ──────────── базовая настройка ────────────
app = Flask(__name__)

BASE_DIR = pathlib.Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CATS     = ["vocab", "grammar", "phrases"]

def load_sections() -> dict:
    sections = {c: [] for c in CATS}
    for cat in CATS:
        for p in (DATA_DIR / cat).glob("*.json"):
            meta = json.loads(p.read_text('utf-8'))
            sections[cat].append({"slug": p.stem, "title": meta["title"]})
    return sections

SECTIONS = load_sections()

# ──────────── страницы словаря ────────────
@app.route("/")
def index():
    return render_template("index.html", sections=SECTIONS)

@app.route("/<slug>")
def table(slug):
    for cat in CATS:
        f = DATA_DIR / cat / f"{slug}.json"
        if f.exists():
            data = json.loads(f.read_text("utf-8"))
            return render_template(
                "table.html",
                title=data["title"],
                headers=data.get("headers"),
                rows=data["entries"],
                sections=SECTIONS,
            )
    abort(404)

# ──────────── on-the-fly TTS (gTTS) ────────────
SAFE_GR = re.compile(r"^[Α-ΩΆ-Ώα-ωά-ώ\s]+$")
AUDIO_CACHE: dict[str, bytes] = {}

def synthesize(text: str) -> bytes:
    buf = io.BytesIO()
    gTTS(text, lang="el", tld="com").write_to_fp(buf)  # женский голос
    return buf.getvalue()

@app.route("/tts")
def tts() -> Generator:
    q = request.args.get("q", "").strip()
    if not q or len(q) > 40 or not SAFE_GR.fullmatch(q):
        abort(400)
    if (mp3 := AUDIO_CACHE.get(q)) is None:
        mp3 = AUDIO_CACHE[q] = synthesize(q)
    return send_file(io.BytesIO(mp3),
                     mimetype="audio/mpeg",
                     download_name=f"{q}.mp3")

# Jinja-фильтр «только греческие символы»
@app.template_filter("is_greek")
def is_greek(text: str) -> bool:
    return bool(SAFE_GR.fullmatch(text.strip()))

# ──────────── суточная статистика уникальных IP (SQLite) ────────────
DB_PATH = BASE_DIR / "hits.db"

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.execute("""CREATE TABLE IF NOT EXISTS hits(
                           date TEXT, ip TEXT, path TEXT,
                           UNIQUE(date, ip, path))""")
    return g.db

@app.before_request
def log_unique_hit() -> None:
    if request.endpoint == "table":
        today = datetime.date.today().isoformat()
        ip    = request.headers.get("X-Forwarded-For", request.remote_addr).split(",")[0]
        path  = request.path
        db = get_db()
        db.execute("INSERT OR IGNORE INTO hits VALUES (?,?,?)",
                   (today, ip, path))
        db.commit()

@app.route("/stats")
def stats():
    db = get_db()
    rows = db.execute("""
        SELECT date, path, COUNT(*) AS uniq
        FROM hits GROUP BY date, path
        ORDER BY date DESC, path
    """).fetchall()
    tmpl = """
    <h1 class="text-2xl font-bold mb-4">Στατιστικά (unique IP)</h1>
    <table class="border-collapse">
      <tr><th class="px-3 py-1 border">Date</th>
          <th class="px-3 py-1 border">Page</th>
          <th class="px-3 py-1 border">Uniq IP</th></tr>
      {% for d,p,c in rows %}
        <tr><td class="px-3 py-1 border">{{ d }}</td>
            <td class="px-3 py-1 border">{{ p }}</td>
            <td class="px-3 py-1 border text-right">{{ c }}</td></tr>
      {% endfor %}
    </table>
    """
    return render_template_string(tmpl, rows=rows)

@app.teardown_appcontext
def close_db(_exc):
    if (db := g.pop("db", None)):
        db.close()

# ──────────── запуск локально ────────────
if __name__ == "__main__":
    app.run(debug=True)