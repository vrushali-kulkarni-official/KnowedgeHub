---
name: weather-lookup
version: 1.0.0
description: Look up the current weather for a given city.
author: your-name
requires:
  agent_version: ^1.0.0
inputs:
  type: object
  required: [city]
  properties:
    city:
      type: string
      description: Name of the city (e.g. "Paris")
    units:
      type: string
      enum: [celsius, fahrenheit]
      default: celsius
outputs:
  type: object
  required: [temperature, conditions]
  properties:
    temperature:
      type: number
    conditions:
      type: string
entry_point: main.py
tags: [weather, lookup, api]
examples:
  - input: { city: "Tokyo", units: "celsius" }
    output: { temperature: 22.0, conditions: "sunny" }
---

# Weather Lookup Skill

Looks up the current weather for a city using the OpenWeatherMap API.

## Usage

```python
from skills.example_skill.main import run

result = run({"city": "Paris", "units": "celsius"})
print(result)  # {"temperature": 18.0, "conditions": "cloudy"}
```

## Error handling

The skill returns an error dict on failure:

```python
result = run({"city": "Atlantis"})
# {"error": "city not found"}
```
