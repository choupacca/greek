import json, pathlib, re, io
from flask import Flask, render_template, abort, request, send_file
from gtts import gTTS                       # pip install gTTS

app = Flask(__name__)

# ────── данные и меню ──────
BASE_DIR = pathlib.Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CATS     = ["vocab", "grammar", "phrases"]

def load_sections():
    sections = {c: [] for c in CATS}
    for cat in CATS:
        for p in (DATA_DIR / cat).glob("*.json"):
            meta = json.loads(p.read_text('utf-8'))
            sections[cat].append({"slug": p.stem, "title": meta["title"]})
    return sections

SECTIONS = load_sections()

# ────── страницы ──────
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
SAFE_GR_REGEX = re.compile(r"^[Α-ΩΆ-Ώα-ωά-ώ\s]+$")
AUDIO_CACHE: dict[str, bytes] = {}

def synthesize(text: str) -> bytes:
    buf = io.BytesIO()
    gTTS(text, lang="el", tld="com").write_to_fp(buf)   # «com» = женский голос
    return buf.getvalue()

@app.route("/tts")
def tts():
    q = request.args.get("q", "").strip()
    if not q or len(q) > 40 or not SAFE_GR_REGEX.fullmatch(q):
        abort(400)

    mp3 = AUDIO_CACHE.get(q)
    if mp3 is None:
        mp3 = synthesize(q)
        AUDIO_CACHE[q] = mp3
    return send_file(io.BytesIO(mp3),
                     mimetype="audio/mpeg",
                     download_name=f"{q}.mp3")

# ────── фильтр Jinja: только греч. текст ──────
@app.template_filter("is_greek")
def is_greek(text: str) -> bool:
    return bool(SAFE_GR_REGEX.fullmatch(text.strip()))