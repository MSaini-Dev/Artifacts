import json, urllib.request, urllib.parse

def get_weather(lat: float, lon: float, days: int = 3) -> dict:
    """Fetch daily weather forecast from Open-Meteo.
    Returns a dict with keys: date, temperature_max, temperature_min, precipitation_probability, weathercode.
    """
    base_url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
        "timezone": "Asia/Kolkata",
        "forecast_days": days,
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.load(response)
    daily = data.get("daily", {})
    result = []
    for i, date in enumerate(daily.get("time", [])):
        result.append({
            "date": date,
            "temperature_max": daily.get("temperature_2m_max", [])[i],
            "temperature_min": daily.get("temperature_2m_min", [])[i],
            "precipitation_probability": daily.get("precipitation_probability_max", [])[i],
            "weathercode": daily.get("weathercode", [])[i],
        })
    return {"forecast": result}
