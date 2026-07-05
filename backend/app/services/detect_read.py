"""
Detect + Read core (Gate 2 approved architecture).

Tiled Google Vision object localization finds bottle boxes; one Claude
set-of-marks call names each numbered box (the LLM never emits coordinates);
weak marks get a per-crop re-read. Shared by the eval harness
(scripts/candidates.py: c4_daread_*) and the production pipeline so the
eval measures the exact code that ships.

Round 3 tuning (measured against the Gate 2 c2_marks_sonnet5 runs):
- Completion tokens dominated LLM cost (~70%) and latency (~8.5 ms/token):
  compact array output + thinking disabled cut them.
- The 5 Vision tile calls each created a client and uploaded a full-res
  JPEG: one batch_annotate_images call on downscaled tiles cuts wall time.
- Duplicate marks (tile-edge dupes) produced duplicate badges and broke
  top-3 precision: same-name+overlap dedup after the read.
"""

import asyncio
import base64
import io
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from app.services.llm_usage import compute_cost_usd

try:  # HEIC inputs reach this module directly in eval; the route converts first.
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Long edge (px) for images sent to Vision detection. Tiles cover half the
# frame each, so 1600 here ≈ 3200 effective full-frame resolution.
DETECT_LONG_EDGE = 1600
# Long edge for the marked image sent to the LLM. ~2048px ≈ 4.2k image
# tokens; smaller starts to hurt label legibility on dense shelves.
MARKED_LONG_EDGE = 2048
# Marks with no name or confidence below this get a crop re-read.
REREAD_CONF_THRESHOLD = 0.55
REREAD_MAX_CROPS = 8
# Re-read crops are the label zone only (middle band of the bottle), bounded
# to 512x768 px: full-bottle crops at 512 wide ran ~1k image tokens each.
CROP_MAX = (512, 768)
# Production hides badges below 0.45 confidence; don't emit them at all.
MIN_CONFIDENCE = 0.45

VISION_COST_PER_IMAGE = 0.0015  # $1.50 / 1k images, OBJECT_LOCALIZATION

_vision_client = None


def _get_vision_client():
    global _vision_client
    if _vision_client is None:
        from google.cloud import vision
        _vision_client = vision.ImageAnnotatorClient()
    return _vision_client


@dataclass
class DetectReadPrediction:
    wine_name: str
    bbox: dict  # {x, y, w, h} normalized
    confidence: float
    rating: Optional[float] = None


@dataclass
class DetectReadResult:
    predictions: list[DetectReadPrediction]
    usage: list[dict] = field(default_factory=list)
    notes: str = ""
    # Wall-clock ms for the whole detect+read section. The per-call latency
    # sum overstates when panel reads run in parallel.
    wall_ms: Optional[int] = None

    @property
    def total_cost_usd(self) -> float:
        return sum(u.get("cost_usd") or 0.0 for u in self.usage)


# ---------------------------------------------------------------------------
# Detection: one batched Vision request over full frame + 2x2 overlapping tiles
# ---------------------------------------------------------------------------

def _downscale(img: Image.Image, long_edge: int) -> Image.Image:
    scale = long_edge / max(img.size)
    if scale >= 1.0:
        return img
    return img.resize((round(img.width * scale), round(img.height * scale)))


def _jpeg_bytes(img: Image.Image, quality: int = 88) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _iou(a: dict, b: dict) -> float:
    ix1, iy1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    ix2 = min(a["x"] + a["w"], b["x"] + b["w"])
    iy2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def _containment(a: dict, b: dict) -> float:
    ix1, iy1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    ix2 = min(a["x"] + a["w"], b["x"] + b["w"])
    iy2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    smaller = min(a["w"] * a["h"], b["w"] * b["h"])
    return inter / smaller if smaller > 0 else 0.0


