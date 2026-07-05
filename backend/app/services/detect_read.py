"""
Detect + Read core (Gate 2 approved architecture).

Tiled Google Vision object localization finds bottle boxes; Claude reads
each bottle's label from a per-bottle crop (the LLM never emits coordinates,
and crop k IS bottle k, so there is no marker<->bottle correspondence to
lose). Weak reads get one full-bottle rescue pass. Shared by the eval
harness (scripts/candidates.py: c4_daread_*) and the production pipeline so
the eval measures the exact code that ships.

Round 3 history (measured): set-of-marks variants (Gate 2 C2) kept breaking
id<->bottle sync on dense lookalike walls — off-by-one swap cascades — so
the per-crop C3 architecture became the primary read, with thinking
disabled, compact array output, label-zone crops, parallel chunked calls,
width-aware group-box merging, and same-name overlap dedup.
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
# Reads with no name or confidence below this get a full-bottle rescue read.
REREAD_CONF_THRESHOLD = 0.55
REREAD_MAX_CROPS = 8
# Primary label-zone crops are height-bound on tall bottles, so the height
# cap sets the token cost: 640px ≈ 210 image tokens/crop (768px ≈ 300).
# The full-bottle rescue pass keeps the taller cap for context.
CROP_MAX = (512, 640)
CROP_MAX_FULL = (512, 896)
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

    # Containment merge, width-aware. Two cases produce a box mostly inside
    # a bigger one: (a) tile-edge truncation of the SAME bottle -> similar
    # widths, keep the larger box; (b) a multi-bottle GROUP detection that
    # contains a single-bottle box -> group is much wider, keep the singles
    # (a badge on a group box sits between bottles; measured on IMG_8335).
    kept.sort(key=lambda b: b["w"] * b["h"], reverse=True)
    merged: list[dict] = []
    for b in kept:  # area-descending: groups arrive before their singles
        drop = False
        for m in list(merged):
            if _containment(b, m) >= 0.6:
                if b["w"] >= 0.6 * m["w"]:
                    drop = True          # same bottle; keep the larger box
                else:
                    merged.remove(m)     # m spans multiple bottles; prefer b
        if not drop:
            merged.append(b)
    return merged


# ---------------------------------------------------------------------------
# Per-crop label reading (C3 architecture: crop k IS bottle k, so there is no
# marker<->bottle correspondence to lose — set-of-marks variants kept breaking
# id sync on dense lookalike walls, measured as off-by-one swap cascades)
# ---------------------------------------------------------------------------

CROPS_PROMPT = """Each image after this message is a crop of ONE wine bottle from a shelf photo (mostly the label area). The crops correspond, in order, to ids {ids}.

Identify the wine on each crop's dominant/centered bottle.

Return ONLY a JSON array, no prose, no fences, one compact entry per crop in the same order:
[[id, "Producer Wine Name" or null, confidence, rating], ...]

- confidence: 0.0-1.0 that the name is right. rating: your best Vivino-style estimate 1.0-5.0.
- Use null for the name if the label is not readable; never guess."""


def _image_part(jpeg: bytes) -> dict:
    return {"type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}}


def _crop_jpeg(img: Image.Image, b: dict, zone: str) -> bytes:
    """Crop one bottle from the full-res image. zone="label" takes the middle
    band (cheap, ~250-350 image tokens); zone="full" takes the whole bottle
    (more context for the rescue pass)."""
    W, H = img.size
    pad_x = b["w"] * 0.10
    cx1 = max(0, (b["x"] - pad_x) * W)
    cx2 = min(W, (b["x"] + b["w"] + pad_x) * W)
    if zone == "label":
        cy1 = max(0, (b["y"] + b["h"] * 0.15) * H)
        cy2 = min(H, (b["y"] + b["h"] * 0.92) * H)
    else:
        cy1 = max(0, (b["y"] - b["h"] * 0.05) * H)
        cy2 = min(H, (b["y"] + b["h"] * 1.05) * H)
    crop = img.crop((int(cx1), int(cy1), int(cx2), int(cy2)))
    crop.thumbnail(CROP_MAX if zone == "label" else CROP_MAX_FULL)
    return _jpeg_bytes(crop)


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
    # Sync client in a thread: litellm's request prep (image token counting
    # on multi-MB base64) is CPU-bound and serializes concurrent acompletion
    # calls on the event loop (measured: parallel calls ran serial).
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
    boxes). Adjacent facings of the same SKU don't overlap and are kept."""
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

