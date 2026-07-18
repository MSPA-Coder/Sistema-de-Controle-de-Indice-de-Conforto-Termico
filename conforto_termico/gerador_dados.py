# -*- coding: utf-8 -*-
"""Geracao de series meteorologicas historicas e carga termica animal.

Dados climaticos horarios sao obtidos da API historica Open-Meteo com o
modelo ERA5. Pontos sub-horarios sao derivados por interpolacao e sempre
rotulados como tal. Nenhuma falha de rede e substituida por clima aleatorio.

O modelo animal e uma aproximacao de grupo, reproduzivel por semente. A
estrutura metabolica (massa^0,75, particao sensivel/latente e aumento por
atividade/producao) segue os principios de CIGR 2002 e ASABE D384.2; horarios
de alimentacao, repouso e ordenha sao parametrizacoes explicitas, nao dados
observados. O objetivo e produzir carga de entrada plausivel e auditavel,
nao reconstruir o comportamento individual de um rebanho real.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import random
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import certifi
import truststore

from . import dados_entrada_db as dados_db
from . import thermal_indices as ti

FONTE_CLIMA = "Open-Meteo Historical Weather API / ERA5"
URL_OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"
DIAS_MINIMOS = 1
DIAS_MAXIMOS = 366
INTERVALO_MINIMO_MINUTOS = 1
INTERVALO_MAXIMO_MINUTOS = 1440
MAXIMO_MEDICOES = 2_000_000
ATRASO_PADRAO_ERA5_DIAS = 8

VARIAVEIS_OPEN_METEO = {
    "temperature_2m": "tbs",
    "relative_humidity_2m": "ur",
    "wind_speed_10m": "vento",
    "precipitation": "precipitacao",
    "surface_pressure": "pressao",
    "shortwave_radiation": "radiacao",
    "cloud_cover": "nebulosidade",
}


class GeracaoDadosError(ValueError):
    """Erro esperado e seguro para exibicao ao usuario."""


@dataclass(frozen=True)
class ParametrosGeracao:
    dias: int
    intervalo_minutos: int
    data_final: datetime.date
    data_inicio: datetime.date
    semente: int


def _inteiro(dados: dict, chave: str, minimo: int, maximo: int) -> int:
    try:
        valor = int(dados.get(chave))
    except (TypeError, ValueError) as erro:
        raise GeracaoDadosError(f"Informe um número inteiro para {chave}.") from erro
    if not minimo <= valor <= maximo:
        raise GeracaoDadosError(f"{chave} deve estar entre {minimo} e {maximo}.")
    return valor


def validar_parametros(dados: dict, total_zonas: int) -> ParametrosGeracao:
    dias = _inteiro(dados, "dias", DIAS_MINIMOS, DIAS_MAXIMOS)
    intervalo = _inteiro(
        dados, "intervalo_minutos", INTERVALO_MINIMO_MINUTOS, INTERVALO_MAXIMO_MINUTOS
    )
    bruto_data = dados.get("data_final")
    if bruto_data:
        try:
            data_final = datetime.date.fromisoformat(str(bruto_data))
        except ValueError as erro:
            raise GeracaoDadosError("data_final deve estar no formato AAAA-MM-DD.") from erro
    else:
        data_final = datetime.date.today() - datetime.timedelta(
            days=ATRASO_PADRAO_ERA5_DIAS
        )
    data_final_maxima = datetime.date.today() - datetime.timedelta(
        days=ATRASO_PADRAO_ERA5_DIAS
    )
    if data_final > data_final_maxima:
        raise GeracaoDadosError(
            "A data final precisa ser igual ou anterior a "
            f"{data_final_maxima.isoformat()}, pois o ERA5 possui atraso de consolidação."
        )
    data_inicio = data_final - datetime.timedelta(days=dias - 1)
    try:
        semente = int(dados.get("semente", 20260718))
    except (TypeError, ValueError) as erro:
        raise GeracaoDadosError("A semente da simulação deve ser inteira.") from erro

    pontos_por_zona = math.ceil(dias * 1440 / intervalo)
    total = pontos_por_zona * total_zonas
    if total > MAXIMO_MEDICOES:
        raise GeracaoDadosError(
            f"A combinação solicitada geraria {total:,} medições; o limite de segurança "
            f"é {MAXIMO_MEDICOES:,}. Aumente o intervalo ou reduza os dias."
        )
    return ParametrosGeracao(dias, intervalo, data_final, data_inicio, semente)


def calcular_ponto_orvalho(tbs: float, ur: float) -> float:
    """Magnus (Alduchov/Eskridge), temperatura em graus Celsius."""
    ur_limitada = max(0.1, min(100.0, float(ur)))
    a, b = 17.625, 243.04
    gama = math.log(ur_limitada / 100.0) + a * float(tbs) / (b + float(tbs))
    return b * gama / (a - gama)


def calcular_bulbo_umido(tbs: float, ur: float) -> float:
    """Aproximacao de Stull (2011), adequada para series ambientais."""
    rh = max(1.0, min(100.0, float(ur)))
    t = float(tbs)
    resultado = (
        t * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * (rh ** 1.5) * math.atan(0.023101 * rh)
        - 4.686035
    )
    return min(t, resultado)


def estimar_globo_negro(tbs: float, radiacao: float | None, vento: float) -> float:
    """Estimativa transparente de TGN quando nao ha globo negro observado.

    A radiacao eleva a temperatura de globo e o vento reduz esse ganho. O
    resultado e um campo calculado e nunca e rotulado como observacao.
    """
    radiacao = max(0.0, float(radiacao or 0.0))
    ganho = 0.012 * radiacao / math.sqrt(max(0.1, float(vento)))
    return float(tbs) + min(25.0, ganho)


def _chave_cache(latitude: float, longitude: float, inicio: str, fim: str) -> str:
    bruto = f"era5|{latitude:.5f}|{longitude:.5f}|{inicio}|{fim}|v1"
    return hashlib.sha256(bruto.encode("ascii")).hexdigest()


def _baixar_json(url: str) -> dict:
    requisicao = urllib.request.Request(
        url,
        headers={"User-Agent": "ConfortoTermico-Mestrado/1.0 (historical-input-generator)"},
    )
    try:
        # O Truststore usa o armazenamento nativo do sistema operacional,
        # incluindo CAs institucionais instaladas no Windows. Certifi fica
        # como fallback defensivo, sempre com verificacao TLS habilitada.
        try:
            contexto_tls = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            contexto_tls = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(
            requisicao, timeout=45, context=contexto_tls
        ) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as erro:
        raise GeracaoDadosError(
            "Não foi possível obter o clima histórico real no Open-Meteo. "
            "Nenhum valor climático foi inventado; verifique a internet e tente novamente."
        ) from erro


def obter_clima_horario(
    latitude: float,
    longitude: float,
    inicio_utc: datetime.datetime,
    fim_utc_exclusivo: datetime.datetime,
) -> dict:
    # Um dia extra fornece a ancora das interpolacoes no fim do periodo.
    data_inicio = (inicio_utc - datetime.timedelta(days=1)).date().isoformat()
    data_fim = (fim_utc_exclusivo + datetime.timedelta(days=1)).date().isoformat()
    chave = _chave_cache(latitude, longitude, data_inicio, data_fim)
    cache = dados_db.obter_cache_clima(chave)
    if cache is not None:
        completa, _ = _avaliar_cobertura_clima(
            cache, inicio_utc, fim_utc_exclusivo
        )
        if completa:
            return cache
        # Uma resposta consultada antes da consolidação do ERA5 não pode
        # permanecer válida para sempre. Remova-a e consulte a fonte novamente.
        dados_db.excluir_cache_clima(chave)

    parametros = {
        "latitude": f"{latitude:.6f}",
        "longitude": f"{longitude:.6f}",
        "start_date": data_inicio,
        "end_date": data_fim,
        "hourly": ",".join(VARIAVEIS_OPEN_METEO),
        "timezone": "UTC",
        "wind_speed_unit": "ms",
        "models": "era5",
    }
    url = URL_OPEN_METEO + "?" + urllib.parse.urlencode(parametros)
    bruto = _baixar_json(url)
    if bruto.get("error"):
        raise GeracaoDadosError(str(bruto.get("reason") or "Open-Meteo rejeitou a consulta."))
    hourly = bruto.get("hourly")
    if not isinstance(hourly, dict) or not hourly.get("time"):
        raise GeracaoDadosError("A fonte meteorológica não retornou a série horária esperada.")
    faltando = [variavel for variavel in VARIAVEIS_OPEN_METEO if variavel not in hourly]
    if faltando:
        raise GeracaoDadosError(
            "A fonte meteorológica não retornou: " + ", ".join(faltando)
        )
    completa, ultima_hora = _avaliar_cobertura_clima(
        bruto, inicio_utc, fim_utc_exclusivo
    )
    if not completa:
        ultima = (
            ultima_hora.astimezone(datetime.timezone.utc).strftime("%d/%m/%Y às %H:%M UTC")
            if ultima_hora is not None else "nenhuma hora"
        )
        raise GeracaoDadosError(
            "O ERA5 ainda não consolidou todo o período solicitado. "
            f"A última hora completa recebida foi {ultima}. "
            "Escolha uma data final mais antiga e tente novamente."
        )
    dados_db.salvar_cache_clima(chave, bruto, FONTE_CLIMA)
    return bruto


def _serie_clima(bruto: dict) -> tuple[list[datetime.datetime], dict[str, list]]:
    horario = bruto["hourly"]
    tempos = []
    for item in horario["time"]:
        texto = str(item)
        dt = datetime.datetime.fromisoformat(texto)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        tempos.append(dt.astimezone(datetime.timezone.utc))
    series = {apelido: horario[variavel] for variavel, apelido in VARIAVEIS_OPEN_METEO.items()}
    return tempos, series


def _numero_valido(valor) -> float | None:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _avaliar_cobertura_clima(
    bruto: dict,
    inicio_utc: datetime.datetime,
    fim_utc_exclusivo: datetime.datetime,
) -> tuple[bool, datetime.datetime | None]:
    """Confirma que cada hora necessária possui todas as variáveis reais.

    A hora do fim exclusivo também é exigida como âncora para interpolar o
    último ponto sub-horário. Respostas futuras preenchidas com ``null`` não
    são aceitas nem armazenadas no cache.
    """
    try:
        tempos, series = _serie_clima(bruto)
    except (KeyError, TypeError, ValueError):
        return False, None
    if not tempos or any(len(serie) != len(tempos) for serie in series.values()):
        return False, None

    completos = {
        instante
        for indice, instante in enumerate(tempos)
        if all(_numero_valido(serie[indice]) is not None for serie in series.values())
    }
    ultima_hora = max(completos) if completos else None
    cursor = inicio_utc.astimezone(datetime.timezone.utc).replace(
        minute=0, second=0, microsecond=0
    )
    limite = fim_utc_exclusivo.astimezone(datetime.timezone.utc)
    if limite.minute or limite.second or limite.microsecond:
        limite = limite.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
    while cursor <= limite:
        if cursor not in completos:
            return False, ultima_hora
        cursor += datetime.timedelta(hours=1)
    return True, ultima_hora


def _interpolar(tempos: list[datetime.datetime], serie: list, alvo: datetime.datetime) -> tuple[float, bool]:
    if alvo < tempos[0] or alvo > tempos[-1]:
        raise GeracaoDadosError("A série meteorológica não cobre todo o período solicitado.")
    passo = (alvo - tempos[0]).total_seconds() / 3600
    esquerda_idx = max(0, min(len(tempos) - 1, math.floor(passo)))
    direita_idx = max(0, min(len(tempos) - 1, math.ceil(passo)))
    esquerda = _numero_valido(serie[esquerda_idx])
    direita = _numero_valido(serie[direita_idx])
    if esquerda is None or direita is None:
        raise GeracaoDadosError(
            "A série meteorológica possui uma lacuna no período solicitado; "
            "nenhum valor anterior será repetido para preencher dados ausentes."
        )
    dt_esquerda = tempos[esquerda_idx]
    dt_direita = tempos[direita_idx]
    if dt_esquerda == dt_direita:
        return esquerda, alvo != dt_esquerda
    fracao = (alvo - dt_esquerda).total_seconds() / (
        dt_direita - dt_esquerda
    ).total_seconds()
    valor = esquerda + (direita - esquerda) * fracao
    return valor, alvo != dt_esquerda


def _clima_no_instante(
    tempos: list[datetime.datetime],
    series: dict[str, list],
    alvo: datetime.datetime,
    intervalo_minutos: int,
) -> dict:
    valores = {}
    interpolado = False
    for nome, serie in series.items():
        valor, derivado = _interpolar(tempos, serie, alvo)
        valores[nome] = valor
        interpolado = interpolado or derivado
    # Open-Meteo fornece precipitacao acumulada na hora. Distribuir pelo
    # passo conserva o volume horario quando sao pedidos pontos sub-horarios.
    if intervalo_minutos < 60:
        valores["precipitacao"] *= intervalo_minutos / 60.0
    valores["ur"] = max(0.1, min(100.0, valores["ur"]))
    valores["vento"] = max(0.0, valores["vento"])
    valores["radiacao"] = max(0.0, valores["radiacao"])
    valores["precipitacao"] = max(0.0, valores["precipitacao"])
    valores["nebulosidade"] = max(0.0, min(100.0, valores["nebulosidade"]))
    valores["interpolado"] = interpolado
    return valores


def _janelas_ordenha(ordenhas: int) -> tuple[float, ...]:
    return {
        0: (), 1: (6.0,), 2: (5.0, 17.0), 3: (5.0, 13.0, 21.0),
        4: (4.0, 10.0, 16.0, 22.0),
    }[ordenhas]


def _perto_da_hora(hora: float, centros: tuple[float, ...], duracao: float) -> bool:
    for centro in centros:
        distancia = abs(hora - centro)
        distancia = min(distancia, 24 - distancia)
        if distancia <= duracao / 2:
            return True
    return False


def _atividade_animal(
    especie: str, hora: float, ordenhas: int, estresse: float, rng: random.Random
) -> dict:
    variacao = rng.uniform(-0.08, 0.08)
    if especie == "bovinos":
        em_ordenha = _perto_da_hora(hora, _janelas_ordenha(ordenhas), 1.2)
        alimentando = _perto_da_hora(hora, (7.0, 16.0), 3.0)
        noite = hora >= 22 or hora < 4.5
        if em_ordenha:
            atividade, deitados, fator, taxa_comida = "ordenha", 0.03, 1.18, 0.0
        elif alimentando:
            atividade, deitados, fator, taxa_comida = "alimentação", 0.12, 1.22, 1.0
        elif noite or 11.5 <= hora <= 14.5:
            atividade, deitados, fator, taxa_comida = "repouso/ruminação", 0.78, 0.88, 0.0
        else:
            atividade, deitados, fator, taxa_comida = "ruminação/deslocamento", 0.45, 1.02, 0.05
        fracao_ordenha = 0.82 if em_ordenha else 0.0
    elif especie == "suinos":
        alimentando = _perto_da_hora(hora, (7.0, 17.0), 2.0)
        repouso = hora >= 21 or hora < 5.5 or 11 <= hora <= 15.5
        if alimentando:
            atividade, deitados, fator, taxa_comida = "alimentação", 0.18, 1.25, 1.0
        elif repouso:
            atividade, deitados, fator, taxa_comida = "repouso/sono", 0.88, 0.78, 0.0
        else:
            atividade, deitados, fator, taxa_comida = "exploração/deslocamento", 0.48, 1.08, 0.08
        fracao_ordenha = 0.0
    else:
        escuro = hora >= 20 or hora < 5
        if escuro:
            atividade, deitados, fator, taxa_comida = "repouso", 0.94, 0.72, 0.0
        else:
            atividade, deitados, fator, taxa_comida = "alimentação/atividade", 0.30, 1.15, 1.0
        fracao_ordenha = 0.0

    # Calor intenso aumenta repouso e reduz ingestao; a pequena variacao
    # impede dias identicos sem destruir a reprodutibilidade.
    deitados = max(0.0, min(0.98, deitados + 0.18 * estresse + variacao))
    taxa_comida *= max(0.45, 1.0 - 0.45 * estresse)
    return {
        "atividade": atividade,
        "fracao_deitados": deitados,
        "fracao_ordenha": fracao_ordenha,
        "fator_metabolico": fator,
        "taxa_comida": taxa_comida,
    }


def simular_animais(
    config: dict,
    instante_local: datetime.datetime,
    tbs: float,
    ur: float,
    intervalo_minutos: int,
    rng: random.Random,
) -> dict:
    especie = config["especie"]
    quantidade = int(config["quantidade_animais"])
    peso = float(config["peso_medio_kg"])
    producao = float(config["producao_leite_kg_dia"])
    ordenhas = int(config["ordenhas_dia"])
    hora = instante_local.hour + instante_local.minute / 60
    thi = (1.8 * tbs + 32) - (0.55 - 0.0055 * ur) * (1.8 * tbs - 26)
    estresse = max(0.0, min(1.0, (thi - 68.0) / 16.0))
    rotina = _atividade_animal(especie, hora, ordenhas, estresse, rng)

    deitados = int(round(quantidade * rotina["fracao_deitados"]))
    deitados = max(0, min(quantidade, deitados))
    em_pe = quantidade - deitados
    em_ordenha = int(round(quantidade * rotina["fracao_ordenha"]))
    em_ordenha = max(0, min(em_pe, em_ordenha))

    coeficiente = {"bovinos": 6.0, "suinos": 7.0, "frangos": 9.5}[especie]
    calor_por_animal = coeficiente * (peso ** 0.75) * rotina["fator_metabolico"]
    if especie == "bovinos":
        calor_por_animal += producao * 12.0
    calor_total = calor_por_animal * quantidade
    fracao_sensivel = max(0.30, min(0.70, 0.68 - 0.015 * (tbs - 15) - 0.001 * (ur - 50)))
    sensivel = calor_total * fracao_sensivel
    latente = calor_total - sensivel
    vapor = latente * 3600 / 2_450_000

    ingestao_diaria = {
        "bovinos": 0.025 * peso + 0.25 * producao,
        "suinos": 0.030 * peso,
        "frangos": 0.060 * peso,
    }[especie]
    horas_alimentacao = {"bovinos": 6.0, "suinos": 4.0, "frangos": 15.0}[especie]
    comida = (
        ingestao_diaria
        * quantidade
        * rotina["taxa_comida"]
        * intervalo_minutos
        / (horas_alimentacao * 60)
    )
    agua_diaria = {
        "bovinos": max(35.0, 0.08 * peso + 2.5 * producao),
        "suinos": max(3.0, 0.10 * peso),
        "frangos": max(0.18, 0.12 * peso),
    }[especie]
    agua = agua_diaria * quantidade * intervalo_minutos / 1440
    agua *= 1.0 + 0.9 * estresse
    if rotina["atividade"].startswith("alimentação"):
        agua *= 1.35

    return {
        "quantidade_animais": quantidade,
        "atividade_predominante": rotina["atividade"],
        "alimentacao_kg": round(comida, 5),
        "consumo_agua_l": round(agua, 4),
        "animais_em_pe": em_pe,
        "animais_deitados": deitados,
        "animais_em_ordenha": em_ordenha,
        "calor_sensivel_animais_w": round(sensivel, 2),
        "calor_latente_animais_w": round(latente, 2),
        "vapor_agua_animais_kg_h": round(vapor, 5),
    }


def _indice(zona: dict, tbs: float, tbu: float, tpo: float, vento: float, radiacao: float):
    indice = zona["indice"]
    if indice == "ITU":
        entradas = {"tbs": tbs, "tbu": tbu}
        valor = ti.calcular_itu(tbs, tbu)
    elif indice == "ITUV":
        entradas = {"tbs": tbs, "tbu": tbu, "v": max(0.01, vento)}
        valor = ti.calcular_ituv(tbs, tbu, max(0.01, vento))
    else:
        tgn = estimar_globo_negro(tbs, radiacao, vento)
        entradas = {"tgn": tgn, "tpo": tpo}
        valor = ti.calcular_ignu(tgn, tpo)
    return valor, ti.classificar_status(valor, zona["especie"], indice), entradas


def _iterar_instantes(inicio: datetime.datetime, fim: datetime.datetime, minutos: int):
    atual = inicio
    passo = datetime.timedelta(minutes=minutos)
    while atual < fim:
        yield atual
        atual += passo


def gerar(dados: dict, zonas: list[dict]) -> dict:
    zonas = [zona for zona in zonas if zona.get("ativa")]
    if not zonas:
        raise GeracaoDadosError("Ative ao menos uma zona antes de gerar os dados.")
    parametros = validar_parametros(dados, len(zonas))
    configs = dados_db.obter_configuracoes_zonas(zonas)
    por_id = {config["zona_id"]: config for config in configs}
    incompletas = [zona["nome"] for zona in zonas if not por_id.get(zona["id"], {}).get("configurada")]
    if incompletas:
        raise GeracaoDadosError(
            "Complete localização, quantidade e peso dos animais nestas zonas: "
            + ", ".join(incompletas)
        )

    execucao_id = dados_db.criar_execucao(
        data_inicio=parametros.data_inicio.isoformat(),
        data_fim=parametros.data_final.isoformat(),
        dias=parametros.dias,
        intervalo_minutos=parametros.intervalo_minutos,
        semente=parametros.semente,
        total_zonas=len(zonas),
        fonte_clima=FONTE_CLIMA,
    )
    total = 0
    try:
        for zona in zonas:
            config = por_id[zona["id"]]
            fuso = ZoneInfo(config["fuso_horario"])
            inicio_local = datetime.datetime.combine(
                parametros.data_inicio, datetime.time.min, tzinfo=fuso
            )
            fim_local = inicio_local + datetime.timedelta(days=parametros.dias)
            inicio_utc = inicio_local.astimezone(datetime.timezone.utc)
            fim_utc = fim_local.astimezone(datetime.timezone.utc)
            bruto = obter_clima_horario(
                config["latitude"], config["longitude"], inicio_utc, fim_utc
            )
            tempos, series = _serie_clima(bruto)
            seed_zona = parametros.semente + zona["id"] * 100_003
            rng = random.Random(seed_zona)
            lote = []
            for instante_local in _iterar_instantes(
                inicio_local, fim_local, parametros.intervalo_minutos
            ):
                instante_utc = instante_local.astimezone(datetime.timezone.utc)
                clima = _clima_no_instante(
                    tempos, series, instante_utc, parametros.intervalo_minutos
                )
                tbs = clima["tbs"]
                ur = clima["ur"]
                tpo = calcular_ponto_orvalho(tbs, ur)
                tbu = calcular_bulbo_umido(tbs, ur)
                valor, status, entradas = _indice(
                    zona, tbs, tbu, tpo, clima["vento"], clima["radiacao"]
                )
                animais = simular_animais(
                    config, instante_local, tbs, ur,
                    parametros.intervalo_minutos, rng,
                )
                qualidade = "reanálise_interpolada" if clima["interpolado"] else "reanálise_horária"
                origem = {
                    "tbs_externa_c": FONTE_CLIMA,
                    "ur_externa_pct": FONTE_CLIMA,
                    "velocidade_vento_ms": FONTE_CLIMA,
                    "precipitacao_mm": FONTE_CLIMA,
                    "pressao_hpa": FONTE_CLIMA,
                    "radiacao_w_m2": FONTE_CLIMA,
                    "nebulosidade_pct": FONTE_CLIMA,
                    "ponto_orvalho_c": "calculado por Magnus a partir de TBS e UR ERA5",
                    "tbu_c": "calculado por Stull a partir de TBS e UR ERA5",
                    "animais": (
                        "simulação de grupo parametrizada por área, densidade e peso; "
                        "CIGR/ASABE/NASEM"
                    ),
                }
                medicao = {
                    "execucao_id": execucao_id,
                    "zona_id": zona["id"],
                    "zona_nome": zona["nome"],
                    "especie": zona["especie"],
                    "indice": zona["indice"],
                    "timestamp_utc": instante_utc.isoformat(timespec="minutes"),
                    "timestamp_local": instante_local.isoformat(timespec="minutes"),
                    "fuso_horario": config["fuso_horario"],
                    "tbs_externa_c": round(tbs, 3),
                    "ur_externa_pct": round(ur, 3),
                    "ponto_orvalho_c": round(min(tbs, tpo), 3),
                    "tbu_c": round(min(tbs, tbu), 3),
                    "velocidade_vento_ms": round(clima["vento"], 3),
                    "precipitacao_mm": round(clima["precipitacao"], 5),
                    "pressao_hpa": round(clima["pressao"], 2),
                    "radiacao_w_m2": round(clima["radiacao"], 2),
                    "nebulosidade_pct": round(clima["nebulosidade"], 2),
                    "valor_indice": round(valor, 4),
                    "status_termico": status,
                    "area_util_m2": round(float(config["area_util_m2"]), 3),
                    "densidade_categoria": config["densidade_categoria"],
                    "densidade_animais_m2": round(
                        float(config["densidade_animais_m2"]), 6
                    ),
                    "origem_variaveis": origem,
                    "indicador_qualidade": qualidade,
                    "entradas_indice": {k: round(v, 4) for k, v in entradas.items()},
                    "simulation_seed": seed_zona,
                    **animais,
                }
                lote.append(medicao)
                if len(lote) >= 1000:
                    dados_db.inserir_medicoes(lote)
                    total += len(lote)
                    lote.clear()
            if lote:
                dados_db.inserir_medicoes(lote)
                total += len(lote)
        dados_db.concluir_execucao(execucao_id, total)
    except Exception as erro:
        dados_db.falhar_execucao(execucao_id, str(erro))
        raise
    return {
        "ok": True,
        "execucao_id": execucao_id,
        "total_medicoes": total,
        "total_zonas": len(zonas),
        "data_inicio": parametros.data_inicio.isoformat(),
        "data_fim": parametros.data_final.isoformat(),
        "dias": parametros.dias,
        "intervalo_minutos": parametros.intervalo_minutos,
        "fonte_clima": FONTE_CLIMA,
    }
