import requests
import time
import pandas as pd
from typing import List, Dict, Optional

# --------------------------
# CONFIGURACIÓN
# --------------------------
API_URL = "http://200.7.102.148:3350/1win"
POLL_INTERVAL = 3  # segundos
EXIT_POINT = 1.7
OPTIMAL_MINUTES = [1,3,5,9,11,13,15,19,21,23,25,29,31,33,35,39,41,43,45,49,51,53,55,59]
SIGNAL_COOLDOWN = 4  # segundos de enfriamiento entre señales

last_signal_time = 0
last_results_checked = set()
signals_log = []

# --------------------------
# FUNCIONES AUXILIARES
# --------------------------
def calculate_trend(recent: List[float]) -> str:
    if len(recent) < 5:
        return "neutral"
    half = len(recent)//2
    first = sum(recent[:half])/half
    second = sum(recent[half:])/half
    if second < first*0.85: return "down"
    if second > first*1.15: return "up"
    return "neutral"

# --------------------------
# ESTRATEGIAS DE AVIATOR
# --------------------------
def low_sequence(recent: List[float], threshold=1.5, count_req=6) -> Optional[Dict]:
    last10 = recent[-10:]
    count = sum(1 for v in last10 if v < threshold)
    if count >= count_req:
        return {"strategy":"LOW_SEQ_1.5","entryPoint":1.65,"confidence":88,"reason":f"{count} bajos <{threshold} en últimas 10"}
    return None

def crash_recovery(recent: List[float]) -> Optional[Dict]:
    last15 = recent[-15:]
    crashes = sum(1 for v in last15 if v < 1.2)
    recovered = any(v > 2.5 for v in last15[-5:])
    if crashes >= 4 and not recovered:
        return {"strategy":"CRASH_RECOVERY","entryPoint":1.66,"confidence":91,"reason":f"{crashes} crashes sin recuperación"}
    return None

def perfect_low_cycle(recent: List[float]) -> Optional[Dict]:
    lows = [i for i,v in enumerate(recent[-30:]) if v < 1.4]
    if len(lows) >= 4:
        gaps = [lows[i+1]-lows[i] for i in range(len(lows)-1)]
        avg_gap = sum(gaps)/len(gaps)
        variance = sum((g-avg_gap)**2 for g in gaps)/len(gaps)
        if variance < 2 and 2 < avg_gap < 8:
            return {"strategy":"PERFECT_CYCLE","entryPoint":1.65,"confidence":94,"reason":f"Ciclo perfecto cada ~{round(avg_gap)} rondas"}
    return None

def double_low_recovery(recent: List[float]) -> Optional[Dict]:
    last8 = recent[-8:]
    low_seq = 0
    for i in range(len(last8)-1):
        if last8[i]<1.5 and last8[i+1]<1.5: low_seq+=1
    if low_seq >=2:
        return {"strategy":"DOUBLE_LOW_RECOVERY","entryPoint":1.68,"confidence":88,"reason":f"{low_seq} secuencias dobles bajos detectadas"}
    return None

def consecutive_lows_break(recent: List[float]) -> Optional[Dict]:
    last10 = recent[-10:]
    max_consec=1
    current=1
    for i in range(1,len(last10)):
        if last10[i]<1.6 and last10[i-1]<1.6:
            current+=1
            max_consec=max(max_consec,current)
        else:
            current=1
    if max_consec>=6:
        return {"strategy":"CONSECUTIVE_LOWS_BREAK","entryPoint":1.65,"confidence":89,"reason":f"{max_consec} bajos consecutivos"}
    return None

def low_average_recovery(recent: List[float]) -> Optional[Dict]:
    last10 = recent[-10:]
    avg = sum(last10)/len(last10)
    low_count = sum(1 for v in last10 if v<1.6)
    if avg<1.8 and low_count>=7:
        return {"strategy":"LOW_AVG_RECOVERY","entryPoint":1.68,"confidence":87,"reason":f"Promedio {avg:.2f} con {low_count} bajos"}
    return None