def detect_bottles(img: Image.Image, iou_dedup: float = 0.45) -> list[dict]:
    """Bottle bboxes (normalized {x,y,w,h,conf}) via 5 concurrent Vision calls
    (full frame + 4 overlapping tiles), each downscaled before upload.

    Measured: batch_annotate_images processes the batch serially server-side
    (3.4-12.2s); 5 concurrent single-image calls on a shared client with
    downscaled payloads run in ~2s wall."""
    from concurrent.futures import ThreadPoolExecutor

    from google.cloud import vision

    W, H = img.size
    jobs: list[tuple[float, float, float, float, Image.Image]] = [(0, 0, W, H, img)]
    overlap = 0.15
    tw, th = W * (0.5 + overlap / 2), H * (0.5 + overlap / 2)
    for ox, oy in [(0, 0), (W - tw, 0), (0, H - th), (W - tw, H - th)]:
        crop = img.crop((int(ox), int(oy), int(ox + tw), int(oy + th)))
        jobs.append((ox, oy, tw, th, crop))

    client = _get_vision_client()

    def _annotate(tile: Image.Image):
        jpeg = _jpeg_bytes(_downscale(tile, DETECT_LONG_EDGE))
        return client.object_localization(
            image=vision.Image(content=jpeg)
        ).localized_object_annotations

    with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        results = list(ex.map(lambda j: _annotate(j[4]), jobs))

    keywords = ("bottle", "wine", "drink")
    boxes: list[dict] = []
    for (ox, oy, jw, jh, _), annotations in zip(jobs, results):
        for o in annotations:
            if not any(k in o.name.lower() for k in keywords):
                continue
            vs = o.bounding_poly.normalized_vertices
            xs, ys = [v.x for v in vs], [v.y for v in vs]
            boxes.append({
                "x": (ox + min(xs) * jw) / W,
                "y": (oy + min(ys) * jh) / H,
                "w": (max(xs) - min(xs)) * jw / W,
                "h": (max(ys) - min(ys)) * jh / H,
                "conf": o.score,
            })

    boxes.sort(key=lambda b: b["conf"], reverse=True)
    kept: list[dict] = []
    for b in boxes:
        if all(_iou(b, k) < iou_dedup for k in kept):
            kept.append(b)

    # Tile-edge truncations produce a second, shorter box on the same bottle
    # with low IoU; merge pairs where the intersection covers most of the
    # smaller box, keeping the larger (more complete) box.
    kept.sort(key=lambda b: b["w"] * b["h"], reverse=True)
    merged: list[dict] = []
    for b in kept:
        if all(_containment(b, m) < 0.6 for m in merged):
            merged.append(b)
    return merged


# ---------------------------------------------------------------------------
# Set-of-marks read
# ---------------------------------------------------------------------------

READ_PROMPT = """This wine-shelf photo has numbered yellow markers, one per detected bottle. Marker N sits centered at the TOP of bottle N's box, directly above/on that bottle's neck.

For EACH marker {first}..{last}, read the label of THAT bottle (not a neighbor's) and identify the wine.

Return ONLY a JSON array, no prose, no fences. One compact entry per marker, every marker exactly once:
[[id, "Producer Wine Name" or null, confidence, rating], ...]

- confidence: 0.0-1.0 that the name is right. rating: your best Vivino-style estimate 1.0-5.0.
- Adjacent bottles often share a producer but differ in varietal/cuvée. Read the varietal text on the marked bottle itself; if you cannot make it out, use confidence below 0.55.
- Use null for the name if the label is unreadable; never guess or copy a neighbor's label.
- If you clearly read a bottle that has NO marker, append [-1, "Name", confidence, rating, [x, y, w, h]] with that bottle's normalized bbox in THIS image."""

REREAD_PROMPT = """Each image after this message is a crop of ONE wine bottle. The crops correspond, in order, to ids {ids}.

Identify the wine on each crop's centered/dominant bottle.

Return ONLY a JSON array, no prose, no fences, one compact entry per crop in order:
[[id, "Producer Wine Name" or null, confidence, rating], ...]"""


