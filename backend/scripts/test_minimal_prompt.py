"""Test minimal prompt approach: ask for wine NAMES only, no metadata."""
import base64, json, os, sys, time, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'env', '.env')
if os.path.exists(env_path): load_dotenv(env_path, override=True)

MINIMAL_PROMPT = """List every wine bottle visible in this photo. Return ONLY a JSON array of wine names. No bounding boxes, no ratings, no metadata. Just names.

Example: ["Caymus Cabernet Sauvignon", "Opus One 2019"]

If you can read the producer/winery name and grape variety, include both. If you can only see partial text, include your best guess. Return ONLY the JSON array, nothing else."""

image_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "test-images", "IMG_8080.jpg")
with open(image_path, "rb") as f:
    image_bytes = f.read()
image_b64 = base64.b64encode(image_bytes).decode("utf-8")

async def test_gemini(model: str):
    import litellm
    litellm.set_verbose = False
    t0 = time.perf_counter()
    response = await litellm.acompletion(
        model=f"gemini/{model}",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            {"type": "text", "text": MINIMAL_PROMPT},
        ]}],
        max_tokens=1000,
        temperature=0.1,
    )
    elapsed = time.perf_counter() - t0
    text = response.choices[0].message.content.strip()
    if text.startswith("```"): text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        wines = json.loads(text)
    except:
        wines = []
        print(f"  PARSE ERROR: {text[:200]}")
    return elapsed, wines

async def main():
    print(f"Image: {len(image_bytes)/1024:.0f} KB")

    for model in ["gemini-2.0-flash", "gemini-2.0-flash-lite"]:
        print(f"\n{'='*60}")
        print(f"Model: {model} (names-only prompt)")
        elapsed, wines = await test_gemini(model)
        print(f"Time: {elapsed:.2f}s")
        print(f"Wines: {len(wines)}")
        for i, w in enumerate(wines):
            print(f"  {i+1}. {w}")

        # Now do parallel DB lookups
        from app.services.wine_matcher import WineMatcher
        matcher = WineMatcher(use_sqlite=True)
        t0 = time.perf_counter()
        results = []
        for name in wines:
            match = matcher.match(name)
            if match:
                results.append((name, match.canonical_name, match.rating, match.confidence))
            else:
                results.append((name, None, None, 0))
        t_db = time.perf_counter() - t0

        print(f"\nDB lookup: {t_db*1000:.0f}ms")
        matched = sum(1 for _, cn, _, _ in results if cn)
        with_rating = sum(1 for _, _, r, _ in results if r is not None)
        print(f"DB matched: {matched}/{len(wines)}")
        print(f"With ratings: {with_rating}/{len(wines)}")
        print(f"TOTAL time (LLM + DB): {elapsed + t_db:.2f}s")

        for llm_name, db_name, rating, conf in results:
            status = f"-> {db_name} (rating={rating}, conf={conf:.2f})" if db_name else "-> NO MATCH"
            print(f"  {llm_name:<45s} {status}")

asyncio.run(main())