def minute_opportunity(last_entry: Dict, recent: List[float]) -> Optional[Dict]:
    t = last_entry.get("time","00:00:00")
    minute = int(t.split(":")[1])
    if minute in OPTIMAL_MINUTES:
        low_count = sum(1 for v in recent[-10:] if v<2)
        if low_count>=6:
            return {"strategy":f"MINUTE_BASED_{minute}","entryPoint":1.7,"confidence":92,"reason":f"Minuto {minute} con {low_count} bajos"}
    return None

# --------------------------
# GENERADOR DE ESTRATEGIAS
# --------------------------
def generate_strategies(recent: List[float], last_entry: Dict) -> List[Dict]:
    funcs = [low_sequence, crash_recovery, perfect_low_cycle, double_low_recovery,
             consecutive_lows_break, low_average_recovery, minute_opportunity]
    results=[]
    for f in funcs:
        if f==minute_opportunity:
            res=f(last_entry,recent)
        else:
            res=f(recent)
        if res: results.append(res)
    return results

# --------------------------
# ANALIZADOR DE SEÑALES
# --------------------------
def analyze(results: List[Dict]) -> Optional[Dict]:
    global last_signal_time, last_results_checked
    if len(results)<30: return None
    last_entry = results[-1]
    last_value = float(last_entry.get("result",0))
    if last_value in last_results_checked: return None
    last_results_checked.add(last_value)
    now=time.time()
    if now - last_signal_time < SIGNAL_COOLDOWN:
        return None
    recent = [float(r["result"]) for r in results if "result" in r]
    last30 = recent[-30:]
    if calculate_trend(last30)=="down": return None
    strategies = generate_strategies(last30,last_entry)
    if not strategies: return None
    best = max(strategies,key=lambda x:x["confidence"])
    best.update({"exitPoint":EXIT_POINT,"attempts":0,"status":"pendiente","start_index":len(results)-1})
    last_signal_time=now
    return best

# --------------------------
# SEGUIMIENTO DE SEÑALES
# --------------------------
def check_signal(signal: Dict, next_value: float):
    signal["attempts"]+=1
    if next_value>=signal["exitPoint"]:
        signal["status"]="ganada"
        return True
    elif signal["attempts"]<2:
        signal["status"]="reintento"
        return False
    else:
        signal["status"]="perdida"
        print("x"*30 + " LOSS " + "x"*30)
        return False

# --------------------------
# ESCANER CONTINUO
# --------------------------
def run_scanner():
    all_results=[]
    active_signals=[]
    while True:
        try:
            r=requests.get(API_URL,timeout=5)
            data=r.json()
            if not isinstance(data,list):
                time.sleep(POLL_INTERVAL)
                continue
            all_results.extend(data)
            all_results=all_results[-1000:]
            signal=analyze(all_results)
            if signal:
                print(f"✅ Nueva Señal: {signal['strategy']} · Entrada: {signal['entryPoint']} · Confianza: {signal['confidence']:.1f}% · Razón: {signal['reason']}")
                active_signals.append(signal)
            for sig in active_signals[:]:
                if sig.get("status") in ["ganada","perdida"]: continue
                attempt_index = sig["start_index"] + sig["attempts"]
                if attempt_index >= len(all_results): continue
                next_value=float(all_results[attempt_index]["result"])
                check_signal(sig,next_value)
                if sig.get("status") in ["ganada","perdida"]:
                    print(f"📊 Resultado Señal: {sig['strategy']} · Estado: {sig['status']} · Entrada: {sig['entryPoint']} · Intentos: {sig['attempts']}")
                    signals_log.append(sig)
                    active_signals.remove(sig)
            if signals_log:
                pd.DataFrame(signals_log).to_csv("signals_log.csv",index=False)
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(POLL_INTERVAL)

if __name__=="__main__":
    run_scanner()
