"""
zona_service.py
================
Orquestra o calculo do indice de conforto termico POR ZONA: le todos os
sensores Modbus cadastrados na zona, tira a MEDIA das leituras quando ha
mais de um sensor para o mesmo campo (ex.: duas leituras de tbs viram uma
unica media de tbs), deriva ur/ponto de orvalho a partir de tbs+tbu quando
a zona nao tem sensor dedicado para esses campos, calcula o indice
configurado para a zona -- reaproveitando as mesmas classes de dominio do
fluxo manual (`Temperatura`/`Resfriamento` de models.py) -- e persiste no
historico com o `zona_id`. Tambem aciona os atuadores (ventiladores/
nebulizadores) da zona via Modbus, usando uma instancia de `Resfriamento`
POR ZONA (mesma logica de intensidade/histerese ja usada no fluxo manual,
mas com estado independente por zona: a zona A pode estar em "Perigo"
enquanto a zona B esta em "Conforto").

Uma falha ao ler um sensor especifico ou ao escrever num atuador especifico
nunca derruba o calculo inteiro -- ela fica registrada (sensor: entra na
lista `sensores_com_falha`; atuador: entra em `atuadores_com_falha` e vai
para o log) e o restante do fluxo segue normalmente, seguindo o mesmo
principio de resiliencia ja adotado no resto do projeto (ver
agents.md, "Stability Rules").
"""

from __future__ import annotations

import datetime
import threading
from typing import TYPE_CHECKING, cast

from . import modbus_client
from . import thermal_indices as ti
from .models import Resfriamento, Temperatura

if TYPE_CHECKING:
    from collections.abc import Callable


class ZonaCalculoError(ti.EntradaInvalidaError):
    """Erro ao calcular o indice de uma zona: zona inexistente/desativada,
    ou nenhum sensor respondeu com dados suficientes para o indice
    configurado. Subclasse de `EntradaInvalidaError` para reaproveitar o
    tratamento HTTP de entradas invalidas (400)."""


def _derivar_campos_calculaveis(entradas: dict, altitude: float) -> dict:
    """Deriva 'ur' e 'tpo' a partir de tbs+tbu quando a zona nao tem sensor
    dedicado para esses campos usando
    `thermal_indices.calcular_umidade_relativa` e
    `thermal_indices.calcular_ponto_orvalho`. A regra por zona e sempre
    automatica: se ha sensor cadastrado para o campo, o valor medido vence;
    senao, deriva de tbs/tbu quando isso for possivel."""
    preparadas = dict(entradas)
    if "tbs" in preparadas and "tbu" in preparadas:
        try:
            tbs = float(preparadas["tbs"])
            tbu = float(preparadas["tbu"])
            if "ur" not in preparadas:
                preparadas["ur"] = round(ti.calcular_umidade_relativa(tbs, tbu, altitude), 1)
            if "tpo" not in preparadas:
                preparadas["tpo"] = round(ti.calcular_ponto_orvalho(tbs, tbu, altitude), 1)
        except (ti.EntradaInvalidaError, TypeError, ValueError):
            # Deixa a validacao normal do indice (mais abaixo, em
            # Temperatura.calcular_ict) reclamar do campo que realmente
            # faltar, com uma mensagem mais especifica do que esta funcao
            # conseguiria dar aqui.
            pass
    return preparadas


