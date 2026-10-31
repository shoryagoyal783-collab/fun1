import os, random, sqlite3, threading
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, join_room, emit
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-before-deploying")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
DB = os.environ.get("DATABASE_PATH", "game.db")
games, lock = {}, threading.RLock()

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, password TEXT NOT NULL, credits INTEGER NOT NULL DEFAULT 1000
        )""")

init_db()

def user_info(username):
    with db() as c:
        row = c.execute("SELECT username, credits FROM users WHERE username=?", (username,)).fetchone()
        return dict(row) if row else None

def change_credits(username, amount):
    with db() as c:
        c.execute("UPDATE users SET credits=credits+? WHERE username=?", (amount, username))

def safe_game(g):
    public_players = [({"username": p["username"]} if p else None) for p in g["players"]]
    return {
        "code": g["code"], "host": g["host"], "players": public_players,
        "phase": g["phase"], "trump": g.get("trump"), "trump_picker": g.get("trump_picker"),
        "turn": g.get("turn"), "trick": g.get("trick", []),
        "trick_no": g.get("trick_no", 0), "scores": g.get("scores", [0,0]),
        "team_bids": g.get("team_bids", [None,None]), "pot": g.get("pot", 0),
        "base_stake": g["base_stake"], "winner": g.get("winner"),
        "message": g.get("message", "")
    }

def player_index(g, sid):
    for i, p in enumerate(g["players"]):
        if p and p["sid"] == sid: return i
    return None

def send_state(code):
    g = games.get(code)
    if not g: return
    public = safe_game(g)
    for i, p in enumerate(g["players"]):
        if p:
            socketio.emit("game_state", {**public, "you": i, "hand": g.get("hands", [[],[],[],[]])[i],
                                        "balance": user_info(p["username"])["credits"]}, room=p["sid"])

def make_deck():
    return [{"suit": s, "rank": r, "label": r+s[0]} for s in ["Clubs","Spades","Diamonds","Hearts"]
            for r in ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]]

def card_value(card):
    return ["2","3","4","5","6","7","8","9","10","J","Q","K","A"].index(card["rank"])

def start_game(g):
    deck = make_deck()
    random.shuffle(deck)
    g["hands"] = [deck[i*5:(i+1)*5] for i in range(4)]
    g["phase"] = "trump"
    # Previous winning team's member gets priority; otherwise random player.
    previous = g.get("next_picker")
    g["trump_picker"] = previous if previous is not None else random.randrange(4)
    g["trump"] = None
    g["message"] = "Five cards dealt. Waiting for the selected player to choose trump."
    send_state(g["code"])

def finish_game(g):
    winner = 0 if g["scores"][0] > g["scores"][1] else 1
    g["winner"] = winner
    g["phase"] = "finished"
    pot = g["pot"]
    team_members = [0,2] if winner == 0 else [1,3]
    # Split the virtual pot equally between the winning team.
    for i in team_members:
        change_credits(g["players"][i]["username"], pot // 2)
    g["next_picker"] = random.choice(team_members)
    g["message"] = f"Team {winner+1} won {g['scores'][winner]} tricks and received {pot} credits."
    send_state(g["code"])

def next_trick(g):
    if g["trick_no"] >= 13:
        finish_game(g); return
    g["trick"] = []
    g["turn"] = (g["leader"] + 1) % 4 if g["trick_no"] else g["leader"]
    g["message"] = f"Trick {g['trick_no']+1}: play a card."
    send_state(g["code"])

@app.route("/")
def index():
    return render_template("index.html")

@app.post("/api/register")
def register():
    data = request.get_json() or {}
    name, password = data.get("username","").strip(), data.get("password","")
    if len(name) < 3 or len(name) > 18 or len(password) < 4:
        return jsonify(error="Username must be 3–18 characters and password at least 4 characters."), 400
    try:
        with db() as c:
            c.execute("INSERT INTO users(username,password,credits) VALUES(?,?,1000)",
                      (name, generate_password_hash(password)))
    except sqlite3.IntegrityError:
        return jsonify(error="That username is already taken."), 409
    session["username"] = name
    return jsonify(user=user_info(name))

@app.post("/api/login")
def login():
    data = request.get_json() or {}
    with db() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (data.get("username","").strip(),)).fetchone()
    if not row or not check_password_hash(row["password"], data.get("password","")):
        return jsonify(error="Incorrect username or password."), 401
    session["username"] = row["username"]
    return jsonify(user=user_info(row["username"]))

@app.get("/api/me")
def me():
    name = session.get("username")
    return jsonify(user=user_info(name)) if name else (jsonify(error="Log in first."), 401)

@socketio.on("create_room")
def create_room(data):
    name = session.get("username")
    if not name:
        emit("notice", {"error":"Please log in first."}); return
    code = ''.join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=5))
    stake = max(10, min(10000, int(data.get("base_stake", 50))))
    with lock:
        games[code] = {"code":code, "host":name, "players":[None]*4, "phase":"lobby",
                       "base_stake":stake, "hands":[[],[],[],[]], "scores":[0,0],
                       "team_bids":[None,None], "pot":0, "trick_no":0, "trick":[],
                       "leader":0, "turn":0, "next_picker":None}
    join_room(code)
    games[code]["players"][0] = {"username": name, "sid": request.sid}
    emit("room_created", {"code":code})
    socketio.emit("lobby_state", safe_game(games[code]), room=code)
    emit("notice", {"message":"Room created. You are Player 1. Share the room code with three friends."})

@socketio.on("join_room")
def join_game(data):
    name = session.get("username")
    code = data.get("code","").upper().strip()
    if not name:
        emit("notice", {"error":"Please log in first."}); return
    with lock:
        g = games.get(code)
        if not g:
            emit("notice", {"error":"Room not found."}); return
        if any(p and p["username"] == name for p in g["players"]):
            emit("notice", {"error":"You are already in this room."}); return
        try: idx = g["players"].index(None)
        except ValueError:
            emit("notice", {"error":"Room is full."}); return
        g["players"][idx] = {"username":name, "sid":request.sid}
        join_room(code)
        emit("joined", {"code":code, "seat":idx})
        socketio.emit("lobby_state", safe_game(g), room=code)

@socketio.on("start_game")
def start(data):
    code = data.get("code")
    with lock:
        g = games.get(code)
        if not g or g["host"] != session.get("username"):
            emit("notice", {"error":"Only the host can start the game."}); return
        if any(p is None for p in g["players"]):
            emit("notice", {"error":"Four players are required."}); return
        if g["phase"] not in ("lobby","finished"):
            emit("notice", {"error":"A game is already in progress."}); return
        g["scores"]=[0,0]; g["team_bids"]=[None,None]; g["pot"]=0
        g["trick_no"]=0; g["leader"]=0; g["winner"]=None
        start_game(g)

@socketio.on("choose_trump")
def choose_trump(data):
    code, suit = data.get("code"), data.get("suit")
    with lock:
        g = games.get(code); idx = player_index(g, request.sid) if g else None
        if not g or g["phase"] != "trump" or idx != g["trump_picker"] or suit not in ["Clubs","Spades","Diamonds","Hearts"]:
            emit("notice", {"error":"It is not your turn to choose trump."}); return
        g["trump"] = suit
        deck = [c for h in g["hands"] for c in h]
        used = {c["label"] for c in deck}
        remaining = [c for c in make_deck() if c["label"] not in used]
        random.shuffle(remaining)
        for i in range(4): g["hands"][i].extend(remaining[i*8:(i+1)*8])
        g["phase"]="bidding"
        g["message"]="Trump selected. Each team must enter its wager."
        send_state(code)

@socketio.on("place_bid")
def place_bid(data):
    code, amount = data.get("code"), data.get("amount")
    with lock:
        g=games.get(code); idx=player_index(g,request.sid) if g else None
        if not g or g["phase"]!="bidding" or idx is None: return
        team = idx % 2
        if g["team_bids"][team] is not None:
            emit("notice", {"error":"Your team has already placed its wager."}); return
        try: amount=int(amount)
        except: amount=0
        members=[0,2] if team==0 else [1,3]
        max_amount=min(user_info(g["players"][i]["username"])["credits"] for i in members)*2
        if amount < g["base_stake"] or amount > max_amount or amount % 2:
            emit("notice", {"error":f"Wager must be an even amount between {g['base_stake']} and {max_amount} credits."}); return
        g["team_bids"][team]=amount
        if all(x is not None for x in g["team_bids"]):
            # Both teams' wagers form the pot; only winners receive it.
            g["pot"]=sum(g["team_bids"])
            # Deduct each team's wager equally from its two players.
            for team_id, wager in enumerate(g["team_bids"]):
                members = [0,2] if team_id == 0 else [1,3]
                for seat in members:
                    change_credits(g["players"][seat]["username"], -(wager // 2))
            g["phase"]="playing"
            g["leader"]=random.randrange(4)
            g["turn"]=g["leader"]
            g["message"]="Wagers locked. Play 13 tricks!"
        send_state(code)

@socketio.on("play_card")
def play_card(data):
    code, label = data.get("code"), data.get("label")
    with lock:
        g=games.get(code); idx=player_index(g,request.sid) if g else None
        if not g or g["phase"]!="playing" or idx != g["turn"]: 
            emit("notice", {"error":"It is not your turn."}); return
        hand=g["hands"][idx]
        card=next((c for c in hand if c["label"]==label),None)
        if not card:
            emit("notice", {"error":"That card is not in your hand."}); return
        if g["trick"]:
            lead=g["trick"][0]["card"]["suit"]
            if any(c["suit"]==lead for c in hand) and card["suit"]!=lead:
                emit("notice", {"error":"You must follow the suit led if you can."}); return
        hand.remove(card)
        g["trick"].append({"player":idx,"card":card})
        if len(g["trick"]) < 4:
            g["turn"]=(idx+1)%4
            send_state(code); return
        lead=g["trick"][0]["card"]["suit"]
        def strength(entry):
            c=entry["card"]
            return (2 if c["suit"]==g["trump"] else 1 if c["suit"]==lead else 0, card_value(c))
        winner=max(g["trick"],key=strength)["player"]
        g["scores"][winner%2]+=1
        g["leader"]=winner
        g["trick_no"]+=1
        g["message"]=f"Player {winner+1} won trick {g['trick_no']}."
        send_state(code)
        if g["trick_no"]==13:
            finish_game(g)
        else:
            g["trick"]=[]
            g["turn"]=winner
            send_state(code)

@socketio.on("disconnect")
def disconnect():
    # Keep seats reserved during a temporary disconnect; a refresh can rejoin by username.
    pass

if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
