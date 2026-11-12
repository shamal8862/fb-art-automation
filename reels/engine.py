"""
Doodlore Reels engine: one narrated, fact-checked, public-domain-art story Reel per run.

Pipeline: topic bank -> Wikipedia article -> Gemini script (+caption) -> Gemini fact QA against the article
-> Wikimedia Commons public-domain art per scene (+Gemini vision safety/fit check) -> storybook render
(cream paper, framed art, logo, word-synced captions, British storyteller voice) -> Facebook Reel.

Keep this file pure ASCII. Non-ASCII characters are built with chr().
"""
import os
import io
import re
import json
import time
import wave
import random
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime, timezone

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
WORK = HERE / "work"
OUT = HERE / "output"
HISTORY = HERE / "history.json"
TOPICS = HERE / "topics.json"
UA = {"User-Agent": "DoodloreBot/1.0 (https://github.com/shamal8862; automated art reels) python-requests/2.32"}

W, H, FPS = 1080, 1920, 30
PAPER = (243, 234, 216)
INK = (43, 29, 20)
ACCENT = (178, 58, 38)
VOICE = os.getenv("REEL_VOICE", "en-GB-RyanNeural")
CTA_TEXT = "Follow Doodlore for the stories behind the stories."
CTA_LINE = "Myths, legends & lost history"
EMOJI = {"speech": chr(0x1F4AC), "palette": chr(0x1F3A8)}


# =============================================================================== gemini
def _keys():
    raw = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
    return [k.strip().strip("'\"") for k in re.split(r"[,\n]", raw) if k.strip().strip("'\"")]


MODELS = [m.strip() for m in os.getenv("GEMINI_MODELS", "gemini-3.5-flash,gemini-3.8-flash,gemini-3.5-flash-lite").split(",") if m.strip()]


def gemini_json(prompt: str, images: list = None, temperature: float = 0.6) -> dict:
    from google import genai
    from google.genai import types
    keys = _keys()
    if not keys:
        raise RuntimeError("No GEMINI_API_KEYS configured")
    last = None
    for model in MODELS:
        for key in random.sample(keys, len(keys)):
            try:
                client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=120000))
                t0 = time.time()
                contents = [prompt] + [types.Part.from_bytes(data=b, mime_type="image/jpeg") for b in (images or [])]
                r = client.models.generate_content(model=model, contents=contents, config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=temperature))
                print(f"[Gemini] {model} answered in {time.time() - t0:.0f}s")
                text = (r.text or "").strip()
                text = re.sub(r"^```(json)?|```$", "", text).strip()
                return json.loads(text)
            except Exception as e:
                last = e
                print(f"[Gemini] {model} failed: {str(e)[:90]}")
                time.sleep(1)
    raise RuntimeError(f"Gemini failed on all models/keys: {str(last)[:200]}")


# =============================================================================== history / topics
def load_history() -> list:
    if HISTORY.exists():
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    return []


def save_history(items: list):
    HISTORY.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")


def next_topics(history: list, n: int = 4) -> list:
    done = {h["title"] for h in history}
    topics = json.loads(TOPICS.read_text(encoding="utf-8"))
    return [t for t in topics if t["title"] not in done][:n]


