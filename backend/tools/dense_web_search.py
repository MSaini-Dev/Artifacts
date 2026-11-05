import json
import urllib.request
import urllib.parse
import re
from html.parser import HTMLParser
import time
from datetime import datetime

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, data):
        self.text.append(data)
    def get_text(self):
        return "".join(self.text)

def clean_html(raw_html):
    if not raw_html:
        return ""
    try:
        parser = HTMLTextExtractor()
        parser.feed(raw_html)
        text = parser.get_text()
        return re.sub(r'\s+', ' ', text).strip()
    except Exception:
        return re.sub(r'<[^>]+>', '', raw_html).strip()

def search_duckduckgo_html(query, max_results=10):
    results = []
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        blocks = html.split('class="result ')
        for block in blocks[1:]:
            if len(results) >= max_results:
                break
            
            url_match = re.search(r'class="result__url"[^>]*href="([^"]+)"', block)
            if not url_match:
                url_match = re.search(r'class="result__snippet"[^>]*href="([^"]+)"', block)
            
            target_url = ""
            if url_match:
                raw_url = url_match.group(1)
                if "uddg=" in raw_url:
                    parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
                    if "uddg" in parsed_q:
                        target_url = parsed_q["uddg"][0]
                elif raw_url.startswith("http"):
                    target_url = raw_url

            title_match = re.search(r'class="result__title"[^>]*>(.*?)<\/a>', block, re.DOTALL)
            title = ""
            if title_match:
                title = clean_html(title_match.group(1))

            snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)<\/a>', block, re.DOTALL)
            snippet = ""
            if snippet_match:
                snippet = clean_html(snippet_match.group(1))
            else:
                snip_match2 = re.search(r'class="result__snippet"[^>]*>(.*?)<\/div>', block, re.DOTALL)
                if snip_match2:
                    snippet = clean_html(snip_match2.group(1))

            if target_url and (title or snippet):
                domain = ""
                try:
                    parsed_uri = urllib.parse.urlparse(target_url)
                    domain = parsed_uri.netloc
                except Exception:
                    domain = ""

                results.append({
                    "title": title or target_url,
                    "url": target_url,
                    "source": domain,
                    "snippet": snippet,
                    "publication_date": None,
                    "engine": "duckduckgo_html"
                })
    except Exception as e:
        print(f"DuckDuckGo HTML search error for '{query}': {e}")
    return results

def search_duckduckgo_api(query, max_results=10):
    results = []
    try:
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8', errors='ignore'))
            
            for topic in data.get('RelatedTopics', []):
                if len(results) >= max_results:
                    break
                if 'Text' in topic and 'FirstURL' in topic:
                    t_url = topic['FirstURL']
                    t_text = topic['Text']
                    domain = ""
                    try:
                        domain = urllib.parse.urlparse(t_url).netloc
                    except Exception:
                        pass
                    results.append({
                        "title": t_text[:80] + "..." if len(t_text) > 80 else t_text,
                        "url": t_url,
                        "source": domain,
                        "snippet": t_text,
                        "publication_date": None,
                        "engine": "duckduckgo_api"
                    })
            
            for res in data.get('Results', []):
                if len(results) >= max_results:
                    break
                if 'Text' in res and 'FirstURL' in res:
                    t_url = res['FirstURL']
                    t_text = res['Text']
                    domain = ""
                    try:
                        domain = urllib.parse.urlparse(t_url).netloc
                    except Exception:
                        pass
                    results.append({
                        "title": t_text[:80] + "..." if len(t_text) > 80 else t_text,
                        "url": t_url,
                        "source": domain,
                        "snippet": t_text,
                        "publication_date": None,
                        "engine": "duckduckgo_api"
                    })
    except Exception as e:
        print(f"DuckDuckGo API search error for '{query}': {e}")
    return results

def dense_web_search(queries, max_results_per_query=10, depth="normal"):
    '''Accepts a natural-language research query or a list/string of queries.
    Supports multiple search queries for one research task.
    Searches the web using DuckDuckGo HTML and API fallback.
    Collects results from multiple sources, deduplicates URLs, extracts title, URL, source, snippet, publication date.
    Returns clean structured JSON string or dict.
    '''
    if isinstance(queries, str):
        base_query = queries.strip()
        query_list = [base_query]
        if depth in ["deep", "thorough"] and len(base_query.split()) > 2:
            query_list.append(f"{base_query} news 2026")
            query_list.append(f"{base_query} latest updates")
            query_list.append(f"{base_query} analysis")
    elif isinstance(queries, list):
        query_list = queries
    else:
        query_list = [str(queries)]

    all_raw_results = []
    for q in query_list:
        res = search_duckduckgo_html(q, max_results=max_results_per_query)
        if not res:
            res = search_duckduckgo_api(q, max_results=max_results_per_query)
        all_raw_results.extend(res)
        time.sleep(0.5)

    seen_urls = set()
    deduped_results = []
    
    date_pattern = re.compile(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b|\b\d{4}-\d{2}-\d{2}\b', re.IGNORECASE)

    for r in all_raw_results:
        url = r.get("url", "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        
        pub_date = r.get("publication_date")
        if not pub_date:
            combined_text = f"{r.get('title', '')} {r.get('snippet', '')}"
            match = date_pattern.search(combined_text)
            if match:
                pub_date = match.group(0)
        
        r["publication_date"] = pub_date
        deduped_results.append(r)

    return {
        "query_input": queries,
        "queries_executed": query_list,
        "total_results": len(deduped_results),
        "results": deduped_results
    }