def draw_marks_panel(base: Image.Image, boxes: list[dict], ids: list[int],
                     py1: float, py2: float) -> bytes:
    """Crop the normalized [py1, py2) horizontal band from `base`, draw the
    numbered yellow boxes for `ids` (full-image-normalized), return JPEG."""
    W, H = base.size
    panel = base.crop((0, int(py1 * H), W, int(py2 * H))).convert("RGB")
    ph = panel.height
    draw = ImageDraw.Draw(panel)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", max(18, int(H * 0.025)))
    except Exception:
        f = ImageFont.load_default()
    for i in ids:
        b = boxes[i]
        x1, x2 = b["x"] * W, (b["x"] + b["w"]) * W
        y1 = (b["y"] - py1) / (py2 - py1) * ph
        y2 = (b["y"] + b["h"] - py1) / (py2 - py1) * ph
        draw.rectangle([x1, y1, x2, y2], outline=(255, 220, 0), width=3)
        # Center the tag on the bottle: a top-left tag visually hovers over
        # the left neighbor in tight packs (measured neighbor-copy swaps).
        tw = draw.textlength(str(i), font=f)
        tx = (x1 + x2) / 2 - tw / 2
        tb = draw.textbbox((tx, y1 + 2), str(i), font=f)
        draw.rectangle([tb[0] - 3, tb[1] - 2, tb[2] + 3, tb[3] + 2], fill=(0, 0, 0))
        draw.text((tx, y1 + 2), str(i), fill=(255, 220, 0), font=f)
    return _jpeg_bytes(panel, quality=90)


def _image_part(jpeg: bytes) -> dict:
    return {"type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}}


async def _llm_call(model: str, content: list, max_tokens: int, usage_out: list,
                    call_label: str) -> str:
    import litellm
    kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=max_tokens,
        drop_params=True,
        # Perception read, not reasoning: adaptive thinking on Sonnet 5 was
        # burning 1-2k completion tokens per scan (= most of cost + latency).
        thinking={"type": "disabled"},
    )
    t0 = time.perf_counter()
    # Run the sync client in a thread: litellm's request prep (image token
    # counting on multi-MB base64) is CPU-bound and serializes concurrent
    # acompletion calls on the event loop (measured: panel reads ran serial).
    response = await asyncio.to_thread(litellm.completion, **kwargs)
    latency_ms = round((time.perf_counter() - t0) * 1000)
    u = getattr(response, "usage", None)
    pt = getattr(u, "prompt_tokens", None) if u else None
    ct = getattr(u, "completion_tokens", None) if u else None
    usage_out.append({
        "call": call_label,
        "model": model,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "latency_ms": latency_ms,
        "cost_usd": compute_cost_usd(model, pt, ct, None),
        "truncated": bool(ct and ct >= max_tokens * 0.95),
    })
    return response.choices[0].message.content or ""