# Crops per LLM call. Crops are independent, so chunking across parallel
# calls halves wall time with no context loss and no extra image tokens
# (unlike the abandoned marked-image panel split).
CROPS_PER_CALL = 10


def _reading_order(boxes: list[dict]) -> list[dict]:
    """Sort boxes top row first, left-to-right within a row (stable ids for
    debugging and rendered-proof review)."""
    rows: list[dict] = []
    for b in sorted(boxes, key=lambda x: x["y"] + x["h"] / 2):
        cy = b["y"] + b["h"] / 2
        for r in rows:
            if abs(cy - r["cy"]) < 0.5 * r["h"]:
                r["items"].append(b)
                r["cy"] = sum(x["y"] + x["h"] / 2 for x in r["items"]) / len(r["items"])
                r["h"] = sum(x["h"] for x in r["items"]) / len(r["items"])
                break
        else:
            rows.append({"cy": cy, "h": b["h"], "items": [b]})
    rows.sort(key=lambda r: r["cy"])
    out: list[dict] = []
    for r in rows:
        out.extend(sorted(r["items"], key=lambda x: x["x"]))
    return out


async def _read_crops(model: str, img: Image.Image, boxes: list[dict],
                      ids: list[int], zone: str, usage: list[dict],
                      call_label: str) -> dict[int, tuple]:
    """One LLM call reading the crops for `ids`. Returns id -> (name, conf,
    rating); unreadable (null-name) crops are omitted."""
    content: list = [{"type": "text", "text": CROPS_PROMPT.format(ids=ids)}]
    for i in ids:
        jpeg = await asyncio.to_thread(_crop_jpeg, img, boxes[i], zone)
        content.append(_image_part(jpeg))
    text = await _llm_call(model, content, max_tokens=1200, usage_out=usage,
                           call_label=call_label)
    entries = _parse_entries(text)
    if not entries:
        # Sonnet 5 occasionally returns empty content — retry once.
        logger.warning("detect_read: empty/unparseable crops response, retrying once")
        text = await _llm_call(model, content, max_tokens=1200, usage_out=usage,
                               call_label=f"{call_label}_retry")
        entries = _parse_entries(text)
    out: dict[int, tuple] = {}
    for e in entries:
        idx, name, conf, rating = e[0], e[1], e[2], e[3]
        if name and isinstance(idx, int) and idx in ids:
            out[idx] = (
                str(name),
                float(conf) if isinstance(conf, (int, float)) else 0.5,
                float(rating) if isinstance(rating, (int, float)) else None,
            )
    return out


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

    boxes = _reading_order(boxes)
    all_ids = list(range(len(boxes)))
    chunks = [all_ids[i:i + CROPS_PER_CALL] for i in range(0, len(all_ids), CROPS_PER_CALL)]
    results = await asyncio.gather(*[
        _read_crops(model, img, boxes, chunk, "label", usage, call_label)
        for chunk in chunks
    ])
    named: dict[int, tuple] = {}
    for r in results:
        named.update(r)

    # Rescue pass: unreadable or low-confidence label-zone crops get one
    # full-bottle re-read (wider context). Tiny boxes can't be read at all.
    weak = [i for i in all_ids
            if (i not in named or named[i][1] < REREAD_CONF_THRESHOLD)
            and boxes[i]["w"] * img.width >= 140]
    weak = weak[:REREAD_MAX_CROPS]
    if weak:
        rescued = await _read_crops(model, img, boxes, weak, "full", usage,
                                    f"{call_label}_rescue")
        for i, (name, conf, rating) in rescued.items():
            orig = named.get(i)
            if orig is None or conf >= orig[1]:
                named[i] = (name, conf, rating)

    preds = [
        DetectReadPrediction(
            wine_name=name,
            bbox={k: boxes[i][k] for k in ("x", "y", "w", "h")},
            confidence=conf, rating=rating,
        )
        for i, (name, conf, rating) in named.items()
    ]
    n_before = len(preds)
    preds = dedup_predictions(preds)
    n_dedup = n_before - len(preds)
    preds = [p for p in preds if p.confidence >= MIN_CONFIDENCE]
    return DetectReadResult(
        predictions=preds, usage=usage,
        notes=(f"detected={len(boxes)} chunks={len(chunks)} "
               f"rescued={len(weak)} deduped={n_dedup}"),
        wall_ms=round((time.perf_counter() - wall_start) * 1000),
    )
