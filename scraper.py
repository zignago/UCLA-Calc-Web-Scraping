#!/usr/bin/env python3
"""
UCLA Course Catalog Scraper
============================
Finds all 2025-2026 UCLA courses whose description lists
Mathematics 31A (Calculus I) as a prerequisite and exports
them to an Excel spreadsheet.

No browser or special credentials needed — uses UCLA's own
public course-description API that powers the registrar website.

USAGE
-----
  python scraper.py                      # default: save to Excel
  python scraper.py --csv                # also save a CSV copy
  python scraper.py --out my_file.xlsx   # choose output filename
  python scraper.py --all-subjects       # slower: fetch every subject
                                         # area individually (more
                                         # thorough but takes ~5 min)
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# API endpoints (public, no auth required — UCLA registrar website uses these)
# ---------------------------------------------------------------------------
API_BASE = "https://api.ucla.edu/sis/publicapis/course"

# Returns list of all subject area codes  e.g. [{"subj_area_cd":"MATH","display_value":"Mathematics (MATH)"},...]
EP_ALL_SUBJECTS = f"{API_BASE}/getallcourses"

# Returns all courses for one subject area  ?subjectarea=MATH
EP_BY_SUBJECT = f"{API_BASE}/getcoursedetail"

# Full-text search across all course descriptions  ?searchquery=Mathematics+31A
EP_SEARCH = f"{API_BASE}/getcoursedetailbysearch"

# ---------------------------------------------------------------------------
# What to search for
# ---------------------------------------------------------------------------
# The UCLA catalog uniformly writes "Mathematics 31A" (never "Math 31A")
# in prerequisite lines, so one search term is sufficient.
SEARCH_QUERY = "Mathematics 31A"

# Regex for local post-filtering (catches rare variants like "Math. 31A")
_PREREQ_RE = re.compile(
    r'\b(?:Mathematics|Math\.?|MATH)\s+31A\b'
)

def mentions_math_31a(text: str) -> bool:
    return bool(_PREREQ_RE.search(text or ""))


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://registrar.ucla.edu/",
}

def fetch_json(url: str, retries: int = 3, backoff: float = 2.0) -> list | dict:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            print(f"  [HTTP {exc.code}] {url}", file=sys.stderr)
            if exc.code in (429, 503):
                time.sleep(backoff * (attempt + 1))
                continue
            raise
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(backoff)
                continue
            raise
    return []


# ---------------------------------------------------------------------------
# Strategy A — search endpoint (fast, ~1 second)
# ---------------------------------------------------------------------------
def search_strategy() -> list[dict]:
    """
    Call the search endpoint for "Mathematics 31A".
    This is what the registrar's own website does when you type in the
    search box — it searches all course descriptions at once.
    """
    url = f"{EP_SEARCH}?searchquery={SEARCH_QUERY.replace(' ', '+')}"
    print(f"  Querying: {url}")
    results = fetch_json(url)
    if not isinstance(results, list):
        print("  Unexpected response format.", file=sys.stderr)
        return []
    return results


# ---------------------------------------------------------------------------
# Strategy B — per-subject fetch (slow, ~5 min, more thorough)
# ---------------------------------------------------------------------------
def all_subjects_strategy() -> list[dict]:
    """
    Fetch every subject area individually and filter locally.
    Slower but guarantees we see every course description in the catalog.
    """
    subjects = fetch_json(EP_ALL_SUBJECTS)
    if not isinstance(subjects, list):
        print("Failed to load subject areas.", file=sys.stderr)
        return []

    print(f"  Found {len(subjects)} subject areas.")
    matching: list[dict] = []

    for i, subj in enumerate(subjects, start=1):
        code = subj.get("subj_area_cd", "").strip()
        name = subj.get("display_value", "").strip()
        print(f"  [{i:3d}/{len(subjects)}] {code:<12} {name}", end="")

        url = f"{EP_BY_SUBJECT}?subjectarea={urllib.parse.quote(code)}"
        try:
            courses = fetch_json(url)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            continue

        hits = [c for c in courses if mentions_math_31a(c.get("crs_desc", ""))]
        print(f"  → {len(hits)} match(es)" if hits else "")
        matching.extend(hits)
        time.sleep(0.3)  # polite delay

    return matching


# ---------------------------------------------------------------------------
# Normalise raw API records into clean rows
# ---------------------------------------------------------------------------
def normalise(courses: list[dict]) -> list[dict]:
    """
    Convert raw API dicts to clean output rows, keeping only relevant columns.
    Columns returned:
      subject_area  — e.g. "Chemistry (CHEM)"
      course_name   — e.g. "20A. Chemical Structure"
      units         — e.g. "4.0" or "2.0 to 4.0"
      level         — e.g. "Lower Division Courses"
      description   — full description text
    """
    rows = []
    seen: set[str] = set()  # deduplicate

    for c in courses:
        key = (
            c.get("subj_area_cd", "").strip(),
            c.get("course_title", "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)

        # Post-filter: make sure the description really mentions Math 31A
        desc = (c.get("crs_desc") or "").strip()
        if not mentions_math_31a(desc):
            continue

        rows.append({
            "subject_area":  (c.get("subj_area_nm") or "").strip(),
            "course_name":   (c.get("course_title") or "").strip(),
            "units":         str(c.get("unt_rng") or "").strip(),
            "level":         (c.get("crs_career_lvl_nm") or "").strip(),
            "description":   desc,
        })

    # Sort by subject area then course name for easy reading
    rows.sort(key=lambda r: (r["subject_area"], r["course_name"]))
    return rows


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def export_excel(rows: list[dict], path: Path) -> None:
    df = pd.DataFrame(rows, columns=[
        "subject_area", "course_name", "units", "level", "description"
    ])

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Math 31A Prereq Courses")
        ws = writer.sheets["Math 31A Prereq Courses"]

        # Auto-size columns (rough heuristic)
        col_widths = {"A": 35, "B": 45, "C": 8, "D": 28, "E": 90}
        for col_letter, width in col_widths.items():
            ws.column_dimensions[col_letter].width = width

        # Wrap text in description column
        from openpyxl.styles import Alignment
        for cell in ws["E"][1:]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

        # Freeze the header row
        ws.freeze_panes = "A2"

    print(f"  Saved {len(df)} courses → {path}")


def export_csv(rows: list[dict], path: Path) -> None:
    df = pd.DataFrame(rows, columns=[
        "subject_area", "course_name", "units", "level", "description"
    ])
    df.to_csv(path, index=False)
    print(f"  Saved CSV → {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find UCLA courses that require Mathematics 31A."
    )
    parser.add_argument(
        "--out", default="ucla_courses_requiring_calc1.xlsx",
        help="Output Excel filename (default: ucla_courses_requiring_calc1.xlsx)"
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="Also save a CSV copy alongside the Excel file."
    )
    parser.add_argument(
        "--all-subjects", dest="all_subjects", action="store_true",
        help=(
            "Fetch every subject area individually (slower, ~5 min) "
            "instead of using the search endpoint."
        )
    )
    args = parser.parse_args()

    print("UCLA Course Catalog Scraper")
    print("===========================")
    print(f"Looking for courses that list '{SEARCH_QUERY}' as a prerequisite.\n")

    # --- Fetch ---
    if args.all_subjects:
        print("Mode: Fetching all subject areas individually (slow but thorough)...")
        import urllib.parse  # needed in all_subjects_strategy
        raw = all_subjects_strategy()
    else:
        print("Mode: Search API (fast — takes ~5 seconds) ...")
        raw = search_strategy()

    if not raw:
        print("\nNo courses returned. Check your internet connection.")
        sys.exit(1)

    print(f"\n  Raw results from API: {len(raw)} courses")

    # --- Normalise & deduplicate ---
    rows = normalise(raw)
    print(f"  After dedup + filtering: {len(rows)} courses\n")

    if not rows:
        print("No courses matched after filtering. Unexpected — please report.")
        sys.exit(1)

    # --- Preview ---
    print("Preview (first 10 matches):")
    print(f"  {'Subject Area':<35} {'Course':<40} {'Units'}")
    print(f"  {'-'*35} {'-'*40} {'-'*5}")
    for r in rows[:10]:
        print(f"  {r['subject_area']:<35} {r['course_name']:<40} {r['units']}")
    if len(rows) > 10:
        print(f"  ... and {len(rows) - 10} more.\n")

    # --- Export ---
    out_path = Path(args.out)
    print(f"\nExporting ...")
    export_excel(rows, out_path)

    if args.csv:
        csv_path = out_path.with_suffix(".csv")
        export_csv(rows, csv_path)

    print("\nDone!")


if __name__ == "__main__":
    main()
