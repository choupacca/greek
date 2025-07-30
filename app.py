import json, pathlib, io, re, sqlite3, datetime
from collections.abc import Generator
from collections import defaultdict
from flask import (
    Flask, render_template, render_template_string,
    abort, request, send_file, g
)
from gtts import gTTS               # pip install gTTS

# ────── базовая настройка ──────
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

# ────── страницы словаря ──────
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
                title    = data["title"],
                headers  = data.get("headers"),
                rows     = data["entries"],
                sections = SECTIONS,
            )
    abort(404)

# ────── on-the-fly TTS ──────
SAFE_GR = re.compile(r"^[Α-ΩΆ-Ώα-ωά-ώ\s]+$")
AUDIO_CACHE: dict[str, bytes] = {}

def synthesize(text: str) -> bytes:
    buf = io.BytesIO()
    gTTS(text, lang="el", tld="com").write_to_fp(buf)   # женский голос
    return buf.getvalue()

@app.route("/tts")
def tts() -> Generator:
    q = request.args.get("q", "").strip()
    if not q or len(q) > 40 or not SAFE_GR.fullmatch(q):
        abort(400)
    mp3 = AUDIO_CACHE.get(q) or synthesize(q)
    AUDIO_CACHE[q] = mp3
    return send_file(io.BytesIO(mp3),
                     mimetype="audio/mpeg",
                     download_name=f"{q}.mp3")

@app.template_filter("is_greek")
def is_greek(text: str) -> bool:
    return bool(SAFE_GR.fullmatch(text.strip()))

# ────── SQLite хиты ──────
DB_PATH = BASE_DIR / "hits.db"

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.execute("""CREATE TABLE IF NOT EXISTS hits(
                          date TEXT, ip TEXT, path TEXT,
                          UNIQUE(date, ip, path))""")
    return g.db

@app.before_request
def log_hit():
    if request.endpoint == "table":
        today = datetime.date.today().isoformat()
        ip    = request.headers.get("X-Forwarded-For",
                                    request.remote_addr).split(",")[0]
        path  = request.path
        db = get_db()
        db.execute("INSERT OR IGNORE INTO hits VALUES (?,?,?)",
                   (today, ip, path))
        db.commit()

@app.teardown_appcontext
def close_db(_exc):
    if (db := g.pop("db", None)):
        db.close()

# ────── PNG-график ──────
import matplotlib
matplotlib.use("Agg")              # headless backend
import matplotlib.pyplot as plt

@app.route("/stats.png")
def stats_png():
    db   = get_db()

    # ── ① почасовая разбивка по каждой странице (остается как было)
    rows = db.execute("""SELECT date, path, COUNT(*) AS c
                         FROM hits
                         GROUP BY date, path
                         ORDER BY date, path""").fetchall()

    # ── ② Суммарно: уникальные IP по дате (DISTINCT ip)
    total_rows = db.execute("""SELECT date, COUNT(DISTINCT ip) AS c
                               FROM hits
                               GROUP BY date
                               ORDER BY date""").fetchall()
    total_map = {d: c for d, c in total_rows}

    # ── ③ Подготовка данных
    from collections import defaultdict
    data = defaultdict(dict)                  # path → {date: c}
    for d, p, c in rows:
        data[p][d] = c

    dates = sorted({d for d, _, _ in rows}) or [datetime.date.today().isoformat()]
    x = [datetime.datetime.fromisoformat(d) for d in dates]

    # ── ④ Рисуем
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    for path, series in data.items():
        y = [series.get(d, 0) for d in dates]
        ax.plot(x, y, marker="o", label=path, linewidth=1)

    # ── ⑤ Линия Total (жирная, черная)
    y_total = [total_map.get(d, 0) for d in dates]
    ax.plot(x, y_total, marker="o", linewidth=3, color="black", label="Total")

    ax.set_title("Уникальные IP / день")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Uniq IP")
    ax.legend(fontsize=8)
    fig.autofmt_xdate()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

# ────── HTML-страница стат-таблица + график ──────
@app.route("/stats")
def stats():
    db = get_db()
    rows = db.execute("""SELECT date, path, COUNT(*) c
                         FROM hits GROUP BY date, path
                         ORDER BY date DESC, path""").fetchall()
    html = """
    <h1 class="text-2xl font-bold mb-4">Στατιστικά (unique IP)</h1>
    <img src="/stats.png" alt="график">
    <table class="mt-6 border-collapse">
      <tr><th class="border px-2">Date</th>
          <th class="border px-2">Page</th>
          <th class="border px-2">Uniq</th></tr>
      {% for d,p,c in rows %}
        <tr><td class="border px-2">{{ d }}</td>
            <td class="border px-2">{{ p }}</td>
            <td class="border px-2 text-right">{{ c }}</td></tr>
      {% endfor %}
    </table>
    """
    return render_template_string(html, rows=rows)

# ────── локальный запуск ──────
if __name__ == "__main__":
    app.run(debug=True)