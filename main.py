from fastapi import FastAPI
import requests
from datetime import datetime
import pytz

app = FastAPI(
    title="Aviator 1Win",
    version="1.0.0"
)

URL = "https://app.tipmanager.net/api/casino-bot/get-crash-results-cached?limit=300&offset=0&id_bookmaker=5&place=15"

LOCAL_TZ = pytz.timezone("America/Bogota")

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/1win")
def crash_simple():
    response = requests.get(URL, timeout=10).json()["data"]

    resultados = []

    for item in response:
        utc_dt = datetime.fromisoformat(item["date"].replace("Z", "+00:00"))
        local_dt = utc_dt.astimezone(LOCAL_TZ)

        resultados.append({
            "hora": local_dt.strftime("%H:%M:%S"),
            "resultado": item["odd"]
        })

    # 🔥 MÁS NUEVO ARRIBA
    resultados.sort(key=lambda x: x["hora"], reverse=True)

    return resultados
