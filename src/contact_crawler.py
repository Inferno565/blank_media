"""contact_crawler: HTML-only heuristics to extract visible contact details.

This module provides functions to fetch a URL, parse the DOM while skipping
hidden/script/style/template content, and extract social links, emails,
phones, and name candidates using DOM heuristics only.
"""
from bs4 import BeautifulSoup, Comment
import requests
import re
from urllib.parse import urljoin, urlparse
import phonenumbers

SOCIAL_DOMAINS = [
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "github.com",
    "behance.net",
    "t.me",
    "wa.me",
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
# Very permissive phone-like regex: +country optional, digits, spaces, punctuation
PHONE_RE = re.compile(r"(\+\d{1,3}[\s\-\.]*)?(?:\(?\d{2,4}\)?[\s\-\.]*)?\d[\d\s\-\.]{6,20}\d")


def fetch_html(url, timeout=15):
    headers = {"User-Agent": "contact-crawler/1.0 (+https://example)"}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text, r.url


def _is_hidden(elem):
    # Check inline style and aria-hidden and hidden attribute
    if not elem:
        return False
    # walk up parents
    for el in elem.parents if hasattr(elem, 'parents') else []:
        if getattr(el, 'name', None) == 'template':
            return True
        try:
            style = el.get('style', '') or ''
            if 'display:none' in style.replace(' ', '').lower():
                return True
        except Exception:
            pass
        if el.get('aria-hidden') == 'true':
            return True
        if el.has_attr('hidden'):
            return True
    # also check self
    try:
        style = elem.get('style', '') or ''
        if 'display:none' in style.replace(' ', '').lower():
            return True
    except Exception:
        pass
    if elem.get('aria-hidden') == 'true':
        return True
    if elem.has_attr('hidden'):
        return True
    return False


def _visible_texts(soup):
    # Remove script/style/template and comments
    for s in soup(['script', 'style', 'noscript', 'iframe']):
        s.extract()
    # remove comments
    for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
        comment.extract()

    texts = []
    for elem in soup.find_all(text=True):
        parent = elem.parent
        if parent and parent.name in ['script', 'style', 'template']:
            continue
        # strip and ignore empty
        txt = elem.string
        if not txt:
            continue
        txt = txt.strip()
        if not txt:
            continue
        # skip if hidden by inline rules or ancestors
        if _is_hidden(parent):
            continue
        texts.append((parent, txt))
    return texts


def extract_socials(soup, base_url):
    found = []
    for a in soup.find_all('a'):
        href = a.get('href')
        if not href:
            # visible text may contain link, but we require href for social
            continue
        href_lower = href.lower()
        # normalize
        full = urljoin(base_url, href)
        for dom in SOCIAL_DOMAINS:
            if dom in href_lower:
                # avoid JS or mailto
                if href_lower.startswith('javascript:'):
                    continue
                found.append(full)
                break
    # dedupe while preserving order
    seen = set()
    out = []
    for u in found:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def extract_emails(soup):
    emails = set()
    # mailto
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if href.lower().startswith('mailto:'):
            addr = href.split(':', 1)[1].split('?')[0]
            addr = addr.strip()
            if EMAIL_RE.match(addr):
                if not _is_hidden(a):
                    emails.add(addr)
    # visible text
    for parent, txt in _visible_texts(soup):
        for m in EMAIL_RE.findall(txt):
            emails.add(m)
    return list(sorted(emails))


def extract_phones(soup):
    phones = []
    seen = set()
    # tel: links
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if href.lower().startswith('tel:'):
            num = href.split(':', 1)[1].split('?')[0]
            if _is_hidden(a):
                continue
            norm = _normalize_phone(num)
            if num not in seen:
                phones.append({"original": num, "normalized": norm})
                seen.add(num)
    # visible text
    for parent, txt in _visible_texts(soup):
        for m in PHONE_RE.findall(txt):
            # m may be tuple due to groups; get full match by searching
            match = PHONE_RE.search(txt)
            if not match:
                continue
            num = match.group(0).strip()
            # clean obvious punctuation
            if len(re.sub(r"\D", "", num)) < 7:
                continue
            if num in seen:
                continue
            if _is_hidden(parent):
                continue
            norm = _normalize_phone(num)
            phones.append({"original": num, "normalized": norm})
            seen.add(num)
    return phones


def _normalize_phone(num_str):
    s = num_str.strip()
    try:
        # try parsing with phonenumbers; allow region None so + formats work
        if s.startswith('+'):
            parsed = phonenumbers.parse(s, None)
        else:
            # try a default region heuristic: use 'IN' if number contains '91' or 'mumbai' not available
            parsed = phonenumbers.parse(s, 'IN')
        if phonenumbers.is_possible_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    # fallback: return digits-only as normalization
    digits = re.sub(r"\D", "", s)
    return digits


def extract_name_candidates(soup):
    candidates = []
    reasons = []

    def add_candidate(name, confidence, reason):
        candidates.append({"name": name.strip(), "confidence": confidence, "reason": reason})

    # 1. meta author
    ma = soup.find('meta', attrs={'name': 'author'})
    if ma and ma.get('content'):
        add_candidate(ma.get('content'), 0.9, 'meta[name=author]')

    # 2. page title
    title = soup.title.string if soup.title and soup.title.string else None
    if title:
        # sometimes title contains site - try to split by | or -
        parts = re.split(r"[|\-–—]\s*", title)
        if parts:
            add_candidate(parts[0], 0.5, 'title (first part)')

    # 3. headings near contact info: look for h1..h3, or nodes with class/id name/author/contact
    # find elements that contain an email or phone nearby (same parent)
    contact_nodes = set()
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if href.lower().startswith('mailto:') or href.lower().startswith('tel:'):
            contact_nodes.add(a.parent)

    # search for headings
    for tag in ['h1', 'h2', 'h3', 'h4']:
        for h in soup.find_all(tag):
            if _is_hidden(h):
                continue
            text = h.get_text(separator=' ', strip=True)
            if not text:
                continue
            # base confidence on tag
            base = 0.7 if tag == 'h1' else 0.6
            # if heading is sibling/parent of contact node, boost confidence
            boosted = False
            for cn in contact_nodes:
                try:
                    if cn and (cn == h.parent or cn in h.parents or h in cn.parents):
                        add_candidate(text, min(0.95, base + 0.25), f'{tag} near contact')
                        boosted = True
                        break
                except Exception:
                    pass
            if not boosted:
                add_candidate(text, base, tag)

    # 4. look for items with common class/id names
    keys = ['name', 'author', 'contact', 'founder', 'ceo', 'person']
    for k in keys:
        for el in soup.find_all(attrs={'class': re.compile(k, re.I)}):
            if _is_hidden(el):
                continue
            text = el.get_text(separator=' ', strip=True)
            if text and len(text) < 60:
                add_candidate(text, 0.75, f'class contains {k}')
        for el in soup.find_all(attrs={'id': re.compile(k, re.I)}):
            if _is_hidden(el):
                continue
            text = el.get_text(separator=' ', strip=True)
            if text and len(text) < 60:
                add_candidate(text, 0.8, f'id contains {k}')

    # dedupe by normalized name
    seen = set()
    out = []
    for c in sorted(candidates, key=lambda x: -x['confidence']):
        n = ' '.join(c['name'].split())
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(c)
    return out


def crawl_url(url):
    html, final = fetch_html(url)
    soup = BeautifulSoup(html, 'lxml')
    # remove templates early
    for t in soup.find_all('template'):
        t.extract()

    socials = extract_socials(soup, final)
    emails = extract_emails(soup)
    phones = extract_phones(soup)
    names = extract_name_candidates(soup)

    notes = []
    if not emails and not phones and not socials:
        notes.append('no contact items found (page may be JS-heavy or require interaction)')

    return {
        'url': final,
        'socials': socials,
        'emails': emails,
        'phones': phones,
        'name_candidates': names,
        'notes': notes,
    }


if __name__ == '__main__':
    import sys
    u = sys.argv[1]
    import json
    print(json.dumps(crawl_url(u), indent=2))
