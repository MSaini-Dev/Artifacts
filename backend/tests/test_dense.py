import json

from backend.tools.dense_web_search import dense_web_search
result = dense_web_search('test', max_results_per_query=2)
print(json.dumps(result, indent=2))