def refill_topics_if_low(history: list, minimum: int = 40):
    """When the bank runs low, Gemini proposes new topics; only real Wikipedia articles are added."""
    topics = json.loads(TOPICS.read_text(encoding="utf-8"))
    done = {h["title"] for h in history}
    unused = [t for t in topics if t["title"] not in done]
    if len(unused) >= minimum:
        return
    known = [t["title"] for t in topics]
    data = gemini_json(
        "Suggest 60 NEW story topics for a family-friendly Facebook page that tells 45-second illustrated stories: "
        "myths and folklore from any culture, strange-but-true history before 1930, and origins of customs, words and "
        "everyday objects. Each must be the EXACT title of an existing English Wikipedia article and must have good "
        "public-domain artwork available (paintings, engravings, old photographs). Avoid these existing titles: "
        + "; ".join(known[-400:]) + '. Return JSON: {"topics": [{"title": "...", "pillar": "myth|history|origin"}]}')
    proposed = [t for t in data.get("topics", []) if t.get("title") and t["title"] not in known]
    valid = []
    for i in range(0, len(proposed), 40):
        batch = proposed[i:i + 40]
        r = requests.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
            "action": "query", "format": "json", "redirects": 1, "prop": "pageprops", "ppprop": "disambiguation",
            "titles": "|".join(t["title"] for t in batch)}).json().get("query", {})
        pages = {p["title"]: p for p in r.get("pages", {}).values()}
        for t in batch:
            p = pages.get(t["title"])
            if p and "missing" not in p and "disambiguation" not in (p.get("pageprops") or {}):
                valid.append({"title": t["title"], "pillar": t.get("pillar", "myth")})
    topics += valid
    TOPICS.write_text(json.dumps(topics, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[Topics] Bank was low ({len(unused)} unused); added {len(valid)} validated topics.")


# =============================================================================== wikipedia
def wiki_article(title: str) -> dict:
    r = requests.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "format": "json", "redirects": 1, "prop": "extracts|info", "explaintext": 1,
        "inprop": "url", "titles": title}).json()
    page = next(iter(r["query"]["pages"].values()))
    text = page.get("extract", "")
    text = re.split(r"\n== (See also|References|Notes|Further reading|External links|Bibliography) ==", text)[0]
    return {"title": page.get("title", title), "url": page.get("fullurl", ""), "text": text[:12000]}


# =============================================================================== script + QA
WRITER_PROMPT = """You are the head writer for DOODLORE, a Facebook page of 45-second narrated storybook Reels about
myths, folklore, strange history and the origins of everyday things. Tone: a warm, curious British storyteller.
Audience: adults in the US, UK, Canada and Australia. Family-friendly: no gore, no sexual content.

Write ONE Reel about: "{title}" (pillar: {pillar}).

GROUND TRUTH (the ONLY facts you may use; this is the Wikipedia article):
<<<SOURCE
{source}
SOURCE>>>

RULES
- Every fact must be supported by the source. If the source says a detail is disputed, uncertain or legendary,
  say so ("according to legend", "historians still debate").
- Structure: a scroll-stopping hook, a story with a clear arc, and a satisfying twist or reveal near the end.
- Exactly 6 scenes. Scene 1 is the hook (one short sentence). Each other scene: 1-2 complete sentences.
- Total narration 105-135 words. Plain spoken English, no lists, no emojis, no hashtags in scenes.
- Do NOT include a call to action; it is added automatically.
- For each scene give "art_query": a short Wikimedia Commons search (3-6 words) for a PUBLIC-DOMAIN artwork,
  engraving, illustration, museum object or pre-1930 photograph that shows that scene's subject. Name the subject
  plainly plus a medium word, e.g. "Medusa painting", "Thor hammer illustration", "Strasbourg engraving 16th century".
  Also give "art_fallback": a broader search for the same scene.
- Caption: "caption_title" (one punchy line, max 12 words), "caption_body" (2-3 short paragraphs, 70-120 words total,
  natural search keywords, no hashtags), "question" (one engaging comment question), "hashtags": exactly 5, lowercase
  letters a-z only (no digits, no underscores).

Return JSON:
{{"scenes": [{{"text": "...", "art_query": "...", "art_fallback": "..."}}],
  "caption_title": "...", "caption_body": "...", "question": "...", "hashtags": ["#a", "#b", "#c", "#d", "#e"]}}
{feedback}"""

