const order=["internet","aviation","freight","electricity","energy"];
const labels={internet:"TIETOLIIKENNE",aviation:"LENTOLIIKENNE",freight:"MERIRAHTI",electricity:"SÄHKÖVIRTA",energy:"ENERGIAVIRTA"};

function updateClock(){
  const now=new Date();
  document.getElementById("date").textContent=now.toLocaleDateString("fi-FI",{timeZone:"Europe/Helsinki",day:"2-digit",month:"2-digit",year:"numeric"});
  document.getElementById("time").textContent=now.toLocaleTimeString("fi-FI",{timeZone:"Europe/Helsinki",hour:"2-digit",minute:"2-digit",second:"2-digit"});
}
function fmtChange(v){if(v==null)return "VERTAILU —";return `${v>0?"+":""}${v.toFixed(1)} %`;}
function stateLabel(s){return {normal:"NORMAALI",watch:"TARKKAILU",anomaly:"POIKKEAMA",low_watch:"TAVANOMAISTA HILJAISEMPI",low_anomaly:"POIKKEUKSELLISEN HILJAINEN",high_watch:"TAVANOMAISTA VILKKAAMPI",high_anomaly:"POIKKEUKSELLISEN VILKAS",baseline:"VERTAILUTASO",unavailable:"EI SAATAVILLA"}[s]||s.toUpperCase();}
function render(data){
  const root=document.getElementById("flows");root.innerHTML="";
  order.forEach(key=>{
    const f=data.flows?.[key]||{status:"unavailable",state:"unavailable"};
    const row=document.createElement("article");row.className="flow";
    const unavailable=f.status!=="ok";
    const quality=key==="energy"&&f.status==="ok"?`<br>${f.temporal_profile||"HIDAS TAUSTATILA"} · LUOTTAMUS ${f.confidence||"—"}<br>ÖLJY ${f.oil_updated||"—"} · KAASU ${f.gas_updated||"—"} · NOPEA ${f.fast_updated||"—"}`:"";
    const anomalous=["low_anomaly","high_anomaly"].includes(f.state);
    row.innerHTML=`<div><div class="flow-name">${labels[key]}</div><div class="flow-meta">${f.scope||""}<br>${f.provider||""}${quality}</div></div><div class="flow-value ${unavailable?"unavailable":""}">${unavailable?"—":(f.display_value??f.value)}</div><div class="flow-change">${fmtChange(f.change_pct)}</div><div class="flow-state ${anomalous?"alert":""}">${stateLabel(unavailable?"unavailable":f.state)}</div>`;
    root.appendChild(row);
  });
  document.getElementById("systemState").textContent=stateLabel(data.system_state||"baseline");
  const stamp=data.generated_at?new Date(data.generated_at).toLocaleString("fi-FI",{timeZone:"Europe/Helsinki",day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}):"—";
  document.getElementById("updated").textContent=`PÄIVITETTY ${stamp}`;
}
async function load(path="data/latest.json"){
  const note=document.getElementById("archiveNote");
  try{const r=await fetch(`${path}?v=${Date.now()}`);if(!r.ok)throw new Error(r.status);render(await r.json());note.textContent="";}catch(e){note.textContent="HAVAINTOA EI LÖYTYNYT";}
}
document.getElementById("archiveForm").addEventListener("submit",e=>{e.preventDefault();const d=document.getElementById("archiveDate").value;if(d)load(`data/history/${d}.json`);});
document.getElementById("todayButton").addEventListener("click",()=>load());
updateClock();setInterval(updateClock,1000);load();
