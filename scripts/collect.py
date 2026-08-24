#!/usr/bin/env python3
import csv, io, json, math, os, statistics, urllib.parse, urllib.request
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

def get_text(url,timeout=35):
    request=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(request,timeout=timeout) as response:
        return response.read().decode("utf-8-sig")

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

_electricity_cache=None

def electricity():
    global _electricity_cache
    if _electricity_cache is not None: return _electricity_cache
    now=datetime.now(timezone.utc); start=(now-timedelta(days=10)).date().isoformat(); end=now.date().isoformat()
    grids=[]

    # Germany: latest measured load from Fraunhofer Energy-Charts.
    data=get_json("https://api.energy-charts.info/public_power",{"country":"de","start":start,"end":end})
    load=next((x.get("data",[]) for x in data.get("production_types",[]) if x.get("name")=="Load"),[])
    pairs=[(t,v) for t,v in zip(data.get("unix_seconds",[]),load) if isinstance(v,(int,float))]
    if pairs:
        daily={}
        for stamp,value in pairs: daily.setdefault(datetime.fromtimestamp(stamp,timezone.utc).date().isoformat(),[]).append(float(value))
        complete=sorted(daily)[:-1] or sorted(daily)
        latest_day=complete[-1]; current=statistics.mean(daily[latest_day]); previous=[statistics.mean(daily[d]) for d in complete[-8:-1]]
        idx=current/statistics.median(previous)*100 if previous else 100
        grids.append(("SAKSA",current,latest_day,idx))

    # Great Britain: official five-minute demand outturn.
    gb_days=[]
    for offset in range(1,9):
        day=(now-timedelta(days=offset)).date().isoformat()
        gb=get_json("https://data.elexon.co.uk/bmrs/api/v1/demand/outturn/summary",{"settlementDate":day,"format":"json"})
        values=[float(x["demand"]) for x in gb if isinstance(x.get("demand"),(int,float))]
        if values: gb_days.append((day,statistics.mean(values)))
    if gb_days:
        latest_day,current=gb_days[0]; previous=[value for _,value in gb_days[1:]]
        idx=current/statistics.median(previous)*100 if previous else 100
        grids.append(("ISO-BRITANNIA",current,latest_day,idx))

    # Brazil: official daily load, summed over the four ONS subsystems.
    year=now.year
    raw=get_text(f"https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/carga_energia_di/CARGA_ENERGIA_{year}.csv",timeout=45)
    rows=list(csv.DictReader(io.StringIO(raw),delimiter=";"))
    dates=[row.get("din_instante","") for row in rows]
    if dates:
        totals={}
        for row in rows: totals[row["din_instante"]]=totals.get(row["din_instante"],0)+float(row["val_cargaenergiamwmed"])
        latest_date=max(totals); brazil=totals[latest_date]; previous=[totals[d] for d in sorted(totals)[-29:-1]]
        idx=brazil/statistics.median(previous)*100 if previous else 100
        if brazil>0: grids.append(("BRASILIA",brazil,latest_date,idx))

    if not grids: raise RuntimeError("Yhtään sähköverkkoa ei saatu")
    # A geometric composite means that a large grid cannot hide a smaller grid's change.
    composite=math.exp(statistics.mean(math.log(mw) for _,mw,_,_ in grids))
    composite_index=math.exp(statistics.mean(math.log(idx) for *_,idx in grids))
    scope=" · ".join(f"{name} {mw/1000:.1f} GW" for name,mw,_,_ in grids)
    stamp=max(str(updated) for _,_,updated,_ in grids if updated)
    _electricity_cache=result(composite,f"{len(grids)} VERKKOA","ENERGY-CHARTS · ELEXON · ONS",scope,stamp,index=composite_index)
    _electricity_cache["component_indices"]=[{"name":name,"index":idx} for name,_,_,idx in grids]
    return _electricity_cache

def energy():
    # Global monthly oil flows. Compare the latest month with the same month
    # one year earlier, using only countries that reported both observations.
    now=datetime.now(timezone.utc); year=now.year
    current_url=f"https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv/primary/primaryyear{year}.csv"
    previous_url=f"https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv/primary/{year-1}.csv"
    current_rows=list(csv.DictReader(io.StringIO(get_text(current_url,timeout=60))))
    latest_month=max(row["TIME_PERIOD"] for row in current_rows)
    previous_month=f"{year-1}-{latest_month[-2:]}"
    previous_rows=list(csv.DictReader(io.StringIO(get_text(previous_url,timeout=60))))
    wanted={"INDPROD":"ÖLJYNTUOTANTO","REFINOBS":"JALOSTAMOJEN SYÖTTÖ","TOTEXPSB":"ÖLJYVIENTI"}
    def jodi_values(rows,month,flow):
        values={}
        for row in rows:
            raw=row.get("OBS_VALUE","")
            if row.get("TIME_PERIOD")==month and row.get("FLOW_BREAKDOWN")==flow and row.get("UNIT_MEASURE")=="KBD" and raw not in ("","-","x"):
                try: values[row["REF_AREA"]]=float(raw)
                except ValueError: pass
        return values
    parts=[]
    for flow,name in wanted.items():
        current_values=jodi_values(current_rows,latest_month,flow); previous_values=jodi_values(previous_rows,previous_month,flow)
        common=current_values.keys() & previous_values.keys()
        current_total=sum(current_values[country] for country in common); previous_total=sum(previous_values[country] for country in common)
        if current_total>0 and previous_total>0: parts.append({"name":name,"index":current_total/previous_total*100,"coverage":len(common)})

    # Near-current physical bottleneck: observed tanker passages through Hormuz.
    data=get_json("https://raw.githubusercontent.com/jasonhjohnson/strait-of-hormuz-data/main/data/transits.json")
    rows=sorted(data.get("history",[]),key=lambda x:x.get("date",""))
    values=[float(row.get("nTanker",0)) for row in rows if row.get("nTanker") is not None]
    if len(values)<14: raise RuntimeError("Tankkeriliikenteen aikasarja jäi liian lyhyeksi")
    current=statistics.mean(values[-7:])
    reference=statistics.median(values[-37:-7] or values[:-7])
    tanker_index=current/reference*100 if reference else 100
    parts.append({"name":"HORMUZIN TANKKERIT","index":tanker_index,"coverage":1})
    if len(parts)<3: raise RuntimeError("Energiavirran osia saatiin liian vähän")
    idx=math.exp(statistics.mean(math.log(part["index"]) for part in parts))
    scope=" · ".join(f'{part["name"]} {part["index"]:.0f}' for part in parts)
    flow=result(idx,f"{idx:.1f}","JODI OIL · IMF PORTWATCH",scope,max(latest_month,rows[-1].get("date","")),index=idx)
    flow["components"]=parts
    return flow

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
flows={"internet":safe(internet),"aviation":safe(aviation),"freight":safe(freight),"electricity":safe(electricity),"energy":safe(energy)}
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
snapshot={"date":date,"generated_at":now.isoformat(),"method_version":"v0.4","baseline_observations":len(history),"system_state":system,"flows":flows}
payload=json.dumps(snapshot,ensure_ascii=False,indent=2)
(DATA/"latest.json").write_text(payload,encoding="utf-8")
(OBS/f"{hour}.json").write_text(payload,encoding="utf-8")
(HISTORY/f"{date}.json").write_text(payload,encoding="utf-8")
print(payload)