QA_PROMPT = """You are a strict fact-checker. Compare EVERY sentence of the NARRATION and CAPTION against the SOURCE.
A sentence passes only if the source supports it (paraphrase is fine). Disputed or legendary details must be framed as
such. Also fail anything not family-friendly or any sentence that is cut off / incomplete.

SOURCE:
<<<
{source}
>>>

NARRATION:
{narration}

CAPTION:
{caption}

Return JSON: {{"pass": true/false, "problems": ["sentence -> what is wrong", ...]}}"""


def write_script(topic: dict, article: dict) -> dict:
    feedback = ""
    for attempt in range(2):
        data = gemini_json(WRITER_PROMPT.format(title=topic["title"], pillar=topic["pillar"],
                                                source=article["text"], feedback=feedback), temperature=0.8)
        scenes = [s for s in data.get("scenes", []) if s.get("text")]
        problems = []
        if len(scenes) != 6:
            problems.append(f"needs exactly 6 scenes, got {len(scenes)}")
        words = sum(len(s["text"].split()) for s in scenes)
        if not 90 <= words <= 150:
            problems.append(f"narration is {words} words; needs 105-135")
        for s in scenes:
            if not s["text"].strip().endswith((".", "!", "?", "\"")):
                problems.append(f"incomplete sentence: {s['text'][:60]}")
        if not problems:
            narration = "\n".join(s["text"] for s in scenes)
            caption = data.get("caption_title", "") + "\n" + data.get("caption_body", "")
            qa = gemini_json(QA_PROMPT.format(source=article["text"], narration=narration, caption=caption), temperature=0.1)
            if qa.get("pass"):
                data["scenes"] = scenes
                return data
            problems = qa.get("problems", ["failed fact check"])
        print(f"[Writer] Attempt {attempt + 1} rejected: {problems[:4]}")
        feedback = "\nYOUR PREVIOUS DRAFT WAS REJECTED. Fix these problems:\n- " + "\n- ".join(map(str, problems[:8]))
    raise ValueError("script failed fact-check twice")


# =============================================================================== art
ALLOWED_LICENSE = re.compile(r"public domain|^pd|cc0|^cc[- ]by(-sa)?([- ][\d.]+)?$", re.I)
BLOCKED_LICENSE = re.compile(r"\b(nc|nd)\b|non-?commercial|no ?deriv", re.I)
BLOCKED_TITLE = re.compile(r"logo|map\b|maps\b|diagram|chart|graph|coat[ _]of[ _]arms|signature|icon|seal[ _]of|"
                           r"emblem|screenshot|flag[ _]of|stamp|banknote|\.svg|\.gif|\.tif|\.pdf|\.djvu", re.I)


def _strip(v: str) -> str:
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", "", v or ""))).strip()


def commons_search(query: str, limit: int = 12) -> list:
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": 960})
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for p in sorted(pages.values(), key=lambda x: x.get("index", 99)):
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}
        lic = _strip((meta.get("LicenseShortName") or {}).get("value", ""))
        if ii.get("mime") not in ("image/jpeg", "image/png") or BLOCKED_TITLE.search(p["title"]):
            continue
        if not ALLOWED_LICENSE.search(lic) or BLOCKED_LICENSE.search(lic):
            continue
        if ii.get("width", 0) < 700 or ii.get("height", 0) < 500:
            continue
        raw_name = (meta.get("ObjectName") or {}).get("value", "")
        m = re.search(r'en:"([^"]+)"', raw_name)
        name = (m.group(1) if m else _strip(raw_name)) if "QS:" not in _strip(raw_name) or m else ""
        if not name or len(name) > 90:
            name = re.sub(r"\.\w+$", "", p["title"][5:]).replace("_", " ")
        name = re.sub(r"\s*[-,(]?\s*(RP-[A-Z]-[\w-]+|W\d{3,}.*|\d{4,}\.\d+.*)$", "", name).strip(" -,")
        artist = _strip((meta.get("Artist") or {}).get("value", ""))[:60] or "Unknown artist"
        out.append({"title": p["title"], "url": ii.get("thumburl") or ii.get("url"), "license": lic,
                    "credit": f"{name[:80]} ({artist}, {lic})"})
    return out


