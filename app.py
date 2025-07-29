import json, pathlib
from flask import Flask, render_template, abort

app       = Flask(__name__)
BASE_DIR  = pathlib.Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
CATS      = ["vocab", "grammar"]          # ← две категории

def load_sections() -> dict:
    """Сканирует data/vocab и data/grammar → строит меню."""
    sections = {c: [] for c in CATS}
    for cat in CATS:
        for p in (DATA_DIR / cat).glob("*.json"):
            meta = json.loads(p.read_text(encoding="utf-8"))
            sections[cat].append({"slug": p.stem, "title": meta["title"]})
    return sections

SECTIONS = load_sections()

@app.route("/")
def index():
    return render_template("index.html", sections=SECTIONS)

@app.route("/<slug>")
def table(slug):
    # ищем файл в каждой категории
    for cat in CATS:
        f = DATA_DIR / cat / f"{slug}.json"
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            return render_template(
                "table.html",
                title=data["title"],
                headers=data.get("headers"),
                rows=data["entries"],
                sections=SECTIONS,
            )
    abort(404)