def _parse_entries(text: str) -> list[list]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?|\n?```$", "", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        logger.error("detect_read: JSON parse failed: %s", e)
        return []
    return [e for e in data if isinstance(e, list) and len(e) >= 4]


def _norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def dedup_predictions(preds: list[DetectReadPrediction]) -> list[DetectReadPrediction]:
    """Drop same-wine reads whose boxes overlap (one physical bottle, two
    marks). Adjacent facings of the same SKU don't overlap and are kept."""
    preds = sorted(preds, key=lambda p: p.confidence, reverse=True)
    kept: list[DetectReadPrediction] = []
    for p in preds:
        dup = any(
            _norm_name(p.wine_name) == _norm_name(k.wine_name)
            and (_iou(p.bbox, k.bbox) > 0.30 or _containment(p.bbox, k.bbox) > 0.55)
            for k in kept
        )
        if not dup:
            kept.append(p)
    return kept


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

# Panel-split parallel reads were tried and measurably hurt: cropping the
# shelf into bands broke the model's row context (8122 badge precision
# .83 -> .69, off-by-one neighbor cascade). One full-frame read only.
def _split_panels(boxes: list[dict]) -> list[tuple[list[int], float, float]]:
    return [(list(range(len(boxes))), 0.0, 1.0)]


async def _read_panel(model: str, base: Image.Image, boxes: list[dict],
                      panel: tuple[list[int], float, float], usage: list[dict],
                      call_label: str) -> list[list]:
    ids, py1, py2 = panel
    jpeg = await asyncio.to_thread(draw_marks_panel, base, boxes, ids, py1, py2)
    prompt = READ_PROMPT.format(first=ids[0], last=ids[-1])
    content = [_image_part(jpeg), {"type": "text", "text": prompt}]
    text = await _llm_call(model, content, max_tokens=1500, usage_out=usage,
                           call_label=call_label)
    entries = _parse_entries(text)
    if not entries:
        # Sonnet 5 occasionally returns empty content on the marks call.
        logger.warning("detect_read: empty/unparseable marks response, retrying once")
        text = await _llm_call(model, content, max_tokens=1500, usage_out=usage,
                               call_label=f"{call_label}_retry")
        entries = _parse_entries(text)
    # Map any -1 extra-bottle bboxes from panel coords to full-image coords.
    for e in entries:
        if e[0] == -1 and len(e) >= 5 and isinstance(e[4], list) and len(e[4]) == 4:
            x, y, w, h = e[4]
            e[4] = [x, py1 + y * (py2 - py1), w, h * (py2 - py1)]
    return entries


def _brand_dupe_ids(named: dict[int, tuple]) -> list[int]:
    """Marker ids whose read shares a leading brand token with a marker that
    read a DIFFERENT wine — the measured swap mode is same-producer varietal
    mixups (Frontera Cab vs Frontera Merlot). Identical names are duplicate
    facings, not ambiguity. Returns dupes ordered by ascending confidence."""
    groups: dict[str, list[int]] = {}
    for i, (name, _conf, _rating) in named.items():
        tok = _norm_name(name).split()
        if tok and len(tok[0]) >= 3:
            groups.setdefault(tok[0], []).append(i)
    dupes = [
        i for g in groups.values()
        if len({_norm_name(named[j][0]) for j in g}) >= 2
        for i in g
    ]
    return sorted(dupes, key=lambda i: named[i][1])


async def run_detect_read(image_bytes: bytes, model: str,
                          call_label: str = "detect_read") -> DetectReadResult:
    wall_start = time.perf_counter()
    usage: list[dict] = []
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    t0 = time.perf_counter()
    boxes = await asyncio.to_thread(detect_bottles, img)
    usage.append({
        "call": "vision_detect", "model": "google/vision-object-localization",
        "latency_ms": round((time.perf_counter() - t0) * 1000),
        "cost_usd": VISION_COST_PER_IMAGE * 5,
        "prompt_tokens": None, "completion_tokens": None,
    })
    if not boxes:
        return DetectReadResult(predictions=[], usage=usage, notes="no bottles detected")

    boxes.sort(key=lambda b: b["y"] + b["h"] / 2)  # reading order; panels get
    panels = _split_panels(boxes)                  # contiguous id ranges
    base = _downscale(img, MARKED_LONG_EDGE)
    entry_lists = await asyncio.gather(*[
        _read_panel(model, base, boxes, p, usage, call_label) for p in panels
    ])

    named: dict[int, tuple] = {}   # marker id -> (name, conf, rating)
    weak: list[int] = []           # ids with null/low-confidence reads
    extras: list[DetectReadPrediction] = []
    for entries in entry_lists:
        for e in entries:
            idx, name, conf, rating = e[0], e[1], e[2], e[3]
            conf = float(conf) if isinstance(conf, (int, float)) else 0.5
            rating = float(rating) if isinstance(rating, (int, float)) else None
            if isinstance(idx, int) and 0 <= idx < len(boxes):
                if not name or conf < REREAD_CONF_THRESHOLD:
                    weak.append(idx)
                else:
                    named[idx] = (str(name), conf, rating)
            elif idx == -1 and name and len(e) >= 5 and isinstance(e[4], list) and len(e[4]) == 4:
                b = e[4]
                extras.append(DetectReadPrediction(
                    wine_name=str(name),
                    bbox={"x": float(b[0]), "y": float(b[1]),
                          "w": float(b[2]), "h": float(b[3])},
                    confidence=conf, rating=rating,
                ))

    missing = [i for i in range(len(boxes)) if i not in named and i not in weak]
    reread_ids = list(dict.fromkeys(weak + missing + _brand_dupe_ids(named)))
    # A crop narrower than ~140px at full res carries no readable label —
    # re-reading it wastes a call and can overwrite a decent marks read.
    W = img.width
    reread_ids = [i for i in reread_ids if boxes[i]["w"] * W >= 140]
    reread_ids = reread_ids[:REREAD_MAX_CROPS]
    reread_named: dict[int, DetectReadPrediction] = {}
    if reread_ids:
        reread_named = await _reread_crops(model, img, boxes, reread_ids, usage, call_label)

    preds: list[DetectReadPrediction] = list(extras)
    for i, (name, conf, rating) in named.items():
        if i in reread_ids:
            continue  # replaced (or dropped) by the crop re-read below
        preds.append(DetectReadPrediction(
            wine_name=name,
            bbox={k: boxes[i][k] for k in ("x", "y", "w", "h")},
            confidence=conf, rating=rating,
        ))
    for i in reread_ids:
        rr = reread_named.get(i)
        orig = named.get(i)
        # A crop re-read only outranks a confident marks read when it is
        # itself confident — low-res crops produce garbage rewrites otherwise.
        if rr and (orig is None or rr.confidence >= max(0.6, orig[1] - 0.1)):
            preds.append(rr)
        elif orig:
            name, conf, rating = orig
            preds.append(DetectReadPrediction(
                wine_name=name,
                bbox={k: boxes[i][k] for k in ("x", "y", "w", "h")},
                confidence=conf, rating=rating,
            ))

    n_before = len(preds)
    preds = dedup_predictions(preds)
    n_dedup = n_before - len(preds)
    preds = [p for p in preds if p.confidence >= MIN_CONFIDENCE]
    return DetectReadResult(
        predictions=preds, usage=usage,
        notes=(f"detected={len(boxes)} panels={len(panels)} "
               f"reread={len(reread_ids)} deduped={n_dedup}"),
        wall_ms=round((time.perf_counter() - wall_start) * 1000),
    )


async def _reread_crops(model: str, img: Image.Image, boxes: list[dict],
                        ids: list[int], usage: list[dict],
                        call_label: str) -> dict[int, DetectReadPrediction]:
    """One multi-crop call re-reading weak marks from the full-res image."""
    W, H = img.size
    content: list = [{"type": "text", "text": REREAD_PROMPT.format(ids=ids)}]
    for i in ids:
        b = boxes[i]
        # Label zone: middle band of the bottle (labels sit below the shoulder).
        pad_x = b["w"] * 0.10
        cx1 = max(0, (b["x"] - pad_x) * W)
        cx2 = min(W, (b["x"] + b["w"] + pad_x) * W)
        cy1 = max(0, (b["y"] + b["h"] * 0.20) * H)
        cy2 = min(H, (b["y"] + b["h"] * 0.90) * H)
        crop = img.crop((int(cx1), int(cy1), int(cx2), int(cy2)))
        crop.thumbnail(CROP_MAX)
        content.append(_image_part(_jpeg_bytes(crop)))

    text = await _llm_call(model, content, max_tokens=1000, usage_out=usage,
                           call_label=f"{call_label}_reread")
    out: dict[int, DetectReadPrediction] = {}
    for e in _parse_entries(text):
        idx, name, conf, rating = e[0], e[1], e[2], e[3]
        if not name or not (isinstance(idx, int) and idx in ids):
            continue
        out[idx] = DetectReadPrediction(
            wine_name=str(name),
            bbox={k: boxes[idx][k] for k in ("x", "y", "w", "h")},
            confidence=min(float(conf) if isinstance(conf, (int, float)) else 0.5, 0.75),
            rating=float(rating) if isinstance(rating, (int, float)) else None,
        )
    return out
