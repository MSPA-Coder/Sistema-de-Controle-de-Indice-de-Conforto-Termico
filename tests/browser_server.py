"""Fixtures fora da imagem servida; HTTP meteorológico e PostgreSQL reais."""

import datetime as dt
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from urllib.parse import parse_qs, urlparse

from alembic import command
from alembic.config import Config
from flask import request
from waitress import serve

from app import database as db
from app.app_factory import AppConfig, criar_app_ict
from app.dados_entrada import db as dados_db
from app.dados_entrada import gerador_dados
from app.dados_entrada.cidades import CIDADES_POR_ESPECIE
from app.seguranca import auth

weather_release = Event()
weather_requests = 0


class WeatherProvider(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (protocolo da stdlib)
        global weather_requests
        weather_requests += 1
        # Primeira zona já gravou seu staging. O teste libera a barreira.
        if weather_requests == 2 and not weather_release.wait(timeout=45):
            self.send_error(503)
            return
        query = parse_qs(urlparse(self.path).query)
        start = dt.datetime.fromisoformat(query["start_date"][0])
        end = dt.datetime.fromisoformat(query["end_date"][0]) + dt.timedelta(days=1)
        times = [
            start + dt.timedelta(hours=i) for i in range(int((end - start).total_seconds() / 3600))
        ]
        hourly = {"time": [t.isoformat(timespec="minutes") for t in times]}
        values = {
            "temperature_2m": 26.5,
            "relative_humidity_2m": 65.0,
            "wind_speed_10m": 2.0,
            "precipitation": 0.0,
            "surface_pressure": 1000.0,
            "shortwave_radiation": 100.0,
            "cloud_cover": 20.0,
        }
        hourly.update({key: [value] * len(times) for key, value in values.items()})
        payload = json.dumps({"hourly": hourly}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


def main():
    if os.environ.get("BROWSER_TEST_SERVER") != "1":
        raise RuntimeError("Use somente compose.browser.yaml e banco descartável.")
    command.upgrade(Config("alembic.ini"), "head")
    if db.listar_usuarios():
        raise RuntimeError("Banco browser precisa nascer vazio; recrie a pilha.")
    for region, role in (("br", "administrador"), ("us", "administrador"), ("denied", "operador")):
        user = db.criar_usuario(
            {
                "nome": f"Browser {region}",
                "login": f"browser-{region}",
                "perfil": role,
                "senha_hash": auth.gerar_hash_senha("Synthetic-browser-only-2026!"),
            },
            exigir_troca=False,
        )
        db.atualizar_formato_regional(user["id"], "us" if region == "us" else "br")
    zones = [
        db.criar_zona({"nome": f"Zona sintética {i}", "especie": "frangos", "indice": "ITU"})
        for i in (1, 2)
    ]
    configs = []
    for zone, city in zip(zones, CIDADES_POR_ESPECIE["frangos"][:2], strict=True):
        configs.append(
            {
                "zona_id": zone["id"],
                "cidade_codigo_ibge": city["codigo_ibge"],
                "latitude": city["latitude"],
                "longitude": city["longitude"],
                "altitude_m": city["altitude_m"],
                "fuso_horario": city["fuso_horario"],
                "area_util_m2": 100,
                "densidade_categoria": "media",
                "peso_medio_kg": 2.5,
                "producao_leite_kg_dia": 0,
                "ordenhas_dia": 0,
            }
        )
    dados_db.salvar_configuracoes_zonas(configs, zones)
    db.salvar_configuracoes(
        {
            "modoSimuladoZonas": True,
            "coletarDados": False,
            "habilitarEquipamentos": False,
            "enviarEmails": False,
        }
    )
    db.salvar_leitura(
        "frangos",
        "ITU",
        70,
        "Conforto",
        {"tbs": 25, "tbu": 20},
        zona_id=zones[1]["id"],
        timestamp_utc="2025-01-01T12:00:00+00:00",
    )
    db.salvar_leitura_recente_zona(
        zones[1]["id"], "frangos", "ITU", 70, "Conforto", {"tbs": 25, "tbu": 20}
    )
    with db.conexao() as conn:
        conn.execute("UPDATE leituras_recentes_zona SET criado_em='2025-01-01T12:00:00+00:00'")
    provider = ThreadingHTTPServer(("127.0.0.1", 5110), WeatherProvider)
    Thread(target=provider.serve_forever, daemon=True).start()
    gerador_dados.URL_OPEN_METEO = "http://127.0.0.1:5110/archive"
    app = criar_app_ict(AppConfig(False, "127.0.0.1", 5100, True, 1_000_000, True))

    @app.get("/api/__browser__/state")
    def browser_state():
        with dados_db._conexao(escrita=False) as conn:
            staging = conn.execute(
                "SELECT COUNT(*) FROM medicoes m JOIN execucoes e ON e.id=m.execucao_id WHERE e.status='processando'"
            ).fetchone()[0]
        return {
            "weather_requests": weather_requests,
            "staging": staging,
            "execucoes": dados_db.listar_execucoes(),
            "historico": db.contar_leituras(),
        }

    @app.post("/api/__browser__/weather-release")
    def browser_release():
        weather_release.set()
        return {"ok": True}

    @app.post("/api/__browser__/collector-fault")
    def browser_fault():
        os.environ["COLETOR_URL"] = (
            "http://127.0.0.1:5999" if request.json["enabled"] else "http://browser-coletor:5000"
        )
        return {"ok": True}

    for endpoint in ("browser_state", "browser_release", "browser_fault"):
        auth.AREA_POR_ENDPOINT[endpoint] = "sistema"
    serve(app, host="0.0.0.0", port=5100, threads=6)


if __name__ == "__main__":
    main()
