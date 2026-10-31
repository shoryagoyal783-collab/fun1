# Trump Table — multiplayer team card game

A Flask + Socket.IO real-time card game for four players in two fixed teams:
- Team A: seats 1 and 3
- Team B: seats 2 and 4

## Run locally
1. Install Python 3.10+.
2. In this folder run:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   python app.py
   ```
3. Open http://localhost:5000 in four browser sessions. Register four accounts, create a room, and join using its code.

## Deploy on Render
1. Push this folder to a GitHub repository.
2. In Render, choose **New + → Blueprint** and connect that repository.
3. Render reads `render.yaml`, installs dependencies, and starts the web service.
4. After deployment, open the Render URL and share it with three friends.

The included Render blueprint mounts a persistent disk at `/var/data` for the SQLite wallet database. Persistent disks may require a paid Render plan; if your plan does not support disks, change `DATABASE_PATH` to `game.db` and understand that wallet data may reset on redeploy/restart.

## Current game rules / implementation notes
- Registering an account starts it with 1,000 virtual credits.
- Host creates a private five-character room and sets a minimum team wager.
- Four players join. Host deals five cards to each player.
- One randomly selected player chooses Clubs, Spades, Diamonds, or Hearts as trump.
- The remaining 32 cards are dealt (eight more per player).
- Each team submits one wager. The two wagers form the virtual pot. The winning team splits the pot equally.
- 13 tricks are played. Players must follow the suit led when they can. Trump beats non-trump; otherwise the highest card in the led suit wins. Rank order: 2 low through Ace high.
- Team A is seats 1+3; Team B is seats 2+4.
- After a completed game, a player from the winning team is selected as first trump chooser in the next game.

## Important limitations before public launch
This is a playable starter, not a production-money platform. Credits are virtual only. It currently keeps active rooms in server memory, so a server restart ends active games; use a single Render instance for this starter. It does not yet include reconnect recovery, anti-cheat auditing, turn timers, or robust multi-instance scaling. The host can start the next game after the previous game ends.
