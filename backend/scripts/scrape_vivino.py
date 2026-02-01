#!/usr/bin/env python3
"""
Vivino Wine Scraper - Global Edition

Scrapes wine data from Vivino's API for all major wine-producing countries.

Usage:
    python scripts/scrape_vivino.py                    # Scrape all countries
    python scripts/scrape_vivino.py --country us       # Scrape specific country
    python scripts/scrape_vivino.py --country us,fr    # Scrape multiple countries
    python scripts/scrape_vivino.py --resume           # Resume from checkpoint
    python scripts/scrape_vivino.py --test             # Test mode (10 wines per type)
    python scripts/scrape_vivino.py --status           # Show scraping progress
    python scripts/scrape_vivino.py --check-api        # Test API connectivity
    python scripts/scrape_vivino.py --convert-legacy   # Convert existing vivino.csv

NOTE: Vivino's API may block automated requests. If scraping fails, consider:
1. Using the Apify Vivino MCP Server: https://apify.com/canadesk/vivino
2. Downloading existing datasets from Kaggle
3. Manual data collection from Vivino website
"""

import argparse
import csv
import json
import os
import random
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

# Configuration
COUNTRIES = {
    "fr": "France",
    "it": "Italy",
    "es": "Spain",
    "us": "United States",
    "ar": "Argentina",
    "cl": "Chile",
    "au": "Australia",
    "pt": "Portugal",
    "de": "Germany",
    "za": "South Africa",
    "nz": "New Zealand",
    "at": "Austria",
}

WINE_TYPES = {
    1: "Red",
    2: "White",
    3: "Sparkling",
    4: "Rose",
}

# Rate limiting configuration
MIN_DELAY = 1.0  # Minimum seconds between requests
MAX_DELAY = 2.0  # Maximum seconds between requests
RETRY_DELAY = 30  # Seconds to wait on rate limit
MAX_RETRIES = 3  # Max retries per request

# Rotating User-Agent strings
USER_AGENTS = [
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36",
]

# Output paths
OUTPUT_DIR = Path(__file__).parent.parent.parent / "raw-data" / "vivino-scraped"
LEGACY_CSV = Path(__file__).parent.parent.parent / "raw-data" / "vivino-webscraper-and-data" / "vivino.csv"
CHECKPOINT_FILE = OUTPUT_DIR / "checkpoint.json"
WINE_IDS_FILE = OUTPUT_DIR / "scraped_wine_ids.json"
SCRAPE_LOG_FILE = OUTPUT_DIR / "scrape_log.json"

# CSV columns
CSV_COLUMNS = ["Winery", "Year", "Wine ID", "Wine", "Rating", "num_review", "price", "Country", "Region", "Wine Type"]


def check_api_connectivity() -> bool:
    """
    Test if Vivino API is accessible and returning data.

    Returns:
        True if API is working, False otherwise
    """
    print("Testing Vivino API connectivity...")
    print("=" * 60)

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    # First get cookies from explore page
    try:
        explore_resp = session.get(
            "https://www.vivino.com/explore",
            headers=headers,
            timeout=30,
        )
        print(f"  Explore page: {explore_resp.status_code}")
    except requests.RequestException as e:
        print(f"  Failed to reach Vivino: {e}")
        return False

    # Try the API
    params = {
        "country_codes[]": "es",
        "wine_type_ids[]": "1",
        "min_rating": "1",
        "page": "1",
    }

    try:
        api_resp = session.get(
            "https://www.vivino.com/api/explore/explore",
            params=params,
            headers=headers,
            timeout=30,
        )
        print(f"  API response: {api_resp.status_code}")

        if api_resp.status_code == 200:
            data = api_resp.json()
            explore = data.get("explore_vintage", {})
            records = explore.get("records_matched", 0)
            matches = len(explore.get("matches", []))

            print(f"  Records matched: {records:,}")
            print(f"  Wines returned: {matches}")

            if records > 0 and matches > 0:
                print("\n  API is working correctly!")
                return True
            else:
                print("\n  API returns empty results (may be blocking automated requests)")
                _print_alternatives()
                return False
        else:
            print(f"\n  API returned error status: {api_resp.status_code}")
            _print_alternatives()
            return False

    except requests.RequestException as e:
        print(f"\n  API request failed: {e}")
        _print_alternatives()
        return False


