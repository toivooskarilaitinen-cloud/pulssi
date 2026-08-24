#!/usr/bin/env python3
import json, math, os, statistics, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"; HISTORY=DATA/"history"; OBS=DATA/"observations"
for directory in (DATA,HISTORY,OBS): directory.mkdir(parents=True,exist_ok=True)
UA="PULSSI/0.1 (+https://toivooskarilaitinen-cloud.github.io/pulssi/)"

def get_json(url,params=None,headers=None,timeout=35):
    if params: url += ("&" if "?" in url else "?")+urllib.parse.urlencode(params)
    request=urllib.request.Request(url,headers={"User-Agent":UA,**(headers or {})})
    with urllib.request.urlopen(request,timeout=timeout) as response:
        return json.load(response)

def result(value,display,provider,scope,source_updated=None,index=None):
    return {"status":"ok","value":float(value),"display_value":display,"provider":provider,"scope":scope,"source_updated":source_updated,"source_index":index}

def internet():
    token=os.getenv("CLOUDFLARE_API_TOKEN")
    if not token: raise RuntimeError("CLOUDFLARE_API_TOKEN puuttuu")
    data=get_json("https://api.cloudflare.com/client/v4/radar/http/timeseries",{"dateRange":"1d","aggInterval":"1h","format":"JSON"},{"Authorization":f"Bearer {token}"})
    series=data.get("result",{}).get("serie_0",{})
    values=[float(v) for v in series.get("values",[]) if v is not None]
    if not values: raise RuntimeError("Cloudflare ei palauttanut aikasarjaa")
    return result(values[-1],f"{values[-1]:.2f}","CLOUDFLARE RADAR","MAAILMAN HTTP-LIIKENNE")

def aviation():
    data=get_json("https://opensky-network.org/api/states/all",timeout=45)
    states=data.get("states") or []
    airborne=sum(1 for row in states if len(row)>8 and row[8] is False)
    if airborne<1: raise RuntimeError("OpenSky ei palauttanut ilma-aluksia")
    stamp=datetime.fromtimestamp(data.get("time",0),timezone.utc).isoformat()
    return result(airborne,f"{airborne:,}".replace(","," "),"OPENSKY NETWORK","HAVAITUT ILMASSA OLEVAT ALUKSET",stamp)

def freight():
    data=get_json("https://raw.githubusercontent.com/OCHA-DAP/hdx-portwatch-viz/main/data/ports.json")
    ratios=[]; calls=[]; dates=[]
    for port in data.get("ports",[]):
        item=data["port_data"].get(port,{})
        current=item.get("current") or []
        if not current: continue
        latest=max(current,key=lambda x:x["doy"])
        historical=next((x for x in item.get("hist",[]) if x["doy"]==latest["doy"]),None)
        if historical and historical.get("hist_avg"):
            ratios.append(latest["roll7"]/historical["hist_avg"]*100)
        calls.append(latest["roll7"]);dates.append(item.get("latest_date",""))
    if not ratios: raise RuntimeError("PortWatch-vertailua ei saatu")
    idx=statistics.median(ratios); total=sum(calls)
    return result(idx,f"{idx:.1f}","IMF PORTWATCH / HDX","VALITTUJEN SATAMIEN 7 PV INDEKSI",max(dates) if dates else None,index=idx)

def electricity():
    now=datetime.now(timezone.utc); start=(now-timedelta(days=2)).date().isoformat(); end=now.date().isoformat()
    data=get_json("https://api.energy-charts.info/public_power",{"country":"de","start":start,"end":end})
    load=next((x.get("data",[]) for x in data.get("production_types",[]) if x.get("name")=="Load"),[])
    pairs=[(t,v) for t,v in zip(data.get("unix_seconds",[]),load) if isinstance(v,(int,float))]
    if not pairs: raise RuntimeError("Sähkökuormaa ei saatu")
    stamp,value=pairs[-1]; mw=float(value)
    return result(mw,f"{mw/1000:.1f} GW","FRAUNHOFER ENERGY-CHARTS","SAKSAN SÄHKÖJÄRJESTELMÄ",datetime.fromtimestamp(stamp,timezone.utc).isoformat())

def money():
    data=get_json("https://api.blockchain.info/stats")
    value=float(data.get("estimated_transaction_volume_usd") or 0)
    if value<=0: raise RuntimeError("Bitcoin-siirtovolyymia ei saatu")
    stamp=datetime.fromtimestamp(float(data.get("timestamp",0))/1000,timezone.utc).isoformat()
    return result(value,f"${value/1_000_000_000:.1f} MRD","BLOCKCHAIN.COM","BITCOININ ARVIOITU 24 H SIIRTOVOLYYMI",stamp)

def safe(fn):
    try:return fn()
    except Exception as error:return {"status":"unavailable","value":None,"provider":fn.__name__.upper(),"scope":str(error)[:140],"state":"unavailable","change_pct":None}

def histories():
    rows=[]
    for path in sorted(HISTORY.glob("*.json")):
        try: rows.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception: pass
    return rows

now=datetime.now(timezone.utc); date=now.date().isoformat(); hour=now.strftime("%Y-%m-%dT%H")
flows={"internet":safe(internet),"aviation":safe(aviation),"freight":safe(freight),"electricity":safe(electricity),"money":safe(money)}
history=histories()
for key,flow in flows.items():
    if flow.get("status")!="ok": continue
    if flow.get("source_index") is not None:
        index=float(flow["source_index"]); change=index-100
    else:
        past=[h.get("flows",{}).get(key,{}).get("value") for h in history[-30:]]
        past=[float(v) for v in past if isinstance(v,(int,float))]
        baseline=statistics.median(past) if len(past)>=7 else None
        index=(flow["value"]/baseline*100) if baseline else None
        change=(index-100) if index is not None else None
    flow["index"]=index;flow["change_pct"]=change
    if change is None: flow["state"]="baseline"
    elif change<=-20: flow["state"]="alert"
    elif change<=-10: flow["state"]="watch"
    else: flow["state"]="normal"

states=[f.get("state") for f in flows.values() if f.get("status")=="ok"]
system="alert" if "alert" in states else "watch" if "watch" in states else "baseline" if "baseline" in states else "normal"
snapshot={"date":date,"generated_at":now.isoformat(),"method_version":"v0.1","baseline_observations":len(history),"system_state":system,"flows":flows}
payload=json.dumps(snapshot,ensure_ascii=False,indent=2)
(DATA/"latest.json").write_text(payload,encoding="utf-8")
(OBS/f"{hour}.json").write_text(payload,encoding="utf-8")
(HISTORY/f"{date}.json").write_text(payload,encoding="utf-8")
print(payload)

