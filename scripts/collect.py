#!/usr/bin/env python3
import csv, io, json, math, os, statistics, urllib.parse, urllib.request, zipfile
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

def weighted_geomean(items):
    usable=[(value,weight) for value,weight in items if value and value>0 and weight>0]
    total=sum(weight for _,weight in usable)
    if not usable or total<=0: raise RuntimeError("Indeksin osia ei saatu")
    return math.exp(sum(weight*math.log(value) for value,weight in usable)/total)

def internet():
    token=os.getenv("CLOUDFLARE_API_TOKEN")
    if not token: raise RuntimeError("CLOUDFLARE_API_TOKEN puuttuu")
    data=get_json("https://api.cloudflare.com/client/v4/radar/http/timeseries",{"dateRange":"28d","aggInterval":"1h","format":"JSON"},{"Authorization":f"Bearer {token}"})
    series=data.get("result",{}).get("serie_0",{})
    values=[float(v) for v in series.get("values",[]) if v is not None]
    if not values: raise RuntimeError("Cloudflare ei palauttanut aikasarjaa")
    comparable=values[-25::-24]
    if len(comparable)<7: raise RuntimeError("Cloudflare same-hour -vertailu jäi liian lyhyeksi")
    baseline=statistics.median(comparable[:27])
    idx=values[-1]/baseline*100 if baseline else None
    if idx is None: raise RuntimeError("Cloudflare same-hour -vertailutaso oli nolla")
    return result(idx,f"{idx:.1f}","CLOUDFLARE RADAR","SUHTEELLINEN HTTP-AKTIIVISUUS · SAMA UTC-TUNTI = 100",index=idx)

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
    # Monthly official anchors: compare like-for-like reporting countries with
    # the same calendar month one year earlier to remove most seasonality.
    now=datetime.now(timezone.utc); year=now.year
    current_url=f"https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv/primary/primaryyear{year}.csv"
    previous_url=f"https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv/primary/{year-1}.csv"
    current_rows=list(csv.DictReader(io.StringIO(get_text(current_url,timeout=60))))
    latest_month=max(row["TIME_PERIOD"] for row in current_rows)
    previous_month=f"{year-1}-{latest_month[-2:]}"
    previous_rows=list(csv.DictReader(io.StringIO(get_text(previous_url,timeout=60))))
    def jodi_values(rows,month,flow,product=None,unit=None):
        values={}
        for row in rows:
            raw=row.get("OBS_VALUE","")
            matches=(row.get("TIME_PERIOD")==month and row.get("FLOW_BREAKDOWN")==flow and raw not in ("","-","x"))
            if product: matches=matches and row.get("ENERGY_PRODUCT")==product
            if unit: matches=matches and row.get("UNIT_MEASURE")==unit
            if matches:
                try: values[row["REF_AREA"]]=float(raw)
                except ValueError: pass
        return values

    def comparable_index(current,previous):
        common=current.keys() & previous.keys()
        current_total=sum(current[country] for country in common); previous_total=sum(previous[country] for country in common)
        if current_total<=0 or previous_total<=0: return None,len(common)
        return current_total/previous_total*100,len(common)

    oil_parts=[]
    for flow,name,weight in (("INDPROD","ÖLJYNTUOTANTO",0.50),("REFINOBS","JALOSTAMOJEN SYÖTTÖ",0.30),("TOTEXPSB","ÖLJYVIENTI",0.20)):
        current_values=jodi_values(current_rows,latest_month,flow,unit="KBD"); previous_values=jodi_values(previous_rows,previous_month,flow,unit="KBD")
        index,coverage=comparable_index(current_values,previous_values)
        if index: oil_parts.append({"name":name,"index":index,"coverage":coverage,"weight":weight})

    # Global gas: production, pipeline exports and LNG exports from JODI Gas.
    gas_bytes=urllib.request.urlopen(urllib.request.Request("https://www.jodidata.org/jodi-publisher/gas/17/GAS_world_NewFormat.zip",headers={"User-Agent":UA}),timeout=60).read()
    with zipfile.ZipFile(io.BytesIO(gas_bytes)) as archive:
        gas_name=next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        gas_rows=list(csv.DictReader(io.StringIO(archive.read(gas_name).decode("utf-8-sig"))))
    gas_months=sorted({row["TIME_PERIOD"] for row in gas_rows})
    gas_parts=[]
    for flow,product,name,weight in (("INDPROD","NATGAS","KAASUNTUOTANTO",0.50),("EXPPIP","NATGAS","PUTKIKAASU",0.25),("EXPLNG","NATGAS","LNG-VIENTI",0.25)):
        for month in reversed(gas_months):
            previous=f"{int(month[:4])-1}-{month[-2:]}"
            current_values=jodi_values(gas_rows,month,flow,product=product,unit="TJ"); previous_values=jodi_values(gas_rows,previous,flow,product=product,unit="TJ")
            index,coverage=comparable_index(current_values,previous_values)
            if index and coverage>=10:
                gas_parts.append({"name":name,"index":index,"coverage":coverage,"weight":weight,"period":month})
                break

    if len(oil_parts)<2 or len(gas_parts)<2: raise RuntimeError("Öljyn tai kaasun vertailuosia saatiin liian vähän")
    oil_anchor=weighted_geomean([(part["index"],part["weight"]) for part in oil_parts])
    gas_index=weighted_geomean([(part["index"],part["weight"]) for part in gas_parts])
    gas_latest=max(part["period"] for part in gas_parts)

    # Near-current physical bottleneck: observed tanker passages through Hormuz.
    data=get_json("https://raw.githubusercontent.com/jasonhjohnson/strait-of-hormuz-data/main/data/transits.json")
    rows=sorted(data.get("history",[]),key=lambda x:x.get("date",""))
    values=[float(row.get("nTanker",0)) for row in rows if row.get("nTanker") is not None]
    if len(values)<14: raise RuntimeError("Tankkeriliikenteen aikasarja jäi liian lyhyeksi")
    current=statistics.mean(values[-7:])
    reference=statistics.median(values[-37:-7] or values[:-7])
    tanker_index=current/reference*100 if reference else 100
    # Hormuz is a fast disturbance signal inside oil, not a fourth global flow.
    # Capping it prevents one chokepoint from overwhelming the monthly anchor.
    tanker_capped=max(50,min(150,tanker_index))
    oil_index=weighted_geomean([(oil_anchor,0.85),(tanker_capped,0.15)])

    # Global primary-energy shares: oil 40 %, gas 30 %, coal 20 %, other fuels
    # 10 %. Only observed sectors enter the index; coverage exposes the gap.
    idx=weighted_geomean([(oil_index,0.40),(gas_index,0.30)])
    coverage_pct=70
    confidence="KESKITASO"
    parts=[{"name":"ÖLJY","index":oil_index,"weight":40,"details":oil_parts},{"name":"KAASU JA LNG","index":gas_index,"weight":30,"details":gas_parts},{"name":"HORMUZ","index":tanker_index,"weight":0,"role":"NOPEA HÄIRIÖSIGNAALI"}]
    scope=f"ÖLJY {oil_index:.0f} · KAASU JA LNG {gas_index:.0f} · KATTAVUUS {coverage_pct} %"
    flow=result(idx,f"{idx:.1f}","JODI OIL · JODI GAS · IMF PORTWATCH",scope,max(latest_month,gas_latest,rows[-1].get("date","")),index=idx)
    flow.update({"components":parts,"coverage_pct":coverage_pct,"confidence":confidence,"oil_updated":latest_month,"gas_updated":gas_latest,"fast_updated":rows[-1].get("date"),
                 "temporal_profile":"HIDAS TAUSTATILA + NOPEA HÄIRIÖSIGNAALI"})
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