def _download(url: str) -> bytes:
    for attempt in range(4):
        r = requests.get(url, headers=UA, timeout=60)
        if r.status_code == 200 and "image" in (r.headers.get("content-type") or ""):
            return r.content
        wait = int(r.headers.get("retry-after") or 10) + 3
        print(f"[Art] HTTP {r.status_code}, waiting {wait}s")
        time.sleep(min(wait, 90))
    raise RuntimeError(f"download failed: {url[:80]}")


def pick_art(scene_text: str, queries: list, used: set) -> dict:
    """Searches Commons, downloads up to 4 candidates, and lets Gemini vision pick the safest best fit."""
    cands = []
    for q in queries:
        if not q:
            continue
        try:
            for c in commons_search(q):
                if c["title"] not in used and all(c["title"] != x["title"] for x in cands):
                    cands.append(c)
        except Exception as e:
            print(f"[Art] search failed '{q}': {e}")
        time.sleep(1)
        if len(cands) >= 4:
            break
    cands = cands[:4]
    imgs = []
    for c in cands:
        try:
            raw = _download(c["url"])
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            c["image"] = im
            buf = io.BytesIO()
            im.copy().resize((min(im.width, 640), int(im.height * min(im.width, 640) / im.width))).save(buf, "JPEG", quality=80)
            imgs.append(buf.getvalue())
        except Exception as e:
            print(f"[Art] skip {c['title'][:50]}: {e}")
            c["image"] = None
        time.sleep(1.5)
    cands = [c for c in cands if c.get("image") is not None]
    imgs = imgs[:len(cands)]
    if not cands:
        return {}
    verdict = gemini_json(
        f"You are choosing artwork for one scene of a family-friendly storybook Reel. Scene narration: \"{scene_text}\".\n"
        f"There are {len(cands)} candidate images, in order (index 0..{len(cands) - 1}). For each, decide:\n"
        "- safe: FALSE if ANY genitals are visible, ANY female nipples are visible, there is blood, open wounds, torture or "
        "graphic violence, or a corpse. Classical figures are fine only when draped so these areas are covered. Be strict: this "
        "goes on Facebook, whose automatic filters do not exempt art.\n"
        "- is_artwork_or_photo: a clear painting, engraving, illustration, sculpture or photograph (not a map, chart, text "
        "page, logo, diagram, or a barely legible fragment).\n"
        "- fit: 0-10, how clearly it illustrates the scene for a viewer scrolling on a phone.\nReturn JSON: "
        '{"images": [{"index": 0, "safe": true, "is_artwork_or_photo": true, "fit": 7}], "best": 0}', images=imgs, temperature=0.1)
    good = [v for v in verdict.get("images", []) if v.get("safe") is True and v.get("is_artwork_or_photo") and v.get("fit", 0) >= 6
            and 0 <= v.get("index", -1) < len(cands)]
    if not good:
        return {}
    best = max(good, key=lambda v: v["fit"])
    return cands[best["index"]]


# =============================================================================== audio
def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def ff(*args):
    subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", *args], check=True)


_SPOKEN = [(re.compile(r"\bU\.S\.A?\.?(?![A-Za-z])"), "United States"), (re.compile(r"\bUSA?\b"), "United States"),
           (re.compile(r"\bU\.K\.(?![A-Za-z])"), "UK"), (re.compile(r"\bB\.C\.(?![A-Za-z])"), "B.C."),
           (re.compile(r"\bA\.D\.(?![A-Za-z])"), "A.D.")]


def speakable(t: str) -> str:
    for p, s in _SPOKEN:
        t = p.sub(s, t)
    return t


async def _tts(text, path):
    import edge_tts
    try:
        comm = edge_tts.Communicate(text, VOICE, rate="-4%", boundary="WordBoundary")
    except TypeError:
        comm = edge_tts.Communicate(text, VOICE, rate="-4%")
    words = []
    with open(path, "wb") as fh:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append(chunk["offset"] / 1e7)
    return words


