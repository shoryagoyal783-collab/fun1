const socket=io();let mode="login",currentCode=null,state=null,me=null;
const $=id=>document.getElementById(id);
function toast(t){const x=$("toast");x.textContent=t;x.style.display="block";setTimeout(()=>x.style.display="none",2800)}
async function api(path,data){const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});const j=await r.json();if(!r.ok)throw Error(j.error||"Something went wrong");return j}
document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{mode=b.dataset.mode;document.querySelectorAll(".tab").forEach(x=>x.classList.toggle("active",x===b));$("authBtn").textContent=mode==="login"?"Login":"Create account"});
$("authBtn").onclick=async()=>{try{const j=await api("/api/"+mode,{username:$("username").value,password:$("password").value});me=j.user;showLobby()}catch(e){$("authMsg").textContent=e.message}};
async function showLobby(){ $("auth").classList.add("hidden");$("lobby").classList.remove("hidden");$("account").textContent=me.username;$("wallet").textContent=me.credits}
async function refreshMe(){try{const j=await fetch("/api/me").then(r=>r.json());if(j.user){me=j.user;showLobby()}}catch(e){}}
$("createBtn").onclick=()=>socket.emit("create_room",{base_stake:$("baseStake").value});
$("joinBtn").onclick=()=>{currentCode=$("roomCode").value.toUpperCase();socket.emit("join_room",{code:currentCode})};
socket.on("room_created",d=>{currentCode=d.code;$("code").textContent=d.code;$("lobby").classList.add("hidden");$("table").classList.remove("hidden");toast("Room created: "+d.code);});
socket.on("joined",d=>{currentCode=d.code;$("code").textContent=d.code;$("lobby").classList.add("hidden");$("table").classList.remove("hidden")});
socket.on("notice",d=>toast(d.error||d.message));
socket.on("lobby_state",s=>render(s));
socket.on("game_state",s=>{state=s;render(s);if(s.balance!==undefined){$("wallet").textContent=s.balance;me.credits=s.balance}});
function render(s){
 state=s;$("code").textContent=s.code;$("phaseTitle").textContent=({lobby:"Waiting room",trump:"Choose the trump",bidding:"Place your wager",playing:"13 tricks",finished:"Game complete"})[s.phase]||"Trump Table";
 for(let i=0;i<4;i++){let el=$("seat"+(i+1)),p=s.players[i];el.querySelector("b").textContent=p?p.username+(i===s.you?" (you)":""):"Waiting…";el.style.borderColor=p&&i===s.you?"#c4f36a":"#ffffff2b"}
 $("trump").innerHTML="TRUMP<br><b>"+(s.trump?symbol(s.trump):"—")+"</b>";
 $("score").textContent=`TEAM A ${s.scores?.[0]||0} — ${s.scores?.[1]||0} TEAM B`;
 $("status").textContent=s.message||"Waiting for players…";
 $("trick").innerHTML=(s.trick||[]).map(t=>`<div class="played ${isRed(t.card.suit)?"red":""}">${t.card.rank}${symbol(t.card.suit)}<small style="display:block;font-size:9px">P${t.player+1}</small></div>`).join("");
 $("hostActions").classList.toggle("hidden",!(s.phase==="lobby"&&me&&s.host===me.username));
 $("trumpActions").classList.toggle("hidden",!(s.phase==="trump"&&s.you===s.trump_picker));
 $("bidActions").classList.toggle("hidden",s.phase!=="bidding"||s.team_bids?.[s.you%2]!==null);
 $("resultActions").classList.toggle("hidden",s.phase!=="finished");
 const hand=s.hand||[];$("handCount").textContent=`(${hand.length} cards)`;
 $("hand").innerHTML=hand.map(c=>`<button class="card ${isRed(c.suit)?"red":""}" data-label="${c.label}" ${s.phase!=="playing"||s.you!==s.turn?"disabled":""}><span>${c.rank}</span><span style="font-size:22px">${symbol(c.suit)}</span><small>${c.suit}</small></button>`).join("");
 document.querySelectorAll(".card").forEach(b=>b.onclick=()=>socket.emit("play_card",{code:currentCode,label:b.dataset.label}));
}
function symbol(s){return ({Clubs:"♣",Spades:"♠",Diamonds:"♦",Hearts:"♥"})[s]||s}
function isRed(s){return s==="Hearts"||s==="Diamonds"}
document.querySelectorAll("[data-suit]").forEach(b=>b.onclick=()=>socket.emit("choose_trump",{code:currentCode,suit:b.dataset.suit}));
$("bidBtn").onclick=()=>socket.emit("place_bid",{code:currentCode,amount:$("bidAmount").value});
$("startBtn").onclick=()=>socket.emit("start_game",{code:currentCode});
$("againBtn").onclick=()=>socket.emit("start_game",{code:currentCode});
$("copyBtn").onclick=()=>navigator.clipboard.writeText(currentCode).then(()=>toast("Room code copied"));
refreshMe();
