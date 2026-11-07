# capri-pet

A small desktop companion that lives on your screen. Capri from Cyberpunk: Edgerunners 2 floats around above the taskbar, blinks, wanders, dances, sits on the taskbar, lies down and falls asleep if you leave the mouse alone. No AI, no API keys, just sprite animation.

Unofficial fan project. Not affiliated with CD PROJEKT RED, Studio Trigger or Netflix.

## Features
- Wanders, dances, grins, perches on the taskbar, lies down, sleeps and wakes up
- Drag her around (she dangles), click to poke, double click to dance
- Works across multiple monitors (drag her over, or right click > Next monitor)
- Right click menu with Quit

## Setup (Windows)
1. `pip install pillow`
2. Get the sprites. They are not included here because they aren't mine. Clone the original project and copy its `assets/sprites` folder next to `capri.py`:
   `git clone https://github.com/lachydotmcg/capri-desktop`
3. Your folder should look like:
   ```
   capri.py
   assets/sprites/idle.png ...
   ```
4. `python capri.py`

You can also run `python capri.py "C:\path\to\sprites"`.

## Settings
At the top of `capri.py`: `SCALE` (size), `HOVER`, `WALK_SPEED`, `SLEEP_AFTER`.

## Credits
Sprites and character art from [lachydotmcg/capri-desktop](https://github.com/lachydotmcg/capri-desktop).