def tts(text: str, idx: int):
    mp3 = WORK / f"vo_{idx}.mp3"
    for attempt in range(3):
        try:
            starts = asyncio.run(_tts(speakable(text), mp3))
            break
        except Exception as e:
            if attempt == 2:
                raise
            print(f"[TTS] retry ({e})")
            time.sleep(3)
    wav = WORK / f"vo_{idx}.wav"
    ff("-i", str(mp3), "-ar", "44100", "-ac", "1", str(wav))
    with wave.open(str(wav)) as w:
        dur = w.getnframes() / w.getframerate()
    toks = text.split()
    if len(starts) != len(speakable(text).split()) or not starts:
        starts = [i * dur / max(len(toks), 1) for i in range(len(toks))]
    return wav, dur, starts[:len(toks)] + [dur] * max(0, len(toks) - len(starts))


def chunk_words(starts, text):
    toks = text.split()
    chunks, cur, start = [], [], None
    for t, word in zip(starts, toks):
        if start is None:
            start = t
        cur.append(word)
        if len(cur) >= 4 or word[-1] in ".,:;?!":
            chunks.append([start, " ".join(cur)])
            cur, start = [], None
    if cur:
        chunks.append([start, " ".join(cur)])
    return chunks


# =============================================================================== visuals
def _font(name, size):
    return ImageFont.truetype(str(ASSETS / "fonts" / name), size)


