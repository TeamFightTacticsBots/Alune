# Structure and Purpose

```bash
tft/
  app.py        # App entry point; initializes dependencies and starts the game loop
  game.py       # Detects game state and controls when planning is executed

  planning/
    __init__.py
    planning.py # Orchestrates planning phase (economy → placing → items)
    economy.py  # Handles buying XP, rerolling, and gold management
    placing.py  # Handles selling units and enforcing board placement
    items.py    # Handles orb collection and item assignment
```
