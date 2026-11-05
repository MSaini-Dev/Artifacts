"""
Ready-to-run test file.

Usage:
    python -m backend.tests.test_agent       -> runs single agent
    python -m backend.tests.test_agent multi -> runs multi agent
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from backend.agent.single_agent import call_agent
from backend.agent.multi_agent import call_multi_agent
USER_PROMPT = """You are an autonomous AI agent. I want to test your ability to create your own tools, execute them, and use them to complete a real task.

### Task: Build and Test a Web Search Tool

**Step 1: Create the Tool**
Create a Python tool named `dense_web_search.py` using the code provided below.
You have access to `create_tool(file_name, content)` which saves the tool to `backend/tools/dense_web_search.py` and registers it directly into your dynamic tool registry, or you can write it to `backend/tools/dense_web_search.py`.

The tool implementation to create:
```python
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
        return re.sub(r'\\s+', ' ', text).strip()
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

            title_match = re.search(r'class="result__title"[^>]*>(.*?)<\\/a>', block, re.DOTALL)
            title = ""
            if title_match:
                title = clean_html(title_match.group(1))

            snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)<\\/a>', block, re.DOTALL)
            snippet = ""
            if snippet_match:
                snippet = clean_html(snippet_match.group(1))
            else:
                snip_match2 = re.search(r'class="result__snippet"[^>]*>(.*?)<\\/div>', block, re.DOTALL)
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
    
    date_pattern = re.compile(r'\\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \\d{1,2},? \\d{4}\\b|\\b\\d{4}-\\d{2}-\\d{2}\\b', re.IGNORECASE)

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
```

### Step 2: Validate the Tool

After creating the file:
1. Check the Python syntax and fix any errors.
2. Verify that all required imports and functions are available.
3. Test the tool execution using your `execute_command` tool (e.g. `python -c "from backend.tools.dense_web_search import dense_web_search; print(dense_web_search('test', max_results_per_query=2))"`).
4. Verify that HTML parsing, URL deduplication, and result structures return valid results.
5. If the tool is registered in your tool registry, you can also test invoking it directly as a tool call.

Do not claim a test passed unless you actually executed it.

### Step 3: Execute a Real Web Search

Use the tool you created to research the following topic:

**"Latest AI and Generative AI news in October 2026"**

Run the search with `depth="deep"` and retrieve up to 5 results per query (`max_results_per_query=5`).

Use the actual `dense_web_search` function from the file you created. Do not replace the tool with your built-in knowledge or manually fabricate search results.

If the tool fails, inspect the error, attempt to fix the problem, and retry. If external access is blocked, report the limitation honestly.

### Step 4: Analyze the Results

Display the actual results returned by your tool in a readable format.

For each result, show:
- **Title**
- **Source/domain**
- **Publication date**, if available
- **URL**
- **Snippet**
- **Relevance to AI/Generative AI news**

Then provide a short summary of the three most important findings.

Clearly distinguish verified publication dates from dates inferred from snippets. Do not describe an article as recent unless its publication date or other reliable evidence supports that claim.

### Step 5: Demonstrate Autonomous Tool Usage

Show evidence that you:
1. Created the Python file in `backend/tools/dense_web_search.py`.
2. Executed and verified the tool successfully.
3. Passed the research query to the tool.
4. Received and processed its actual output.
5. Identified and fixed any errors encountered.

Include the actual command or function call used, the execution status, and a representative portion of the raw output.

### Final Report

Present your work in these sections:
1. **Tool Creation** — File path and implementation details.
2. **Validation Results** — Tests executed and their actual outcomes.
3. **Real Web Search** — The query and search depth used.
4. **Search Results** — Actual results returned by the tool.
5. **Key Findings** — A concise summary of the latest relevant news.
6. **Issues and Fixes** — Any errors, limitations, or corrections.
7. **Conclusion** — State whether you successfully created, tested, and used your own tool.

### Important Rules

- Actually create the file; do not merely print its code.
- Actually execute the file and use its functions.
- Do not simulate tool execution or invent results.
- Do not claim success without execution evidence.
- Do not silently substitute another search method if your tool fails.
- If a test fails, report the failure and explain what happened.
- Keep the final report clear, concise, and supported by actual execution evidence. """
 
 
def main():
    mode = "single"

    if len(sys.argv) > 1 and sys.argv[1].lower() in ("multi", "m"):
        mode = "multi"

    print(f"\nMode selected: {mode.upper()}")
    print("Prompt length:", len(USER_PROMPT), "chars\n")

    if mode == "multi":
        result = call_multi_agent(USER_PROMPT, verbose=True)
    else:
        result = call_agent(
            USER_PROMPT,
            max_turns=1000,
            verbose=True
        )

    print("\n" + "=" * 60)
    print("FINAL RESULT")
    print("=" * 60)
    print(result)


if __name__ == "__main__":
    main()