class ZonaService:
    def __init__(
        self,
        obter_zona: Callable[[int], dict | None],
        salvar_leitura: Callable,
        obter_configuracoes: Callable,
        obter_historico: Callable,
        salvar_estado_equipamentos: Callable[..., None],
        obter_controle_zona: Callable[[int], dict | None],
        ler_modbus_real: Callable = modbus_client.ler_valor,
        escrever_modbus_real: Callable = modbus_client.escrever_valor,
        ler_estado_atuador_real: Callable | None = None,
        simulador=None,
        limite_historico_grafico: int = 30,
        salvar_leitura_recente: Callable | None = None,
    ):
        self._obter_zona = obter_zona
        self._salvar_leitura = salvar_leitura
        self._obter_configuracoes = obter_configuracoes
        self._obter_historico = obter_historico
        # Persiste o estado ligado/desligado dos atuadores a cada ciclo de
        # calculo (`database.salvar_estado_equipamentos`) -- e o que
        # permite ao "Painel executivo por zona" (agora inteiramente em
        # `database.obter_painel_zonas`) saber quantos equipamentos estao
        # ligados sem depender do estado em memoria deste servico.
        self._salvar_estado_equipamentos = salvar_estado_equipamentos
        self._obter_controle_zona = obter_controle_zona
        self._ler_modbus_real = ler_modbus_real
        self._escrever_modbus_real = escrever_modbus_real
        self._ler_estado_atuador_real = ler_estado_atuador_real
        # `simulador` (um `modbus_simulador.SimuladorModbusZonas`, opcional)
        # substitui a comunicacao Modbus real por valores simulados quando
        # a configuracao `modoSimuladoZonas` estiver ligada (ver
        # `_em_modo_simulado`). Sem um simulador injetado, o servico sempre
        # usa as funcoes "reais" (uteis em testes que querem controlar
        # exatamente o que cada leitura devolve).
        self._simulador = simulador
        # Uma instancia de Resfriamento por zona: cada zona tem seu proprio
        # estado de intensidade/histerese, independente das demais.
        self._resfriadores: dict[int, Resfriamento] = {}
        self._historicos_grafico: dict[int, list[dict]] = {}
        self._limite_historico_grafico = limite_historico_grafico
        self._salvar_leitura_recente = salvar_leitura_recente
        self._lock = threading.Lock()

    @staticmethod
    def _copiar_leitura(leitura: dict) -> dict:
        copia = dict(leitura)
        copia["entradas"] = dict(leitura["entradas"])
        return copia

    def resfriador_da_zona(self, zona_id: int) -> Resfriamento:
        with self._lock:
            if zona_id not in self._resfriadores:
                self._resfriadores[zona_id] = Resfriamento()
            return self._resfriadores[zona_id]

    def definir_simulador(self, simulador) -> None:
        """Wiring pos-construcao: o simulador (`modbus_simulador.
        SimuladorModbusZonas`) precisa de uma forma de consultar o estado
        de resfriamento atual de uma zona, que so existe DEPOIS que este
        `ZonaService` ja foi criado (`resfriador_da_zona`). Por isso o
        simulador e injetado aqui, em vez de no construtor -- evita uma
        dependencia circular na composicao (ver coletor/estado.py)."""
        self._simulador = simulador

    def limpar_historico_grafico(self, zona_id: int | None = None) -> None:
        with self._lock:
            if zona_id is None:
                self._historicos_grafico.clear()
            else:
                self._historicos_grafico.pop(zona_id, None)

    def limpar_resfriador(self, zona_id: int | None = None) -> None:
        """Descarta o estado ATIVO (ventilador/nebulizador ligado,
        intensidade) mantido em memoria para a zona. Mesmo motivo de
        `limpar_historico_grafico`, que ja faz o equivalente para o
        historico do grafico: sem isso, o estado de uma zona ja excluida
        vazaria para uma zona nova que reaproveitasse o mesmo id."""
        with self._lock:
            if zona_id is None:
                self._resfriadores.clear()
            else:
                self._resfriadores.pop(zona_id, None)

    def _registrar_historico_grafico(
        self, zona: dict, valor: float, status: str, entradas: dict, logger
    ) -> list[dict]:
        leitura = {
            "zona_id": zona["id"],
            "especie": zona["especie"],
            "indice": zona["indice"],
            "criado_em": datetime.datetime.now().isoformat(timespec="seconds"),
            "valor": valor,
            "status": status,
            "entradas": dict(entradas),
        }
        try:
            with self._lock:
                if zona["id"] not in self._historicos_grafico:
                    historico_base = self._obter_historico(
                        zona["id"], limite=self._limite_historico_grafico - 1
                    )
                    self._historicos_grafico[zona["id"]] = historico_base
                self._historicos_grafico[zona["id"]].append(leitura)
                self._historicos_grafico[zona["id"]] = self._historicos_grafico[zona["id"]][
                    -self._limite_historico_grafico :
                ]
                return [self._copiar_leitura(item) for item in self._historicos_grafico[zona["id"]]]
        except Exception:
            if logger:
                logger.exception("Falha ao atualizar historico visual da zona %s", zona["id"])
            return []

    def _em_modo_simulado(self) -> bool:
        if not self._simulador:
            return False
        try:
            configuracoes = self._obter_configuracoes(usar_cache=False)
            return bool(configuracoes.get("modoSimuladoZonas", True))
        except Exception:
            # Falha ao ler a configuracao: assume simulado por seguranca
            # (evita tentar falar com hardware real por engano quando nao
            # se sabe ao certo qual modo esta configurado).
            return True

    def _ler_modbus(self, equipamento: dict):
        if self._em_modo_simulado():
            return self._simulador.ler_valor(equipamento)
        return self._ler_modbus_real(equipamento)

    def _escrever_modbus(self, equipamento: dict, ligar: bool) -> bool:
        if self._em_modo_simulado():
            return cast("bool", self._simulador.escrever_valor(equipamento, ligar))
        return cast("bool", self._escrever_modbus_real(equipamento, ligar))

    def _ler_estado_atuador(self, equipamento: dict) -> bool | None:
        if self._em_modo_simulado() and self._simulador:
            return cast("bool | None", self._simulador.ler_estado_atuador(equipamento))
        if not self._ler_estado_atuador_real:
            return None
        return cast("bool | None", self._ler_estado_atuador_real(equipamento))

    def _controle_da_zona(self, zona_id: int) -> dict:
        controle = self._obter_controle_zona(zona_id)
        return controle or {"modo": "desligado", "acionamento_habilitado": False}

    def _permissao_acionamento(self, zona_id: int) -> tuple[bool, str | None]:
        controle = self._controle_da_zona(zona_id)
        modo = controle.get("modo")
        if modo in ("desligado", "manutencao"):
            return False, f"Zona em modo {modo}."
        if not controle.get("acionamento_habilitado"):
            return False, "Acionamento fisico bloqueado para esta zona."
        try:
            global_habilitado = bool(
                self._obter_configuracoes().get("habilitarEquipamentos", False)
            )
        except Exception:
            global_habilitado = False
        if not global_habilitado:
            return False, "Acionamento fisico bloqueado na configuracao global."
        return True, None

    def ler_sensores(self, equipamentos: list[dict]) -> dict:
        """Le todos os sensores informados via Modbus e devolve a MEDIA das
        leituras por campo, quando ha mais de um sensor para o mesmo
        campo. Sensores que falharem sao ignorados na media (nao entram no
        calculo), mas ficam listados em 'sensores_com_falha' para
        diagnostico -- a leitura so falha por completo se NENHUM sensor de
        um campo necessario responder (ver `calcular`)."""
        leituras_por_campo: dict[str, list[float]] = {}
        falhas: list[str] = []
        for equipamento in equipamentos:
            if equipamento.get("tipo") != "sensor":
                continue
            campo = equipamento.get("campo_medido")
            if not campo:
                continue
            valor = self._ler_modbus(equipamento)
            if valor is None:
                falhas.append(equipamento["nome"])
                continue
            leituras_por_campo.setdefault(campo, []).append(valor)

        medias = {
            campo: round(sum(valores) / len(valores), 2)
            for campo, valores in leituras_por_campo.items()
        }
        return {"entradas": medias, "sensores_com_falha": falhas}

    def calcular(self, zona_id: int, logger=None) -> dict:
        zona = self._obter_zona(zona_id)
        if not zona:
            raise ZonaCalculoError(f"Zona {zona_id} não encontrada.")
        if not zona["ativa"]:
            raise ZonaCalculoError(f"A zona '{zona['nome']}' está desativada.")

        equipamentos = zona["equipamentos"]
        leitura = self.ler_sensores(equipamentos)
        entradas = self._preparar_entradas_da_zona(leitura["entradas"])

        if not any(campo in entradas for campo in ti.CAMPOS_POR_INDICE[zona["indice"]]):
            raise ZonaCalculoError(
                f"Nenhum sensor da zona '{zona['nome']}' respondeu com dados "
                f"suficientes para calcular o índice {zona['indice']}."
            )
        return self._calcular_com_entradas(zona, entradas, leitura["sensores_com_falha"], logger)

    def calcular_manual(self, zona_id: int, entradas: dict, logger=None) -> dict:
        zona = self._obter_zona(zona_id)
        if not zona:
            raise ZonaCalculoError(f"Zona {zona_id} não encontrada.")
        if not zona["ativa"]:
            raise ZonaCalculoError(f"A zona '{zona['nome']}' está desativada.")
        return self._calcular_com_entradas(
            zona, self._preparar_entradas_da_zona(entradas or {}), [], logger
        )

    def _preparar_entradas_da_zona(self, entradas: dict) -> dict:
        try:
            altitude = float(self._obter_configuracoes().get("altitudeMetros") or 0)
        except (TypeError, ValueError) as erro:
            raise ZonaCalculoError("A altitude configurada é inválida.") from erro
        if not -500.0 <= altitude <= 9000.0:
            raise ZonaCalculoError("A altitude configurada deve estar entre -500 e 9000 metros.")
        return _derivar_campos_calculaveis(entradas, altitude)

    def _calcular_com_entradas(
        self, zona: dict, entradas: dict, sensores_com_falha: list[str], logger=None
    ) -> dict:
        zona_id = zona["id"]
        equipamentos = zona["equipamentos"]
        temperatura = Temperatura(zona["especie"], zona["indice"])
        valor, status = temperatura.calcular_ict(entradas)
        entradas_historico = self._entradas_para_historico(
            zona["indice"], temperatura.entradas, entradas
        )
        historico_grafico = self._registrar_historico_grafico(
            zona, valor, status, entradas_historico, logger
        )
        if self._salvar_leitura_recente:
            try:
                self._salvar_leitura_recente(
                    zona_id,
                    zona["especie"],
                    zona["indice"],
                    valor,
                    status,
                    entradas_historico,
                    self._limite_historico_grafico,
                )
            except Exception:
                if logger:
                    logger.exception("Falha ao persistir janela em tempo real da zona %s", zona_id)

        gravado = False
        try:
            gravado = self._salvar_leitura(
                zona["especie"],
                zona["indice"],
                valor,
                status,
                entradas_historico,
                zona_id=zona_id,
            )
        except Exception:
            if logger:
                logger.exception("Falha ao gravar histórico da zona %s", zona_id)

        resfriador = self.resfriador_da_zona(zona_id)
        resfriador.registrar_leitura(status)
        try:
            limite_umidade = float(
                self._obter_configuracoes().get("limiteUmidadeNebulizador") or 70
            )
        except (TypeError, ValueError) as erro:
            raise ZonaCalculoError("O limite de umidade do nebulizador é inválido.") from erro
        if not 0.0 <= limite_umidade <= 100.0:
            raise ZonaCalculoError("O limite de umidade do nebulizador deve estar entre 0 e 100%.")
        resfriador.aplicar_limite_umidade_nebulizador(
            self._numero_ou_none(entradas.get("ur")), limite_umidade
        )

        estado_atuadores = resfriador.estado()
        permitido, bloqueio_atuadores = self._permissao_acionamento(zona_id)
        if permitido:
            resultado_atuadores = self._aplicar_atuadores(equipamentos, estado_atuadores, logger)
        else:
            resultado_atuadores = {
                "falhas": [],
                "confirmado": {"ventilador": None, "nebulizador": None},
            }
        atuadores_com_falha = resultado_atuadores["falhas"]
        qualidade = "degradada" if sensores_com_falha or atuadores_com_falha else "boa"

        try:
            argumentos_estado = (
                zona_id,
                estado_atuadores["ativo"],
                estado_atuadores["nebulizador"],
                estado_atuadores["intensidade"],
                estado_atuadores["ventilador"],
                estado_atuadores["nebulizador"],
                resultado_atuadores["confirmado"]["ventilador"],
                resultado_atuadores["confirmado"]["nebulizador"],
                sensores_com_falha + atuadores_com_falha,
                qualidade,
            )
            self._salvar_estado_equipamentos(*argumentos_estado)
        except Exception:
            if logger:
                logger.exception("Falha ao persistir estado dos equipamentos da zona %s", zona_id)

        if self._em_modo_simulado() and self._simulador:
            # Mantem o estado interno do simulador (resfriamento gradual)
            # em sincronia com o resultado real deste ciclo, exatamente
            # com o calculo mais recente da zona.
            self._simulador.registrar_calculo(
                zona_id, zona["especie"], zona["indice"], entradas_historico, valor, status
            )

        return {
            "zona_id": zona_id,
            "zona_nome": zona["nome"],
            "especie": zona["especie"],
            "indice": zona["indice"],
            "valor": valor,
            "status": status,
            "cor": ti.cor_do_status(status),
            "mensagem": ti.mensagem_do_status(status),
            "entradas": entradas_historico,
            "historico_grafico": historico_grafico,
            "leitura_gravada": gravado,
            "sensores_com_falha": sensores_com_falha,
            "equipamento": resfriador.estado(),
            "estado_desejado": {
                "ventilador": estado_atuadores["ventilador"],
                "nebulizador": estado_atuadores["nebulizador"],
            },
            "estado_confirmado": resultado_atuadores["confirmado"],
            "atuadores_com_falha": atuadores_com_falha,
            "acionamento_bloqueado": bloqueio_atuadores,
            "modo_operacao": self._controle_da_zona(zona_id).get("modo"),
            "qualidade": qualidade,
            "modo_simulado": self._em_modo_simulado(),
        }

    @staticmethod
    def _entradas_para_historico(
        indice: str, entradas_validas: dict, entradas_preparadas: dict
    ) -> dict:
        entradas_historico = dict(entradas_validas)
        extras = ("tbs", "tbu", "ur", "tpo") if indice == "IGNU" else ("ur", "tpo")
        for campo in extras:
            if campo in entradas_preparadas and campo not in entradas_historico:
                entradas_historico[campo] = entradas_preparadas[campo]
        return entradas_historico

    @staticmethod
    def _numero_ou_none(valor) -> float | None:
        if valor is None or valor == "":
            return None
        try:
            return float(str(valor).replace(",", "."))
        except (TypeError, ValueError):
            return None

    def _aplicar_atuadores(self, equipamentos: list[dict], estado: dict, logger) -> dict:
        falhas: list[str] = []
        confirmacoes: dict[str, list[bool | None]] = {
            "ventilador": [],
            "nebulizador": [],
        }
        for equipamento in equipamentos:
            if equipamento.get("tipo") == "ventilador":
                ligar = estado["ventilador"]
            elif equipamento.get("tipo") == "nebulizador":
                ligar = estado["nebulizador"]
            else:
                continue

            sucesso = self._escrever_modbus(equipamento, ligar)
            confirmado = self._ler_estado_atuador(equipamento) if sucesso else None
            confirmacoes[equipamento["tipo"]].append(confirmado)
            if not sucesso:
                falhas.append(equipamento["nome"])
                if logger:
                    logger.warning("Falha ao acionar equipamento Modbus '%s'", equipamento["nome"])
            elif confirmado is None:
                falhas.append(f"{equipamento['nome']} (sem confirmacao)")
            elif confirmado != ligar:
                falhas.append(f"{equipamento['nome']} (estado divergente)")

        def _consolidar(valores: list[bool | None]) -> bool | None:
            if not valores or any(valor is None for valor in valores):
                return None
            unicos = set(valores)
            return valores[0] if len(unicos) == 1 else None

        return {
            "falhas": falhas,
            "confirmado": {tipo: _consolidar(valores) for tipo, valores in confirmacoes.items()},
        }

    def comandar_manual(self, zona_id: int, tipo: str, ligar: bool, logger=None) -> dict:
        """Comanda um grupo de atuadores somente no modo manual.

        O metodo nao altera sensores nem calcula indice. A persistencia do
        resultado parcial fica com o gerenciador da malha, que consegue
        preservar o estado do outro tipo de atuador no banco.
        """
        if tipo not in ("ventilador", "nebulizador"):
            raise ZonaCalculoError("Tipo de atuador invalido.")
        if not isinstance(ligar, bool):
            raise ZonaCalculoError("O estado do comando precisa ser booleano.")

        zona = self._obter_zona(zona_id)
        if not zona:
            raise ZonaCalculoError(f"Zona {zona_id} nao encontrada.")
        if not zona["ativa"]:
            raise ZonaCalculoError(f"A zona '{zona['nome']}' esta desativada.")

        controle = self._controle_da_zona(zona_id)
        if controle.get("modo") != "manual":
            raise ZonaCalculoError("Comandos diretos so sao aceitos no modo manual.")

        permitido, bloqueio = self._permissao_acionamento(zona_id)
        if not permitido:
            raise ZonaCalculoError(bloqueio or "Acionamento fisico bloqueado.")

        equipamentos = [
            equipamento for equipamento in zona["equipamentos"] if equipamento.get("tipo") == tipo
        ]
        if not equipamentos:
            raise ZonaCalculoError(f"A zona '{zona['nome']}' nao possui {tipo} cadastrado.")

        estado = {"ventilador": False, "nebulizador": False}
        estado[tipo] = ligar
        resultado = self._aplicar_atuadores(equipamentos, estado, logger)
        return {
            "zona_id": zona_id,
            "zona_nome": zona["nome"],
            "tipo": tipo,
            "desejado": ligar,
            "confirmado": resultado["confirmado"][tipo],
            "atuadores_com_falha": resultado["falhas"],
            "qualidade": "boa" if not resultado["falhas"] else "degradada",
        }

    def desativar_atuadores(self, zona_id: int, logger=None) -> dict:
        """Solicita desligamento de todos os atuadores de uma zona.

        Esta operacao e usada ao entrar em modo desligado/manutencao e nao
        depende das travas de acionamento: desligar e a transicao segura.
        """
        zona = self._obter_zona(zona_id)
        if not zona:
            raise ZonaCalculoError(f"Zona {zona_id} nao encontrada.")

        estado = {"ventilador": False, "nebulizador": False}
        resultado = self._aplicar_atuadores(zona["equipamentos"], estado, logger)
        self.resfriador_da_zona(zona_id).desativar()
        return {
            "zona_id": zona_id,
            "zona_nome": zona["nome"],
            "desejado": estado,
            "confirmado": resultado["confirmado"],
            "atuadores_com_falha": resultado["falhas"],
            "qualidade": "boa" if not resultado["falhas"] else "degradada",
        }
