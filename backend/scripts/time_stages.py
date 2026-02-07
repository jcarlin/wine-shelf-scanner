"""Time each stage of the turbo pipeline independently."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'env', '.env')
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)

os.environ["LOG_LEVEL"] = "WARNING"

image_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "test-images", "IMG_8080.jpg")
with open(image_path, "rb") as f:
    image_bytes = f.read()

print(f"Image: {len(image_bytes)/1024:.0f} KB")

# Stage 1: Vision API
from app.services.vision import VisionService
t0 = time.perf_counter()
vision_service = VisionService()
vision_result = vision_service.analyze(image_bytes)
t_vision = time.perf_counter() - t0
print(f"\n1. Vision API: {t_vision:.2f}s — {len(vision_result.objects)} bottles, {len(vision_result.text_blocks)} text blocks")

# Stage 2: OCR grouping
from app.services.ocr_processor import OCRProcessor
t0 = time.perf_counter()
ocr = OCRProcessor()
ocr_result = ocr.process_with_orphans(vision_result.objects, vision_result.text_blocks)
t_ocr = time.perf_counter() - t0
print(f"2. OCR grouping: {t_ocr*1000:.0f}ms — {len(ocr_result.bottle_texts)} bottles, {len(ocr_result.orphaned_texts)} orphans")
for bt in ocr_result.bottle_texts:
    print(f"   Bottle: normalized={bt.normalized_name!r}")
for ot in ocr_result.orphaned_texts:
    print(f"   Orphan: text={ot.text[:60]!r} normalized={ot.normalized_name!r}")

# Stage 3: Fuzzy matching only (no LLM)
import asyncio
from app.services.recognition_pipeline import RecognitionPipeline
from app.services.wine_matcher import WineMatcher

t0 = time.perf_counter()
matcher = WineMatcher(use_sqlite=True)
t_matcher_init = time.perf_counter() - t0
print(f"\n3a. WineMatcher init: {t_matcher_init:.2f}s")

t0 = time.perf_counter()
pipeline_no_llm = RecognitionPipeline(wine_matcher=matcher, use_llm=False, debug_mode=False)
recognized_no_llm = asyncio.run(pipeline_no_llm.recognize(ocr_result.bottle_texts))
t_fuzzy = time.perf_counter() - t0
print(f"3b. Fuzzy match only: {t_fuzzy*1000:.0f}ms — {len(recognized_no_llm)} matches")
for w in recognized_no_llm:
    print(f"   {w.wine_name} (conf={w.confidence:.2f}, rating={w.rating})")

# Stage 4: With LLM
t0 = time.perf_counter()
pipeline_llm = RecognitionPipeline(wine_matcher=matcher, use_llm=True, debug_mode=False)
recognized_llm = asyncio.run(pipeline_llm.recognize(ocr_result.bottle_texts))
t_llm = time.perf_counter() - t0
print(f"3c. Fuzzy + LLM batch: {t_llm:.2f}s — {len(recognized_llm)} matches")
for w in recognized_llm:
    print(f"   {w.wine_name} (conf={w.confidence:.2f}, rating={w.rating}, src={w.source})")

print(f"\n{'='*60}")
print(f"SUMMARY:")
print(f"  Vision API:     {t_vision:.2f}s")
print(f"  OCR grouping:   {t_ocr*1000:.1f}ms")
print(f"  Matcher init:   {t_matcher_init:.2f}s")
print(f"  Fuzzy only:     {t_fuzzy*1000:.0f}ms ({len(recognized_no_llm)} wines)")
print(f"  Fuzzy + LLM:    {t_llm:.2f}s ({len(recognized_llm)} wines)")
print(f"  Total (no LLM): {t_vision + t_ocr + t_matcher_init + t_fuzzy:.2f}s")
print(f"  Total (w/ LLM): {t_vision + t_ocr + t_matcher_init + t_llm:.2f}s")
