"""CLI for contact crawler.

Usage examples:
  python crawl.py https://example.com
  python crawl.py --input urls.txt --output results/output.json
"""
import argparse
import json
from src.contact_crawler import crawl_url
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('urls', nargs='*', help='One or more URLs')
    p.add_argument('--input', '-i', help='File with URLs, one per line')
    p.add_argument('--output', '-o', help='Output JSON file', default='results/output.json')
    args = p.parse_args()

    urls = []
    if args.input:
        urls = [l.strip() for l in Path(args.input).read_text(encoding='utf-8').splitlines() if l.strip()]
    urls += args.urls
    if not urls:
        p.error('No URLs provided')

    results = []
    for u in urls:
        try:
            print(f'Crawling {u} ...')
            res = crawl_url(u)
            results.append(res)
        except Exception as e:
            print(f'Error crawling {u}: {e}')
            results.append({'url': u, 'error': str(e)})

    outp = Path(args.output)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print('Saved', outp)


if __name__ == '__main__':
    main()
