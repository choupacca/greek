from flask import Flask, render_template, abort
import json, pathlib

app = Flask(__name__)
BASE = pathlib.Path(__file__).parent
DATA_DIR = BASE / "data" / "vocab"
SECTIONS = [
    {"slug": p.stem, "title": json.loads(p.read_text("utf-8"))["title"]}
    for p in DATA_DIR.glob("*.json")
]

@app.route("/")
def index():
    return render_template("index.html", sections=SECTIONS)

@app.route("/<slug>")
def lesson(slug):
    file = DATA_DIR / f"{slug}.json"
    if not file.exists():
        abort(404)
    data = json.loads(file.read_text("utf-8"))
    return render_template("table.html", title=data["title"],
                           rows=data["entries"], sections=SECTIONS)