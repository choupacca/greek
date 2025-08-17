import json, pathlib, io, re, sqlite3, datetime
from collections import defaultdict
from collections.abc import Generator
from flask import (
    Flask, render_template, render_template_string,
    request, send_file, abort, g, send_from_directory
)
from gtts import gTTS                    # pip install gTTS
import matplotlib
matplotlib.use("Agg")                   # headless backend
import matplotlib.pyplot as plt

# ──────────── базовая конфигурация ────────────
app = Flask(__name__)

BASE_DIR = pathlib.Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CATS     = ["vocab", "grammar", "phrases"]

def load_sections() -> dict:
    sections = {c: [] for c in CATS}
    for cat in CATS:
        items = []
        for p in (DATA_DIR / cat).glob("*.json"):
            meta = json.loads(p.read_text('utf-8'))
            items.append({"slug": p.stem, "title": meta["title"]})
        sections[cat] = sorted(items, key=lambda x: x["title"].lower())
    return sections

SECTIONS = load_sections()
VALID_SLUGS = {item["slug"] for items in SECTIONS.values() for item in items}

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
                title    = data["title"],
                headers  = data.get("headers"),
                rows     = data["entries"],
                sections = SECTIONS,
                cat      = cat
            )
    abort(404)

# ──────────── on-the-fly TTS ────────────
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

# ──────────── SQLite: уникальные IP в сутки ────────────
DB_PATH = BASE_DIR / "hits.db"

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.execute("""CREATE TABLE IF NOT EXISTS hits(
                          date TEXT,
                          ip   TEXT,
                          path TEXT,
                          UNIQUE(date, ip, path)
                       )""")
    return g.db

@app.before_request
def log_hit():
    if request.endpoint == "table":
        slug = request.view_args.get("slug")
        if slug not in VALID_SLUGS:      # фильтруем мусорные URL
            return
        today = datetime.date.today().isoformat()
        ip    = request.headers.get("X-Forwarded-For",
                                   request.remote_addr).split(",")[0]
        db = get_db()
        db.execute("INSERT OR IGNORE INTO hits VALUES (?,?,?)",
                   (today, ip, slug))
        db.commit()

@app.teardown_appcontext
def close_db(_exc):
    if (db := g.pop("db", None)):
        db.close()

# ──────────── PNG-график статистики (только Total) ────────────
@app.route("/stats.png")
def stats_png():
    db = get_db()
    total_rows = db.execute("""SELECT date, COUNT(DISTINCT ip) AS c
                               FROM hits
                               GROUP BY date
                               ORDER BY date""").fetchall()
    if not total_rows:
        # чтобы было что показать
        total_rows = [(datetime.date.today().isoformat(), 0)]

    dates = [d for d, _ in total_rows]
    x = [datetime.datetime.fromisoformat(d) for d in dates]
    y = [c for _, c in total_rows]

    fig, ax = plt.subplots(figsize=(8, 5), dpi=160)
    ax.plot(x, y, marker="o", color="black", linewidth=4)
    ax.set_title("Уникальные IP / день")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Total")
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate(rotation=30)

    buf = io.BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

# ──────────── HTML-страница статистики (таблица с Total) ────────────
@app.route("/stats")
def stats():
    db = get_db()
    rows = db.execute("""SELECT date, COUNT(DISTINCT ip) AS total
                         FROM hits
                         GROUP BY date
                         ORDER BY date DESC""").fetchall()

    html = """
    <h1 class="text-2xl font-bold mb-4">Στατιστικά (unique IP)</h1>
    <img src="/stats.png" alt="graph" style="max-width:100%;height:auto">
    <table class="mt-6 border-collapse">
      <thead>
        <tr>
          <th class="border px-2">Date</th>
          <th class="border px-2">Total</th>
        </tr>
      </thead>
      <tbody>
      {% for d, t in rows %}
        <tr>
          <td class="border px-2">{{ d }}</td>
          <td class="border px-2 text-right">{{ t }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    """
    # rows приходит как list[tuple] (date, total)
    rows_tuples = [(d, t) for d, t in rows]
    return render_template_string(html, rows=rows_tuples)


@app.route("/favicon.ico")
def favicon_ico():
    return send_from_directory(BASE_DIR / "static", "favicon.ico",
                               mimetype="image/x-icon")


@app.route("/apple-touch-icon.png")
def apple_touch_icon():
    return send_from_directory(BASE_DIR / "static", "apple-touch-icon.png",
                               mimetype="image/png")


# ──────────── локальный запуск ────────────
if __name__ == "__main__":
    app.run(debug=True)