def observations():
    rows=[]
    for path in sorted(OBS.glob("*.json")):
        try: rows.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception: pass
    return rows

def parsed_time(snapshot):
    try:return datetime.fromisoformat(snapshot.get("generated_at","").replace("Z","+00:00"))
    except (TypeError,ValueError):return None

def baseline_rows(rows,current_time,minimum=7):
    timed=[(parsed_time(row),row) for row in rows]
    timed=[(stamp,row) for stamp,row in timed if stamp and stamp<current_time]
    same_slot=[row for stamp,row in timed if stamp.weekday()==current_time.weekday() and stamp.hour==current_time.hour]
    if len(same_slot)>=minimum:return same_slot[-13:]
    same_hour=[row for stamp,row in timed if stamp.hour==current_time.hour]
    if len(same_hour)>=minimum:return same_hour[-30:]
    return [row for _,row in timed[-90:]]

now=datetime.now(timezone.utc); date=now.date().isoformat(); hour=now.strftime("%Y-%m-%dT%H")
flows={"internet":safe(internet),"aviation":safe(aviation),"freight":safe(freight),"electricity":safe(electricity),"energy":safe(energy)}
history=histories()
observation_history=observations()
comparison_rows=baseline_rows(observation_history or history,now)
for key,flow in flows.items():
    if flow.get("status")!="ok": continue
    if flow.get("source_index") is not None:
        index=float(flow["source_index"]); change=index-100
    else:
        past=[h.get("flows",{}).get(key,{}).get("value") for h in comparison_rows]
        past=[float(v) for v in past if isinstance(v,(int,float))]
        baseline=statistics.median(past) if len(past)>=7 else None
        index=(flow["value"]/baseline*100) if baseline else None
        change=(index-100) if index is not None else None
    flow["index"]=index;flow["change_pct"]=change
    if change is None: flow["state"]="baseline"
    elif change<=-20: flow["state"]="low_anomaly"
    elif change<=-10: flow["state"]="low_watch"
    elif change>=20: flow["state"]="high_anomaly"
    elif change>=10: flow["state"]="high_watch"
    else: flow["state"]="normal"

states=[f.get("state") for f in flows.values() if f.get("status")=="ok"]
system="anomaly" if any(s in ("low_anomaly","high_anomaly") for s in states) else "watch" if any(s in ("low_watch","high_watch") for s in states) else "baseline" if "baseline" in states else "normal"
snapshot={"date":date,"generated_at":now.isoformat(),"method_version":"v0.6","baseline_observations":len(comparison_rows),
          "baseline_method":"same weekday + UTC hour; fallback same UTC hour; rolling median","system_state":system,"flows":flows}
payload=json.dumps(snapshot,ensure_ascii=False,indent=2)
(DATA/"latest.json").write_text(payload,encoding="utf-8")
(OBS/f"{hour}.json").write_text(payload,encoding="utf-8")
(HISTORY/f"{date}.json").write_text(payload,encoding="utf-8")
print(payload)