def paper_texture():
    random.seed(7)
    base = Image.new("RGB", (W, H), PAPER)
    noise = Image.effect_noise((W, H), 18).convert("L").filter(ImageFilter.GaussianBlur(1.2))
    base = Image.composite(base, Image.new("RGB", (W, H), (226, 214, 190)),
                           ImageOps.autocontrast(noise).point(lambda v: 200 + v // 5))
    vign = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vign).ellipse([-300, -200, W + 300, H + 200], fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(160))
    return Image.composite(base, Image.new("RGB", (W, H), (205, 188, 160)), vign)


def _logo():
    return Image.open(ASSETS / "logo.png").convert("RGBA")


def scene_base(paper, art: Image.Image = None) -> Image.Image:
    img = paper.copy()
    logo = _logo()
    if art is not None:  # small top logo on story scenes only; the end card has the large centred logo
        lg = logo.resize((360, int(logo.height * 360 / logo.width)), Image.LANCZOS)
        img.paste(lg, ((W - lg.width) // 2, 140 - lg.height // 2), lg)
    d = ImageDraw.Draw(img)
    if art is not None:
        art = ImageOps.exif_transpose(art)
        s = min(960 / art.width, 1000 / art.height)
        art = art.resize((int(art.width * s), int(art.height * s)), Image.LANCZOS)
        pad = 14
        fr = Image.new("RGB", (art.width + pad * 2, art.height + pad * 2), INK)
        fr.paste(Image.new("RGB", (art.width + 8, art.height + 8), PAPER), (pad - 4, pad - 4))
        fr.paste(art, (pad, pad))
        x, y = (W - fr.width) // 2, 270 + (1010 - fr.height) // 2
        sh = Image.new("RGBA", (fr.width + 60, fr.height + 60), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle([30, 40, fr.width + 30, fr.height + 40], fill=(60, 40, 20, 90))
        sh = sh.filter(ImageFilter.GaussianBlur(16))
        img.paste(sh, (x - 30, y - 30), sh)
        img.paste(fr, (x, y))
    else:  # follow end card
        lg = logo.resize((760, int(logo.height * 760 / logo.width)), Image.LANCZOS)
        img.paste(lg, ((W - lg.width) // 2, 560), lg)
        d.text((W // 2, 860), CTA_LINE, font=_font("Montserrat-Black.ttf", 62), fill=INK, anchor="mm")
        d.line([(W // 2 - 220, 940), (W // 2 + 220, 940)], fill=ACCENT, width=8)
        bw, bh, by = 520, 104, 1010
        d.rounded_rectangle([(W - bw) // 2, by, (W + bw) // 2, by + bh], radius=52, fill=ACCENT)
        d.text((W // 2, by + bh // 2), "+ FOLLOW", font=_font("Montserrat-Black.ttf", 46), fill=PAPER, anchor="mm")
    return img


def caption_png(text, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = _font("Montserrat-Black.ttf", 74)
    lines, cur = [], ""
    for w_ in text.split():
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=f) <= 940:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    lines.append(cur)
    y = 1440 - (len(lines) * 88) // 2
    for line in lines:
        d.text((W // 2, y), line, font=f, fill=INK, anchor="ma", stroke_width=10, stroke_fill=PAPER)
        y += 88
    img.save(path)


def render(scenes: list, out_path: Path) -> Path:
    """scenes: [(PIL image or None for end card, narration text)]"""
    paper = paper_texture()
    clips, audios = [], []
    for i, (art, text) in enumerate(scenes):
        wav, dur, starts = tts(text, i)
        total = dur + 0.4
        padded = WORK / f"vo_{i}_p.wav"
        ff("-i", str(wav), "-af", f"apad=whole_dur={total:.2f}", str(padded))
        audios.append(padded)
        base = WORK / f"base_{i}.png"
        scene_base(paper, art).save(base)
        chunks = chunk_words(starts, text)
        frames = int(total * FPS)
        zoom = "min(1+0.0005*on,1.07)" if i % 2 == 0 else "max(1.07-0.0005*on,1)"
        inputs = ["-i", str(base)]
        filt = [f"[0]scale=1620:2880,zoompan=z='{zoom}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":s={W}x{H}:fps={FPS}[bg]"]
        last = "[bg]"
        for k, (start, ctext) in enumerate(chunks):
            end = chunks[k + 1][0] if k + 1 < len(chunks) else total
            cp = WORK / f"cap_{i}_{k}.png"
            caption_png(ctext, cp)
            inputs += ["-i", str(cp)]
            filt.append(f"{last}[{k + 1}]overlay=0:0:enable='between(t,{max(start - 0.05, 0):.2f},{end:.2f})'[v{k}]")
            last = f"[v{k}]"
        clip = WORK / f"clip_{i}.mp4"
        ff(*inputs, "-filter_complex", ";".join(filt), "-map", last, "-frames:v", str(frames), "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS), str(clip))
        clips.append(clip)
    (WORK / "v.txt").write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    (WORK / "a.txt").write_text("".join(f"file '{a.as_posix()}'\n" for a in audios), encoding="utf-8")
    ff("-f", "concat", "-safe", "0", "-i", str(WORK / "a.txt"), "-c", "copy", str(WORK / "narration.wav"))
    ff("-f", "concat", "-safe", "0", "-i", str(WORK / "v.txt"), "-i", str(WORK / "narration.wav"), "-c:v", "copy",
       "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out_path))
    return out_path


# =============================================================================== caption + publish
def build_caption(script: dict, credits: list, article_url: str) -> str:
    tags = []
    for t in script.get("hashtags", []):
        t = "#" + re.sub(r"[^a-z]", "", str(t).lower())
        if len(t) > 2 and t not in tags:
            tags.append(t)
    for t in ["#doodlore", "#history", "#mythology", "#didyouknow", "#storytime"]:
        if len(tags) >= 5:
            break
        if t not in tags:
            tags.append(t)
    art = " | ".join(dict.fromkeys(credits))
    parts = [script.get("caption_title", "").strip(), script.get("caption_body", "").strip(),
             f"{EMOJI['speech']} {script.get('question', '').strip()}",
             f"{EMOJI['palette']} Art (public domain / free licence, via Wikimedia Commons): {art}",
             " ".join(tags[:5])]
    return "\n\n".join(p for p in parts if p.strip())


def publish_reel(video: Path, description: str, page_id: str, token: str, api: str = "v22.0") -> dict:
    g = f"https://graph.facebook.com/{api}"
    start = requests.post(f"{g}/{page_id}/video_reels", data={"upload_phase": "start", "access_token": token}, timeout=30).json()
    vid = start.get("video_id")
    if not vid:
        return {"success": False, "error": start}
    with open(video, "rb") as fh:
        up = requests.post(f"https://rupload.facebook.com/video-upload/{api}/{vid}",
                           headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(os.path.getsize(video))},
                           data=fh, timeout=300).json()
    if not up.get("success"):
        return {"success": False, "error": up}
    fin = requests.post(f"{g}/{page_id}/video_reels", data={"upload_phase": "finish", "video_id": vid,
                        "video_state": "PUBLISHED", "description": description[:2200], "access_token": token}, timeout=60).json()
    if not fin.get("success"):
        return {"success": False, "error": fin}
    return {"success": True, "video_id": vid}


# =============================================================================== one run
def make_one(dry_run: bool) -> dict:
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    for f in WORK.glob("*"):
        f.unlink()
    history = load_history()
    try:
        refill_topics_if_low(history)
    except Exception as e:
        print(f"[Topics] refill skipped: {e}")
    recent_art = {a for h in history[-60:] for a in h.get("art", [])}

    for topic in next_topics(history):
        print(f"\n[Doodlore] Topic: {topic['title']} ({topic['pillar']})")
        try:
            article = wiki_article(topic["title"])
            print(f"[Wiki] {article['title']}: {len(article['text'])} chars")
            if len(article["text"]) < 1500:
                raise ValueError("article too short")
            script = write_script(topic, article)
            used, scenes, credits, art_titles = set(recent_art), [], [], []
            missing = 0
            for s in script["scenes"]:
                art = pick_art(s["text"], [s.get("art_query"), s.get("art_fallback")], used)
                if not art:
                    missing += 1
                    if not scenes or missing > 1:
                        raise ValueError(f"no suitable art for: {s['text'][:60]}")
                    print("[Art] no art for this scene; holding previous artwork")
                    scenes.append((scenes[-1][0], s["text"]))
                    continue
                used.add(art["title"])
                art_titles.append(art["title"])
                credits.append(art["credit"])
                scenes.append((art["image"], s["text"]))
                print(f"[Art] {art['title'][5:80]} [{art['license']}]")
            scenes.append((None, CTA_TEXT))
            slug = re.sub(r"[^a-z0-9]+", "-", topic["title"].lower()).strip("-")[:50]
            video = render(scenes, OUT / f"doodlore_{slug}.mp4")
            caption = build_caption(script, credits, article["url"])
            print(f"[Doodlore] Rendered {video.name}\n----- CAPTION -----\n{caption}\n-------------------")
            entry = {"title": topic["title"], "pillar": topic["pillar"], "art": art_titles,
                     "date": datetime.now(timezone.utc).isoformat(), "status": "dry_run" if dry_run else "posted"}
            if dry_run:
                return {"ok": True, "video": str(video), "caption": caption, "entry": entry}
            res = publish_reel(video, caption, os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_ACCESS_TOKEN"])
            if not res.get("success"):
                print(f"[Publish] FAILED: {str(res.get('error'))[:300]}")
                return {"ok": False}
            entry["video_id"] = res["video_id"]
            history.append(entry)
            save_history(history)
            print(f"[Publish] Reel published: {res['video_id']}")
            return {"ok": True, "video": str(video), "entry": entry}
        except Exception as e:
            print(f"[Doodlore] Skipping '{topic['title']}': {e}")
            history.append({"title": topic["title"], "pillar": topic["pillar"], "status": "skipped",
                            "reason": str(e)[:200], "date": datetime.now(timezone.utc).isoformat()})
            if not dry_run:
                save_history(history)
    return {"ok": False}
