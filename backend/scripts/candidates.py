"""
Candidate architectures for the overlay-feasibility bake-off (Gate 2).

Each candidate is an async callable: (image_bytes, image_id) -> CandidateResult.
They are EVAL-ONLY thin implementations — the winner gets a production port
after Gate 2 approval. Register in CANDIDATES; run via:

    venv/bin/python -m scripts.eval_overlays --all --candidate c1_lean_sonnet

Shared conventions:
- bbox dicts are {x, y, w, h}, normalized 0-1, top-left origin.
- `usage` carries prompt/completion tokens + measured latency per paid call so
  eval runs produce measured (not estimated) cost.
"""

import asyncio
import base64
import io
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Optional

from PIL import Image, ImageDraw, ImageFont

from app.services.claude_vision import _compress_image_for_vision
from app.services.llm_usage import compute_cost_usd, log_usage
from app.config import Config

logger = logging.getLogger(__name__)

_LLM_IMAGE_RAW_BUDGET = int(5 * 1024 * 1024 * 0.72)


@dataclass
class CandidatePrediction:
    wine_name: str
    bbox: dict  # {x, y, w, h}
    confidence: float
    rating: Optional[float] = None  # LLM-estimated; DB may override later


@dataclass
class CandidateResult:
    predictions: list[CandidatePrediction]
    usage: list[dict] = field(default_factory=list)  # one per paid call
    notes: str = ""

    @property
    def total_cost_usd(self) -> float:
        return sum(u.get("cost_usd") or 0.0 for u in self.usage)

    @property
    def total_latency_ms(self) -> int:
        return sum(u.get("latency_ms") or 0 for u in self.usage)


# ---------------------------------------------------------------------------
# Shared LLM helpers
# ---------------------------------------------------------------------------

async def _llm_call(model: str, content: list, max_tokens: int, usage_out: list,
                    call_label: str, temperature: Optional[float] = 0.1) -> str:
    import litellm
    kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=max_tokens,
        drop_params=True,
    )
    if temperature is not None and "opus-4-7" not in model:
        kwargs["temperature"] = temperature
    t0 = time.perf_counter()
    response = await litellm.acompletion(**kwargs)
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
    return response.choices[0].message.content


def _image_part(image_bytes: bytes) -> dict:
    compressed = _compress_image_for_vision(image_bytes, max_size=_LLM_IMAGE_RAW_BUDGET)
    b64 = base64.b64encode(compressed).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}


