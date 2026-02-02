#!/usr/bin/env python3
"""
Setup XWines test corpus with ground truth.

Reads the XWines dataset CSV and generates ground truth JSON files
for each wine image in the evaluation set.

Usage:
    python scripts/setup_xwines_corpus.py
"""

import csv
import json
import shutil
from pathlib import Path


def main():
    # Paths
    project_root = Path(__file__).parent.parent.parent
    xwines_csv = project_root / "raw-data/X-Wines-main/Dataset/last/XWines_Test_100_wines.csv"
    xwines_images = project_root / "raw-data/X-Wines-main/Evaluation/data_images"
    corpus_labels = project_root / "test-images/corpus/labels"
    corpus_gt = project_root / "test-images/corpus/ground_truth"

    # Ensure directories exist
    corpus_labels.mkdir(parents=True, exist_ok=True)
    corpus_gt.mkdir(parents=True, exist_ok=True)

    if not xwines_csv.exists():
        print(f"Error: XWines CSV not found at {xwines_csv}")
        return 1

    if not xwines_images.exists():
        print(f"Error: XWines images not found at {xwines_images}")
        return 1

    # Read XWines CSV to map wine IDs to names
    wine_lookup = {}
    with open(xwines_csv, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            wine_id = row['WineID']
            wine_name = row['WineName']
            winery = row.get('WineryName', '')
            region = row.get('RegionName', '')
            country = row.get('Country', '')
            wine_type = row.get('Type', '')

            # Build full wine name for ground truth
            # Some wines have winery in name, some don't
            full_name = wine_name
            if winery and winery.lower() not in wine_name.lower():
                full_name = f"{winery} {wine_name}"

            wine_lookup[wine_id] = {
                'wine_name': full_name,
                'simple_name': wine_name,
                'winery': winery,
                'region': region,
                'country': country,
                'wine_type': wine_type,
            }

    print(f"Loaded {len(wine_lookup)} wines from XWines CSV")

    # Process each image
    images_copied = 0
    gt_created = 0

    for image_path in xwines_images.glob("*.jpeg"):
        wine_id = image_path.stem

        if wine_id not in wine_lookup:
            print(f"  Warning: No metadata for wine ID {wine_id}")
            continue

        wine_info = wine_lookup[wine_id]

        # Copy image to corpus/labels
        dest_image = corpus_labels / image_path.name
        if not dest_image.exists():
            shutil.copy(image_path, dest_image)
            images_copied += 1

        # Create ground truth JSON
        gt_file = corpus_gt / f"{wine_id}.json"
        ground_truth = {
            "image_file": image_path.name,
            "wines": [
                {
                    "wine_name": wine_info['wine_name'],
                    "expected_rating": None,  # XWines doesn't have ratings
                    "rating_tolerance": 0.5,
                    "notes": f"Winery: {wine_info['winery']}, Region: {wine_info['region']}, Type: {wine_info['wine_type']}"
                }
            ],
            "total_visible_bottles": 1,
            "notes": f"XWines evaluation image. Country: {wine_info['country']}. Simple name: {wine_info['simple_name']}"
        }

        with open(gt_file, 'w') as f:
            json.dump(ground_truth, f, indent=2)
        gt_created += 1

    print(f"\nSetup complete:")
    print(f"  Images copied: {images_copied}")
    print(f"  Ground truth files created: {gt_created}")
    print(f"  Corpus location: {corpus_labels.parent}")

    return 0


if __name__ == "__main__":
    exit(main())
