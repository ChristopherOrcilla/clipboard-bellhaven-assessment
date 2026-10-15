"""Crawl every directory page AND homepage promotions. Read-only requests."""
import re
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from .util import utcnow

SITE = "https://analyst-assessment-production.up.railway.app"
CITY_LINE = re.compile(r"^(.+?),\s*([A-Z]{2})\s+(\d{5})(?:-\d{4})?$", re.I)
KNOWN_LABELS = {"address", "care offerings", "administrator", "phone", "contact", "website"}


def clean_lines(soup):
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return [x.strip() for x in soup.get_text("\n", strip=True).splitlines() if x.strip()]


def parse_detail(html, url):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if not h1:
        raise ValueError(f"Missing facility title at {url}")
    name = h1.get_text(" ", strip=True)
    lines = clean_lines(soup)
    try:
        ix = next(i for i, s in enumerate(lines) if s.lower() == "address")
    except StopIteration:
        raise ValueError(f"Missing address label at {url}")
    following = []
    for item in lines[ix+1:]:
        if item.lower() in KNOWN_LABELS:
            break
        following.append(item)
    street, city, state, zip_code = "", "", "", ""
    for i, line in enumerate(following):
        m = CITY_LINE.match(line)
        if m:
            city, state, zip_code = m.groups()
            street = ", ".join(following[:i])
            break
    if not (street and city and state and zip_code):
        raise ValueError(f"Can't parse complete postal address at {url}: {following}")
    offerings = []
    try:
        care_ix = next(i for i, s in enumerate(lines) if s.lower() == "care offerings")
        for line in lines[care_ix+1:]:
            if line.lower() in KNOWN_LABELS:
                break
            offerings.append(line)
    except StopIteration:
        pass
    # Some pages render combined offering labels as one text node.
    care_text = " ".join(offerings)
    kinds = [x for x in ["Assisted Living", "Memory Support", "Short-Term Rehabilitation & Nursing", "Independent Living"] if x.lower() in care_text.lower()]
    return {"name": name, "street": street, "city": city, "state": state.upper(), "zip": zip_code, "care_offerings": kinds or offerings, "source_url": url, "scraped_at": utcnow()}


def links_from(html, root=SITE):
    soup = BeautifulSoup(html, "html.parser")
    out = set()
    for a in soup.select('a[href]'):
        href = urljoin(root, a.get("href", ""))
        path = urlparse(href).path
        if urlparse(href).netloc != urlparse(root).netloc:
            continue
        if path.startswith("/communities/") and len(path.rstrip("/").split("/")) == 3:
            out.add(href.split("?")[0].rstrip("/"))
    return out


def scrape_all(base=SITE, session=None, min_expected=30):
    s = session or requests.Session()
    s.headers.update({"User-Agent": "BellhavenAssessmentReconciler/1.0 (read-only public site)"})

    def fetch(url):
        r = s.get(url, timeout=25)
        r.raise_for_status()
        return r.text

    links = set(links_from(fetch(base + "/"), base))
    pagination = 0
    expected = None
    # Crawl until 'next' is gone. Safety maximum protects against broken pagination.
    for page in range(1, 51):
        url = base + ("/communities" if page == 1 else f"/communities?page={page}")
        html = fetch(url)
        links |= links_from(html, base)
        soup = BeautifulSoup(html, "html.parser")
        txt = soup.get_text(" ", strip=True)
        counts = re.search(r"Page\s+\d+\s+of\s+(\d+)\s*[·•]\s*(\d+)\s+communities listed", txt, re.I)
        if counts:
            expected = int(counts.group(2))
        pagination += 1
        next_links = [a.get("href", "") for a in soup.select('a[href]') if "next" in a.get_text(" ", strip=True).lower() and "/communities" in a.get("href", "")]
        if not next_links:
            break
    else:
        raise RuntimeError("Pagination never ended; please inspect the public website")
    if expected is not None and len(links) < expected:
        raise RuntimeError(f"Found {len(links)} unique URLs, below advertised {expected}. No CRM proposals generated")
    if len(links) < min_expected:
        raise RuntimeError(f"Only {len(links)} facilities discovered; aborting to avoid mass incorrect unlisted proposals")
    facilities = [parse_detail(fetch(url), url) for url in sorted(links)]
    return {"facilities": facilities, "stats": {"directory_advertised": expected, "total_unique_facilities": len(facilities), "pages_crawled": pagination, "has_homepage_extras": len(facilities) > (expected or 0)}, "scraped_at": utcnow()}