def _print_alternatives():
    """Print alternative data acquisition methods."""
    print("\n" + "=" * 60)
    print("ALTERNATIVE DATA SOURCES")
    print("=" * 60)
    print("""
Vivino's API appears to be blocking automated requests.
Here are alternative approaches to obtain wine data:

1. APIFY VIVINO SCRAPER (Recommended)
   - URL: https://apify.com/canadesk/vivino
   - Commercial service with reliable scraping
   - Cost: Usage-based pricing (free tier available)
   - Output: Download as CSV, place in raw-data/vivino-scraped/

2. EXISTING LEGACY DATA
   Run: python scripts/scrape_vivino.py --convert-legacy
   - Converts the existing vivino.csv (8,650 Spanish wines)
   - Good for testing the pipeline

3. KAGGLE DATASETS
   Search for "Vivino wine" on kaggle.com
   - Several community datasets available
   - Download and convert to expected format

4. MANUAL COLLECTION
   - Visit vivino.com/explore
   - Use browser DevTools to capture API responses
   - Save as JSON files for processing

After obtaining data, run:
   python scripts/ingest.py --source vivino_global
""")


def convert_legacy_csv():
    """Convert the legacy vivino.csv to the new format with Wine Type column."""
    print("Converting legacy vivino.csv...")
    print("=" * 60)

    if not LEGACY_CSV.exists():
        print(f"Error: Legacy CSV not found at {LEGACY_CSV}")
        return False

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "vivino_es.csv"  # Spanish wines

    # Read legacy CSV
    wines_converted = 0
    with open(LEGACY_CSV, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', newline='', encoding='utf-8') as outfile:

        reader = csv.DictReader(infile)
        writer = csv.DictWriter(outfile, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for row in reader:
            # Legacy format doesn't have Wine Type - infer "Red" since original scrape
            # used wine_type_ids[]=1 (Red wines only)
            new_row = {
                "Winery": row.get("Winery", ""),
                "Year": row.get("Year", ""),
                "Wine ID": row.get("Wine ID", ""),
                "Wine": row.get("Wine", ""),
                "Rating": row.get("Rating", ""),
                "num_review": row.get("num_review", ""),
                "price": row.get("price", ""),
                "Country": row.get("Country", ""),
                "Region": row.get("Region", ""),
                "Wine Type": "Red",  # Original scrape was red wines only
            }
            writer.writerow(new_row)
            wines_converted += 1

    print(f"  Converted {wines_converted:,} wines")
    print(f"  Output: {output_file}")
    print("\nYou can now run:")
    print("  python scripts/ingest.py --source vivino_global")
    return True


class VivinoScraper:
    """Scrapes wine data from Vivino's explore API."""

    BASE_URL = "https://www.vivino.com/api/explore/explore"

    def __init__(self, output_dir: Path = OUTPUT_DIR, min_reviews: int = 10):
        """
        Initialize scraper.

        Args:
            output_dir: Directory to save CSV files
            min_reviews: Minimum number of reviews required to include a wine
        """
        self.output_dir = output_dir
        self.min_reviews = min_reviews
        self.session = requests.Session()
        self.scraped_wine_ids: set[str] = set()
        self.checkpoint: dict = {}

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load existing state
        self._load_wine_ids()
        self._load_checkpoint()

    def _load_wine_ids(self):
        """Load already scraped wine IDs from file."""
        if WINE_IDS_FILE.exists():
            with open(WINE_IDS_FILE, 'r') as f:
                data = json.load(f)
                self.scraped_wine_ids = set(data.get("wine_ids", []))
            print(f"Loaded {len(self.scraped_wine_ids):,} previously scraped wine IDs")

    def _save_wine_ids(self):
        """Save scraped wine IDs to file."""
        with open(WINE_IDS_FILE, 'w') as f:
            json.dump({"wine_ids": list(self.scraped_wine_ids)}, f)

    def _load_checkpoint(self):
        """Load checkpoint for resume capability."""
        if CHECKPOINT_FILE.exists():
            with open(CHECKPOINT_FILE, 'r') as f:
                self.checkpoint = json.load(f)
            print(f"Loaded checkpoint: {self.checkpoint}")

    def _save_checkpoint(self, country: str, wine_type: int, page: int, total_wines: int):
        """Save current progress to checkpoint file."""
        self.checkpoint = {
            "country": country,
            "wine_type": wine_type,
            "page": page,
            "total_wines": total_wines,
            "timestamp": datetime.now().isoformat(),
        }
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump(self.checkpoint, f, indent=2)

    def _clear_checkpoint(self):
        """Clear checkpoint after successful completion."""
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
        self.checkpoint = {}

    def _get_random_user_agent(self) -> str:
        """Get a random User-Agent string."""
        return random.choice(USER_AGENTS)

    def _init_session(self):
        """Initialize session with cookies from Vivino explore page."""
        headers = {"User-Agent": self._get_random_user_agent()}
        try:
            self.session.get(
                "https://www.vivino.com/explore",
                headers=headers,
                timeout=30,
            )
        except requests.RequestException:
            pass  # Continue anyway

    def _make_request(self, params: dict) -> Optional[dict]:
        """
        Make a request to Vivino API with retry logic.

        Args:
            params: Query parameters for the API

        Returns:
            JSON response or None on failure
        """
        headers = {"User-Agent": self._get_random_user_agent()}

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(
                    self.BASE_URL,
                    params=params,
                    headers=headers,
                    timeout=30,
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    # Rate limited
                    print(f"\n  Rate limited. Waiting {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                    continue
                elif response.status_code == 403:
                    print(f"\n  Access forbidden (403). Trying different User-Agent...")
                    headers = {"User-Agent": self._get_random_user_agent()}
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    print(f"\n  HTTP {response.status_code}. Retrying...")
                    time.sleep(MIN_DELAY * (attempt + 1))

            except requests.RequestException as e:
                print(f"\n  Request failed: {e}. Retrying...")
                time.sleep(MIN_DELAY * (attempt + 1))

        return None

    def _parse_wine_record(self, match: dict, wine_type_name: str) -> Optional[dict]:
        """
        Parse a single wine match from API response.

        Args:
            match: Single match from API response
            wine_type_name: Name of wine type (Red, White, etc.)

        Returns:
            Parsed wine record dict or None
        """
        try:
            vintage = match.get("vintage", {})
            wine = vintage.get("wine", {})
            statistics = vintage.get("statistics", {})
            prices = match.get("prices", [])
            winery = wine.get("winery", {})
            region = wine.get("region", {})
            country = region.get("country", {})

            # Extract values
            wine_id = str(wine.get("id", ""))
            if not wine_id:
                return None

            # Skip if already scraped
            if wine_id in self.scraped_wine_ids:
                return None

            ratings_count = statistics.get("ratings_count", 0)
            if ratings_count < self.min_reviews:
                return None

            rating = statistics.get("ratings_average", 0)
            if not rating or rating <= 0:
                return None

            wine_name = wine.get("name", "")
            winery_name = winery.get("name", "")
            year = vintage.get("year", "")

            # Construct full wine name with vintage
            full_name = f"{wine_name} {year}" if year else wine_name

            price = prices[0].get("amount", "") if prices else ""
            country_name = country.get("name", "")
            region_name = region.get("name", "")

            return {
                "Winery": winery_name,
                "Year": year,
                "Wine ID": wine_id,
                "Wine": full_name,
                "Rating": rating,
                "num_review": ratings_count,
                "price": price,
                "Country": country_name,
                "Region": region_name,
                "Wine Type": wine_type_name,
            }

        except Exception as e:
            return None

    def scrape_country(
        self,
        country_code: str,
        test_mode: bool = False,
        resume_from: Optional[dict] = None,
    ) -> dict:
        """
        Scrape all wines from a specific country.

        Args:
            country_code: Two-letter country code
            test_mode: If True, only scrape 10 wines per type
            resume_from: Checkpoint dict to resume from

        Returns:
            Statistics dict with counts
        """
        country_name = COUNTRIES.get(country_code, country_code.upper())
        print(f"\n{'='*60}")
        print(f"Scraping: {country_name} ({country_code})")
        print(f"{'='*60}")

        stats = {
            "country": country_code,
            "wines_scraped": 0,
            "wines_skipped": 0,
            "pages_scraped": 0,
            "errors": 0,
            "api_empty": False,
        }

        # Determine starting point
        start_wine_type = 1
        start_page = 1
        if resume_from and resume_from.get("country") == country_code:
            start_wine_type = resume_from.get("wine_type", 1)
            start_page = resume_from.get("page", 1)
            print(f"Resuming from: wine_type={start_wine_type}, page={start_page}")

        # CSV file for this country
        csv_path = self.output_dir / f"vivino_{country_code}.csv"
        file_exists = csv_path.exists()

        with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_COLUMNS)
            if not file_exists:
                writer.writeheader()

            for wine_type_id, wine_type_name in WINE_TYPES.items():
                if wine_type_id < start_wine_type:
                    continue

                page = start_page if wine_type_id == start_wine_type else 1
                wines_for_type = 0
                consecutive_empty = 0

                print(f"\n  {wine_type_name} wines...")

                # First request to get total count
                params = {
                    "country_codes[]": country_code,
                    "wine_type_ids[]": wine_type_id,
                    "min_rating": 1,
                    "order_by": "ratings_count",
                    "order": "desc",
                    "page": page,
                }

                initial_response = self._make_request(params)
                if not initial_response:
                    print(f"    Failed to get initial response")
                    stats["errors"] += 1
                    continue

                total_matches = initial_response.get("explore_vintage", {}).get("records_matched", 0)
                total_pages = (total_matches // 25) + 1

                if total_matches == 0:
                    print(f"    API returned 0 results (may be blocking)")
                    stats["api_empty"] = True
                    continue

                print(f"    Found {total_matches:,} wines ({total_pages:,} pages)")

                while True:
                    if test_mode and wines_for_type >= 10:
                        print(f"    Test mode: stopping after {wines_for_type} wines")
                        break

                    params["page"] = page
                    response = self._make_request(params)

                    if not response:
                        stats["errors"] += 1
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            print(f"    Too many consecutive failures, moving on")
                            break
                        page += 1
                        continue

                    matches = response.get("explore_vintage", {}).get("matches", [])
                    if not matches:
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            break
                        page += 1
                        continue

                    consecutive_empty = 0
                    wines_this_page = 0

                    for match in matches:
                        record = self._parse_wine_record(match, wine_type_name)
                        if record:
                            writer.writerow(record)
                            self.scraped_wine_ids.add(record["Wine ID"])
                            wines_this_page += 1
                            wines_for_type += 1
                            stats["wines_scraped"] += 1
                        else:
                            stats["wines_skipped"] += 1

                    stats["pages_scraped"] += 1

                    # Progress update
                    progress_pct = min(100, (page / total_pages) * 100)
                    print(f"\r    Page {page}/{total_pages} ({progress_pct:.1f}%) - "
                          f"{wines_for_type:,} wines", end="", flush=True)

                    # Save checkpoint
                    self._save_checkpoint(country_code, wine_type_id, page, stats["wines_scraped"])

                    # Save wine IDs periodically
                    if stats["wines_scraped"] % 1000 == 0:
                        self._save_wine_ids()

                    page += 1

                    # Rate limiting
                    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

                print(f"\n    {wine_type_name}: {wines_for_type:,} wines")

                # Reset start_page for next wine type
                start_page = 1

        # Save final state
        self._save_wine_ids()

        return stats

    def scrape_all(self, test_mode: bool = False, countries: Optional[list] = None, resume: bool = False):
        """
        Scrape wines from all configured countries.

        Args:
            test_mode: If True, only scrape 10 wines per type per country
            countries: List of country codes to scrape (None = all)
            resume: If True, resume from checkpoint
        """
        target_countries = countries if countries else list(COUNTRIES.keys())

        print(f"\nVivino Global Scraper")
        print(f"{'='*60}")
        print(f"Target countries: {', '.join(target_countries)}")
        print(f"Output directory: {self.output_dir}")
        print(f"Minimum reviews: {self.min_reviews}")
        print(f"Test mode: {test_mode}")
        print(f"{'='*60}")

        # Initialize session with cookies
        self._init_session()

        all_stats = []
        resume_checkpoint = self.checkpoint if resume else None
        any_api_empty = False

        # Determine starting country
        start_idx = 0
        if resume and resume_checkpoint:
            resume_country = resume_checkpoint.get("country")
            if resume_country in target_countries:
                start_idx = target_countries.index(resume_country)
                print(f"\nResuming from country: {resume_country}")

        for i, country_code in enumerate(target_countries[start_idx:], start=start_idx):
            # Use checkpoint only for the first country if resuming
            checkpoint_for_country = resume_checkpoint if i == start_idx and resume else None

            stats = self.scrape_country(
                country_code,
                test_mode=test_mode,
                resume_from=checkpoint_for_country,
            )
            all_stats.append(stats)

            if stats.get("api_empty"):
                any_api_empty = True

            # Log to file
            self._log_stats(stats)

        # Clear checkpoint on successful completion
        self._clear_checkpoint()

        # Print summary
        self._print_summary(all_stats)

        # If API returned empty results, show alternatives
        if any_api_empty:
            _print_alternatives()

    def _log_stats(self, stats: dict):
        """Append stats to scrape log file."""
        log_entry = {
            **stats,
            "timestamp": datetime.now().isoformat(),
        }

        log_data = []
        if SCRAPE_LOG_FILE.exists():
            with open(SCRAPE_LOG_FILE, 'r') as f:
                log_data = json.load(f)

        log_data.append(log_entry)

        with open(SCRAPE_LOG_FILE, 'w') as f:
            json.dump(log_data, f, indent=2)

    def _print_summary(self, all_stats: list):
        """Print summary of all scraping stats."""
        print(f"\n{'='*60}")
        print("SCRAPING SUMMARY")
        print(f"{'='*60}")

        total_wines = sum(s["wines_scraped"] for s in all_stats)
        total_skipped = sum(s["wines_skipped"] for s in all_stats)
        total_pages = sum(s["pages_scraped"] for s in all_stats)
        total_errors = sum(s["errors"] for s in all_stats)

        print(f"\nTotal wines scraped: {total_wines:,}")
        print(f"Total wines skipped: {total_skipped:,}")
        print(f"Total pages scraped: {total_pages:,}")
        print(f"Total errors: {total_errors}")

        print(f"\nBy country:")
        for stats in all_stats:
            country_name = COUNTRIES.get(stats["country"], stats["country"])
            print(f"  {country_name}: {stats['wines_scraped']:,} wines")

        print(f"\nUnique wine IDs tracked: {len(self.scraped_wine_ids):,}")

    def show_status(self):
        """Show current scraping status and progress."""
        print(f"\n{'='*60}")
        print("SCRAPING STATUS")
        print(f"{'='*60}")

        # Show checkpoint info
        if self.checkpoint:
            print(f"\nCheckpoint:")
            print(f"  Country: {self.checkpoint.get('country', 'N/A')}")
            print(f"  Wine type: {WINE_TYPES.get(self.checkpoint.get('wine_type'), 'N/A')}")
            print(f"  Page: {self.checkpoint.get('page', 'N/A')}")
            print(f"  Total wines: {self.checkpoint.get('total_wines', 'N/A'):,}")
            print(f"  Timestamp: {self.checkpoint.get('timestamp', 'N/A')}")
        else:
            print("\nNo checkpoint found (fresh start)")

        # Show wine IDs count
        print(f"\nUnique wines tracked: {len(self.scraped_wine_ids):,}")

        # Show existing CSV files
        csv_files = list(self.output_dir.glob("vivino_*.csv"))
        if csv_files:
            print(f"\nExisting CSV files:")
            total_wines = 0
            for csv_file in sorted(csv_files):
                line_count = sum(1 for _ in open(csv_file)) - 1  # Subtract header
                total_wines += line_count
                print(f"  {csv_file.name}: {line_count:,} wines")
            print(f"  Total: {total_wines:,} wines")
        else:
            print("\nNo CSV files found in output directory")

        # Show legacy CSV info
        if LEGACY_CSV.exists():
            legacy_count = sum(1 for _ in open(LEGACY_CSV)) - 1
            print(f"\nLegacy data available:")
            print(f"  {LEGACY_CSV.name}: {legacy_count:,} wines")
            print(f"  Run --convert-legacy to use this data")

        # Show log summary
        if SCRAPE_LOG_FILE.exists():
            with open(SCRAPE_LOG_FILE, 'r') as f:
                log_data = json.load(f)
            if log_data:
                print(f"\nRecent scraping activity:")
                for entry in log_data[-5:]:
                    country_name = COUNTRIES.get(entry["country"], entry["country"])
                    print(f"  {entry['timestamp']}: {country_name} - {entry['wines_scraped']:,} wines")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape wine data from Vivino for all major wine-producing countries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--country", "-c",
        type=str,
        help=f"Comma-separated country codes to scrape (available: {', '.join(COUNTRIES.keys())})",
    )
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="Test mode: scrape only 10 wines per type per country",
    )
    parser.add_argument(
        "--resume", "-r",
        action="store_true",
        help="Resume from last checkpoint",
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Show current scraping status",
    )
    parser.add_argument(
        "--check-api",
        action="store_true",
        help="Test API connectivity without scraping",
    )
    parser.add_argument(
        "--convert-legacy",
        action="store_true",
        help="Convert existing vivino.csv to new format",
    )
    parser.add_argument(
        "--min-reviews",
        type=int,
        default=10,
        help="Minimum number of reviews required (default: 10)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        help="Output directory for CSV files",
    )

    args = parser.parse_args()

    # Handle special commands first
    if args.check_api:
        check_api_connectivity()
        return

    if args.convert_legacy:
        convert_legacy_csv()
        return

    # Set output directory
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR

    # Initialize scraper
    scraper = VivinoScraper(output_dir=output_dir, min_reviews=args.min_reviews)

    if args.status:
        scraper.show_status()
        return

    # Parse countries
    countries = None
    if args.country:
        countries = [c.strip().lower() for c in args.country.split(",")]
        # Validate country codes
        invalid = [c for c in countries if c not in COUNTRIES]
        if invalid:
            print(f"Invalid country codes: {', '.join(invalid)}")
            print(f"Available: {', '.join(COUNTRIES.keys())}")
            sys.exit(1)

    # Run scraper
    scraper.scrape_all(
        test_mode=args.test,
        countries=countries,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
