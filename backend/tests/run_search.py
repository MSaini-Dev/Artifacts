import json

from backend.tools.dense_web_search import dense_web_search
query = "Latest AI and Generative AI news in October 2026"
result = dense_web_search(query, max_results_per_query=5, depth='deep')
print(json.dumps(result, indent=2))