def _parse_json_array(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?|\n?```$", "", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        logger.error("candidate: no JSON array in response: %s", text[:200])
        return []
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        logger.error("candidate: JSON parse failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# C1 — lean-output single call
# ---------------------------------------------------------------------------

C1_PROMPT = """Identify every wine bottle visible in this shelf photo, including back rows and partially occluded bottles.

Return ONLY a JSON array, no prose, no fences. One entry per visible bottle:
[{"n": "Producer Wine Name or null if unreadable", "b": [x, y, w, h], "c": 0.0-1.0, "r": 1.0-5.0}]

- b: normalized bbox of THAT bottle (top-left x,y; width; height), 3 decimals max, tight to the bottle so a badge at (x + w/2, y + 0.25*h) lands on it.
- c: identification confidence. r: your best Vivino-style rating estimate.
- Never merge two bottles into one box. A box must never span two shelf rows.
- Do not invent names you cannot read; use null."""


def _make_lean_single(model: str, label: str) -> Callable:
    async def run(image_bytes: bytes, image_id: str) -> CandidateResult:
        usage: list = []
        text = await _llm_call(
            model, [_image_part(image_bytes), {"type": "text", "text": C1_PROMPT}],
            max_tokens=4000, usage_out=usage, call_label=label,
        )
        preds = []
        for item in _parse_json_array(text):
            if not isinstance(item, dict) or not item.get("n"):
                continue
            b = item.get("b") or [0, 0, 0, 0]
            if not isinstance(b, list) or len(b) != 4:
                continue
            preds.append(CandidatePrediction(
                wine_name=str(item["n"]),
                bbox={"x": float(b[0]), "y": float(b[1]), "w": float(b[2]), "h": float(b[3])},
                confidence=float(item.get("c", 0.5)),
                rating=float(item["r"]) if item.get("r") else None,
            ))
        return CandidateResult(predictions=preds, usage=usage)
    return run


# ---------------------------------------------------------------------------
# Shared detection: Google Vision object localization, optionally tiled
# ---------------------------------------------------------------------------

def _vision_bottles_raw(image_bytes: bytes) -> list[dict]:
    """One OBJECT_LOCALIZATION call -> [{x,y,w,h,conf}] for bottle-ish objects."""
    from google.cloud import vision
    client = vision.ImageAnnotatorClient()
    resp = client.object_localization(image=vision.Image(content=image_bytes))
    out = []
    keywords = ("bottle", "wine", "drink")
    for o in resp.localized_object_annotations:
        if not any(k in o.name.lower() for k in keywords):
            continue
        vs = o.bounding_poly.normalized_vertices
        xs, ys = [v.x for v in vs], [v.y for v in vs]
        out.append({
            "x": min(xs), "y": min(ys),
            "w": max(xs) - min(xs), "h": max(ys) - min(ys),
            "conf": o.score,
        })
    return out


def _iou_d(a: dict, b: dict) -> float:
    ix1, iy1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    ix2 = min(a["x"] + a["w"], b["x"] + b["w"])
    iy2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def detect_bottles(image_bytes: bytes, tiled: bool = True,
                   iou_dedup: float = 0.45) -> list[dict]:
    """Bottle bboxes via Google Vision; `tiled` adds a 2x2 overlapping-tile pass
    to recover small/occluded bottles the full-frame pass misses (recall boost).
    Cost: 1 call full-frame, +4 calls tiled. Returns [{x,y,w,h,conf}] deduped.
    """
    img = Image.open(io.BytesIO(image_bytes))
    W, H = img.size
    boxes = _vision_bottles_raw(image_bytes)

    if tiled:
        overlap = 0.15
        tw, th = W * (0.5 + overlap / 2), H * (0.5 + overlap / 2)
        origins = [(0, 0), (W - tw, 0), (0, H - th), (W - tw, H - th)]
        for ox, oy in origins:
            crop = img.crop((int(ox), int(oy), int(ox + tw), int(oy + th)))
            buf = io.BytesIO()
            crop.convert("RGB").save(buf, format="JPEG", quality=90)
            for b in _vision_bottles_raw(buf.getvalue()):
                boxes.append({
                    "x": (ox + b["x"] * tw) / W,
                    "y": (oy + b["y"] * th) / H,
                    "w": b["w"] * tw / W,
                    "h": b["h"] * th / H,
                    "conf": b["conf"],
                })

    boxes.sort(key=lambda b: b["conf"], reverse=True)
    kept: list[dict] = []
    for b in boxes:
        if all(_iou_d(b, k) < iou_dedup for k in kept):
            kept.append(b)

    # Tile-edge truncations produce a second, shorter box on the same bottle
    # with low IoU (heights differ). Merge pairs where the intersection covers
    # most of the smaller box, keeping the larger (more complete) box.
    def _containment(a: dict, b: dict) -> float:
        ix1, iy1 = max(a["x"], b["x"]), max(a["y"], b["y"])
        ix2 = min(a["x"] + a["w"], b["x"] + b["w"])
        iy2 = min(a["y"] + a["h"], b["y"] + b["h"])
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        smaller = min(a["w"] * a["h"], b["w"] * b["h"])
        return inter / smaller if smaller > 0 else 0.0

    kept.sort(key=lambda b: b["w"] * b["h"], reverse=True)
    merged: list[dict] = []
    for b in kept:
        if all(_containment(b, m) < 0.6 for m in merged):
            merged.append(b)
    return merged


# ---------------------------------------------------------------------------
# C2 — set-of-marks: Vision boxes + numbered markers, LLM assigns names to IDs
# ---------------------------------------------------------------------------

C2_PROMPT = """This wine-shelf photo has numbered yellow markers, one per detected bottle. Marker N sits at the TOP-LEFT of bottle N's box.

For EACH marker number, read the label of THAT bottle and identify the wine.

Return ONLY a JSON array, no prose, no fences:
[{"id": <marker number>, "n": "Producer Wine Name or null if unreadable", "c": 0.0-1.0, "r": 1.0-5.0}]

- n: the wine on the bottle the marker points at — not a neighbor.
- c: identification confidence. r: your best Vivino-style rating estimate.
- Include EVERY marker id exactly once. Use null for unreadable labels.
Additionally, if you can clearly read bottles that have NO marker, append entries with "id": -1 and "b": [x, y, w, h] (normalized bbox of that bottle)."""


def _draw_marks(image_bytes: bytes, boxes: list[dict]) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    W, H = img.size
    draw = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", max(18, int(H * 0.03)))
    except Exception:
        f = ImageFont.load_default()
    for i, b in enumerate(boxes):
        x1, y1 = b["x"] * W, b["y"] * H
        x2, y2 = (b["x"] + b["w"]) * W, (b["y"] + b["h"]) * H
        draw.rectangle([x1, y1, x2, y2], outline=(255, 220, 0), width=3)
        label = str(i)
        tb = draw.textbbox((x1 + 2, y1 + 2), label, font=f)
        draw.rectangle([tb[0] - 3, tb[1] - 2, tb[2] + 3, tb[3] + 2], fill=(0, 0, 0))
        draw.text((x1 + 2, y1 + 2), label, fill=(255, 220, 0), font=f)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _make_set_of_marks(model: str, label: str, tiled: bool = True) -> Callable:
    async def run(image_bytes: bytes, image_id: str) -> CandidateResult:
        usage: list = []
        t0 = time.perf_counter()
        boxes = await asyncio.to_thread(detect_bottles, image_bytes, tiled)
        det_ms = round((time.perf_counter() - t0) * 1000)
        n_calls = 5 if tiled else 1
        usage.append({
            "call": "vision_detect", "model": "google/vision-object-localization",
            "latency_ms": det_ms, "cost_usd": 0.0015 * n_calls,  # $1.50/1k images
            "prompt_tokens": None, "completion_tokens": None,
        })
        if not boxes:
            return CandidateResult(predictions=[], usage=usage, notes="no bottles detected")

        marked = _draw_marks(image_bytes, boxes)
        text = await _llm_call(
            model, [_image_part(marked), {"type": "text", "text": C2_PROMPT}],
            max_tokens=3000, usage_out=usage, call_label=label,
        )
        preds = []
        for item in _parse_json_array(text):
            if not isinstance(item, dict) or not item.get("n"):
                continue
            idx = item.get("id", -1)
            if isinstance(idx, int) and 0 <= idx < len(boxes):
                bbox = {k: boxes[idx][k] for k in ("x", "y", "w", "h")}
            else:
                b = item.get("b")
                if not (isinstance(b, list) and len(b) == 4):
                    continue
                bbox = {"x": float(b[0]), "y": float(b[1]), "w": float(b[2]), "h": float(b[3])}
            preds.append(CandidatePrediction(
                wine_name=str(item["n"]), bbox=bbox,
                confidence=float(item.get("c", 0.5)),
                rating=float(item["r"]) if item.get("r") else None,
            ))
        return CandidateResult(predictions=preds, usage=usage,
                               notes=f"detected={len(boxes)} tiled={tiled}")
    return run


# ---------------------------------------------------------------------------
# C3 — per-crop label reading: Vision boxes -> one multi-crop LLM call
# ---------------------------------------------------------------------------

C3_PROMPT_HEAD = """Each image after this message is a crop of ONE wine bottle (crop index in order, starting at 0).

Identify the wine on each crop's CENTERED/dominant bottle.

Return ONLY a JSON array, no prose, no fences, one entry per crop in order:
[{"id": <crop index>, "n": "Producer Wine Name or null if unreadable", "c": 0.0-1.0, "r": 1.0-5.0}]"""


def _make_per_crop(model: str, label: str, tiled: bool = True) -> Callable:
    async def run(image_bytes: bytes, image_id: str) -> CandidateResult:
        usage: list = []
        t0 = time.perf_counter()
        boxes = await asyncio.to_thread(detect_bottles, image_bytes, tiled)
        det_ms = round((time.perf_counter() - t0) * 1000)
        n_calls = 5 if tiled else 1
        usage.append({
            "call": "vision_detect", "model": "google/vision-object-localization",
            "latency_ms": det_ms, "cost_usd": 0.0015 * n_calls,
            "prompt_tokens": None, "completion_tokens": None,
        })
        if not boxes:
            return CandidateResult(predictions=[], usage=usage, notes="no bottles detected")

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        W, H = img.size
        content: list = [{"type": "text", "text": C3_PROMPT_HEAD}]
        for b in boxes:
            pad_x, pad_y = b["w"] * 0.10, b["h"] * 0.05
            cx1 = max(0, (b["x"] - pad_x) * W)
            cy1 = max(0, (b["y"] - pad_y) * H)
            cx2 = min(W, (b["x"] + b["w"] + pad_x) * W)
            cy2 = min(H, (b["y"] + b["h"] + pad_y) * H)
            crop = img.crop((int(cx1), int(cy1), int(cx2), int(cy2)))
            if crop.width > 512:
                crop = crop.resize((512, int(crop.height * 512 / crop.width)))
            buf = io.BytesIO()
            crop.save(buf, format="JPEG", quality=88)
            content.append({
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64,"
                              + base64.b64encode(buf.getvalue()).decode()},
            })

        text = await _llm_call(model, content, max_tokens=3000,
                               usage_out=usage, call_label=label)
        preds = []
        for item in _parse_json_array(text):
            if not isinstance(item, dict) or not item.get("n"):
                continue
            idx = item.get("id", -1)
            if not (isinstance(idx, int) and 0 <= idx < len(boxes)):
                continue
            preds.append(CandidatePrediction(
                wine_name=str(item["n"]),
                bbox={k: boxes[idx][k] for k in ("x", "y", "w", "h")},
                confidence=float(item.get("c", 0.5)),
                rating=float(item["r"]) if item.get("r") else None,
            ))
        return CandidateResult(predictions=preds, usage=usage,
                               notes=f"detected={len(boxes)} tiled={tiled}")
    return run


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CANDIDATES: dict[str, Callable[[bytes, str], Awaitable[CandidateResult]]] = {
    "c1_lean_sonnet": _make_lean_single("anthropic/claude-sonnet-4-6", "c1_lean_sonnet"),
    "c1_lean_opus": _make_lean_single("anthropic/claude-opus-4-7", "c1_lean_opus"),
    "c1_lean_haiku": _make_lean_single("anthropic/claude-haiku-4-5-20251001", "c1_lean_haiku"),
    "c2_marks_sonnet": _make_set_of_marks("anthropic/claude-sonnet-4-6", "c2_marks_sonnet"),
    "c2_marks_haiku": _make_set_of_marks("anthropic/claude-haiku-4-5-20251001", "c2_marks_haiku"),
    "c3_crops_sonnet": _make_per_crop("anthropic/claude-sonnet-4-6", "c3_crops_sonnet"),
    "c3_crops_haiku": _make_per_crop("anthropic/claude-haiku-4-5-20251001", "c3_crops_haiku"),
}
