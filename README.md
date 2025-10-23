# Contact Crawler

Simple Python tool that fetches HTML and extracts visible contact details (social links, emails, phones, and name candidates) using DOM-only heuristics.

Setup

1. Create a virtualenv and install dependencies:

   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt

Run

Single URL:

python crawl.py https://www.libf.co/directory/libf-2025

From file:

python crawl.py --input urls.txt --output results/libf.json

Output

JSON with fields per page: url, socials, emails, phones, name_candidates, notes

Heuristics & limitations

- Only inspects HTML/DOM; no external site APIs or hidden JSON endpoints.
- Skips content inside <script>, <style>, <template>, and elements with inline style display:none or aria-hidden=true.
- Social links require an actual href containing the social domain; we do not infer from icon classes or background images.
- Phone/email visible text is extracted via regex; may include false positives on noisy pages.
- Name candidates use meta[name=author], title, headings, and elements with classes/ids like 'name' or 'author'. Confidence scores are heuristic.

Improvement ideas

1. Render JS with headless browser (playwright/selenium) to capture dynamically injected contact info.
2. Use context-based NLP (e.g., spaCy) to filter names and match person-name patterns.
