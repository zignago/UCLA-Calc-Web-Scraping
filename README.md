
scraper.py — a clean Python script that:

  1. Calls UCLA's own public API (api.ucla.edu/sis/publicapis/course/...) — the same API the registrar's website uses internally. No browser, no login, no scraping of HTML.
  2. Searches for "Mathematics 31A" across all course descriptions in one API call.
  3. Post-filters with a regex to confirm the match is real.
  4. Exports a formatted Excel spreadsheet (+ optional CSV).

  The result: 52 courses across 17 subject areas, including Chemistry 20A/20B, Physics 1A/1AH, Economics 11/41, Astronomy 81/82, Civil Engineering 91, and others. They span lower-division, upper-division, and graduate levels.

  ---
  How to run it

  # Default — fast (5 seconds), saves Excel
  python3 scraper.py

  # Also save a CSV
  python3 scraper.py --csv

  # Custom output filename
  python3 scraper.py --out results.xlsx

  # Slower thorough mode (fetches all ~200 subject areas individually, ~5 min)
  python3 scraper.py --all-subjects

  The output files are already in your project folder:
  - ucla_courses_requiring_calc1.xlsx
  - ucla_courses_requiring_calc1.csv

  Sources used during investigation:
  - [UCLA Course Descriptions](https://registrar.ucla.edu/academics/course-descriptions)
  - [Department & Subject Area Codes](https://registrar.ucla.edu/faculty-staff/courses-and-programs/department-and-subject-area-codes)
  - [UCLA API Developer Portal](https://developer.api.ucla.edu/api-catalog)