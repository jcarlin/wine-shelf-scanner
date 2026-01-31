
# Vision → Claude → Ratings Pipeline

1. Image uploaded to /scan
2. Google Vision:
   - TEXT_DETECTION
   - OBJECT_LOCALIZATION (bottles)
3. Group OCR text by spatial proximity to bottle bbox
4. Send grouped OCR fragments to Claude
5. Claude returns:
   - canonical wine name
   - confidence score
6. Lookup rating from local DB
7. Return UI schema
