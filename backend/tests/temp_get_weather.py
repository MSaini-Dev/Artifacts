import json

from backend.tools.get_weather import get_weather
forecast = get_weather(26.9124,75.7873,3)
print(json.dumps(forecast, indent=2))
