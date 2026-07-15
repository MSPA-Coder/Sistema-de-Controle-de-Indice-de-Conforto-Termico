# -*- coding: utf-8 -*-
"""
services.py
===========
Servicos de aplicacao usados pelas rotas Flask.

As rotas ficam responsaveis por HTTP; este modulo concentra estado em memoria
e regras de negocio que nao pertencem diretamente a camada web.
"""

from __future__ import annotations

import datetime
import random
import threading
from dataclasses import dataclass
from typing import Callable

from . import thermal_indices as ti
from .models import Email, Resfriamento, Temperatura


@dataclass(frozen=True)
class EstadoSensor:
    entradas: dict[str, float]
    valor: float
    status: str


class HistoricoGraficoService:
    """Mantem o historico visual em memoria, separado do historico persistido.

    Padrao aplicado: Service Layer. A rota nao precisa conhecer detalhes de
    cache, copia defensiva ou limite de pontos exibidos nos graficos.
    """

    def __init__(self, obter_historico: Callable, limite: int = 20):
        self._obter_historico = obter_historico
        self._limite = limite
        self._historicos: dict[tuple[str, str], list[dict]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _copiar_leitura(leitura: dict) -> dict:
        copia = dict(leitura)
        copia["entradas"] = dict(leitura["entradas"])
        return copia

    def obter(self, especie: str, indice: str) -> list[dict]:
        chave = (especie, indice)
        with self._lock:
            if chave in self._historicos:
                return [self._copiar_leitura(leitura) for leitura in self._historicos[chave]]

        return self._obter_historico(especie, indice, limite=self._limite)

    def registrar(self, especie: str, indice: str, valor: float, status: str, entradas: dict) -> list[dict]:
        chave = (especie, indice)
        leitura = {
            "criado_em": datetime.datetime.now().isoformat(timespec="seconds"),
            "valor": valor,
            "status": status,
            "entradas": dict(entradas),
        }

        with self._lock:
            if chave not in self._historicos:
                self._historicos[chave] = self._obter_historico(
                    especie, indice, limite=self._limite - 1
                )
            self._historicos[chave].append(leitura)
            self._historicos[chave] = self._historicos[chave][-self._limite:]
            return [self._copiar_leitura(item) for item in self._historicos[chave]]

    def limpar(self, especie: str | None = None, indice: str | None = None) -> None:
        with self._lock:
            if especie and indice:
                self._historicos.pop((especie, indice), None)
            elif especie:
                for chave in list(self._historicos):
                    if chave[0] == especie:
                        self._historicos.pop(chave, None)
            else:
                self._historicos.clear()


class GeradorLeituraAleatoria:
    """Estrategia de geracao aleatoria para o sensor simulado."""

    def gerar(self, indice: str) -> dict[str, float]:
        if indice == "ITU":
            return {
                "tbs": round(random.uniform(18, 40), 1),
                "tbu": round(random.uniform(12, 30), 1),
            }
        if indice == "ITUV":
            return {
                "tbs": round(random.uniform(18, 40), 1),
                "tbu": round(random.uniform(12, 30), 1),
                "v": round(random.uniform(0.1, 5.0), 2),
            }
        if indice == "IGNU":
            return {
                "tgn": round(random.uniform(18, 45), 1),
                "tpo": round(random.uniform(5, 30), 1),
            }
        raise ti.EntradaInvalidaError("Índice inválido.")


class EstrategiaResfriamento:
    """Estrategia de leitura quando ventilador/nebulizador estao ligados."""

    def __init__(
        self,
        fator_resfriamento: float = 0.95,
        fator_ventilacao: float = 1.05,
    ):
        self._fator_resfriamento = fator_resfriamento
        self._fator_ventilacao = fator_ventilacao

    def aplicar(self, especie: str, indice: str, estado: EstadoSensor) -> EstadoSensor:
        entradas = dict(estado.entradas)
        ajustadas = {
            campo: round(self._valor_ajustado(campo, entradas[campo]), 2 if campo == "v" else 1)
            for campo in ti.CAMPOS_POR_INDICE[indice]
        }
        valor, status = ti.calcular_e_classificar(especie, indice, ajustadas)
        return EstadoSensor(entradas=ajustadas, valor=valor, status=status)

    def _valor_ajustado(self, campo: str, valor: float) -> float:
        minimo, maximo = ti.RANGE_VALIDACAO[campo]
        if campo == "v":
            ajustado = valor * self._fator_ventilacao
        elif valor >= 0:
            ajustado = valor * self._fator_resfriamento
        else:
            ajustado = valor / self._fator_resfriamento
        return max(minimo, min(maximo, ajustado))


class SensorSimuladoService:
    """Controla o estado do sensor simulado.

    Padrao aplicado: Strategy. O servico escolhe entre geracao aleatoria e
    estrategia de resfriamento sem expor essa decisao as rotas.
    """

    def __init__(
        self,
        gerador_aleatorio: GeradorLeituraAleatoria | None = None,
        estrategia_resfriamento: EstrategiaResfriamento | None = None,
    ):
        self._gerador_aleatorio = gerador_aleatorio or GeradorLeituraAleatoria()
        self._estrategia_resfriamento = estrategia_resfriamento or EstrategiaResfriamento()
        self._estados: dict[tuple[str, str], EstadoSensor] = {}
        self._lock = threading.Lock()

    def registrar_calculo(
        self,
        especie: str,
        indice: str,
        entradas: dict,
        valor: float,
        status: str,
    ) -> None:
        estado = EstadoSensor(entradas=dict(entradas), valor=valor, status=status)
        with self._lock:
            self._estados[(especie, indice)] = estado

    def gerar(
        self,
        especie: str,
        indice: str,
        resfriamento_ativo: bool,
        ao_atingir_conforto: Callable[[], None] | None = None,
    ) -> dict[str, float]:
        if resfriamento_ativo:
            leitura_resfriada = self._gerar_com_resfriamento(especie, indice, ao_atingir_conforto)
            if leitura_resfriada is not None:
                return leitura_resfriada
        return self._gerador_aleatorio.gerar(indice)

    def _gerar_com_resfriamento(
        self,
        especie: str,
        indice: str,
        ao_atingir_conforto: Callable[[], None] | None,
    ) -> dict[str, float] | None:
        chave = (especie, indice)
        with self._lock:
            estado = self._estados.get(chave)

        if not estado:
            return None

        novo_estado = self._estrategia_resfriamento.aplicar(especie, indice, estado)
        if novo_estado is None:
            if ao_atingir_conforto:
                ao_atingir_conforto()
            return None

        with self._lock:
            self._estados[chave] = novo_estado

        if novo_estado.status == "Conforto" and ao_atingir_conforto:
            ao_atingir_conforto()
        return dict(novo_estado.entradas)

    def limpar(self, especie: str | None = None, indice: str | None = None) -> None:
        with self._lock:
            if especie and indice:
                self._estados.pop((especie, indice), None)
            elif especie:
                for chave in list(self._estados):
                    if chave[0] == especie:
                        self._estados.pop(chave, None)
            else:
                self._estados.clear()


class CalculoIctService:
    """Orquestra o caso de uso de calculo do indice de conforto termico."""

    def __init__(
        self,
        resfriador: Resfriamento,
        historico_grafico: HistoricoGraficoService,
        sensor_simulado: SensorSimuladoService,
        salvar_leitura: Callable,
        obter_historico: Callable,
        email_cls: type[Email] = Email,
        obter_configuracoes: Callable | None = None,
    ):
        self._resfriador = resfriador
        self._historico_grafico = historico_grafico
        self._sensor_simulado = sensor_simulado
        self._salvar_leitura = salvar_leitura
        self._obter_historico = obter_historico
        self._email_cls = email_cls
        # Usado apenas para buscar host/porta/usuario/senha SMTP direto da
        # configuracao persistida no servidor (ver `_smtp_config_atual`).
        # Opcional e por ultimo para nao quebrar quem ja instancia esta
        # classe sem esse parametro -- nesse caso, o envio de e-mail volta a
        # depender só das variaveis de ambiente SMTP_*, como antes.
        self._obter_configuracoes = obter_configuracoes

    def calcular(
        self,
        especie: str,
        indice: str,
        entradas: dict,
        config: dict,
        logger=None,
    ) -> dict:
        if not ti.indice_disponivel(especie, indice):
            raise ti.EntradaInvalidaError(
                f"O índice {indice} não está disponível para {ti.NOME_ESPECIE.get(especie, especie)}."
            )

        entradas_preparadas = self._preparar_entradas(entradas, config, indice)
        resultados = {}
        avisos = []
        for indice_calculado in ti.INDICES_POR_ESPECIE[especie]:
            if indice_calculado != indice and not self._entradas_completas(indice_calculado, entradas_preparadas):
                continue
            resultado = self._calcular_indice(
                especie, indice_calculado, entradas_preparadas, config, logger
            )
            resultados[indice_calculado] = resultado
            if resultado.get("aviso"):
                avisos.append(f"{indice_calculado}: {resultado['aviso']}")

        selecionado = resultados[indice]
        equipamento_info = self._atualizar_equipamentos(
            selecionado["status"], selecionado["entradas"], config, logger
        )
        email_info = self._montar_email(
            indice,
            selecionado["valor"],
            selecionado["status"],
            selecionado["entradas"],
            config,
            logger,
        )

        resposta = dict(selecionado)
        resposta.update(
            {
                "indices": resultados,
                "equipamento": equipamento_info,
                "email": email_info,
                "tocarSom": bool(config.get("habilitarSons")) and selecionado["status"] != "Conforto",
            }
        )
        if avisos:
            resposta["aviso"] = "<br>".join(avisos)
        return resposta

    @staticmethod
    def _numero_config(config: dict, chave: str, padrao: float) -> float:
        try:
            return float(str(config.get(chave, padrao)).replace(",", "."))
        except (TypeError, ValueError):
            return padrao

    @staticmethod
    def _campo_preenchido(entradas: dict, campo: str) -> bool:
        return campo in entradas and CalculoIctService._entrada_preenchida(entradas[campo])

    def _preparar_entradas(self, entradas: dict, config: dict, indice_selecionado: str) -> dict:
        preparadas = dict(entradas)
        altitude = self._numero_config(config, "altitudeMetros", 0.0)
        tem_bulbos = self._campo_preenchido(preparadas, "tbs") and self._campo_preenchido(preparadas, "tbu")
        modo_tpo_calculado = config.get("modoPontoOrvalho") == "calculado"
        modo_ur_calculado = config.get("modoUmidadeRelativa", "calculado") != "medido"

        if tem_bulbos:
            try:
                tbs = float(str(preparadas["tbs"]).replace(",", "."))
                tbu = float(str(preparadas["tbu"]).replace(",", "."))
                if modo_ur_calculado:
                    preparadas["ur"] = round(ti.calcular_umidade_relativa(tbs, tbu, altitude), 1)
                if modo_tpo_calculado:
                    preparadas["tpo"] = round(ti.calcular_ponto_orvalho(tbs, tbu, altitude), 1)
            except ti.EntradaInvalidaError:
                if modo_tpo_calculado or indice_selecionado == "IGNU":
                    raise
            except (TypeError, ValueError):
                pass
        if not tem_bulbos and modo_tpo_calculado and indice_selecionado == "IGNU":
            raise ti.EntradaInvalidaError(
                "Para calcular o ponto de orvalho, preencha tbs e tbu."
            )
        if not modo_ur_calculado and self._campo_preenchido(preparadas, "ur"):
            preparadas["ur"] = self._validar_umidade_relativa(preparadas["ur"])

        return preparadas

    @staticmethod
    def _validar_umidade_relativa(valor) -> float:
        try:
            umidade = float(str(valor).replace(",", "."))
        except (TypeError, ValueError) as err:
            raise ti.EntradaInvalidaError("O valor de 'ur' precisa ser numérico.") from err
        if not (0 <= umidade <= 100):
            raise ti.EntradaInvalidaError(
                f"O valor de 'ur' ({umidade}) está fora da faixa esperada (0 a 100)."
            )
        return umidade

    @staticmethod
    def _entrada_preenchida(valor) -> bool:
        return valor is not None and str(valor).strip() != ""

    def _entradas_completas(self, indice: str, entradas: dict) -> bool:
        return all(
            campo in entradas and self._entrada_preenchida(entradas[campo])
            for campo in ti.CAMPOS_POR_INDICE[indice]
        )

    def _calcular_indice(
        self,
        especie: str,
        indice: str,
        entradas: dict,
        config: dict,
        logger,
    ) -> dict:
        temperatura = Temperatura(especie, indice)
        valor, status = temperatura.calcular_ict(entradas)

        self._sensor_simulado.registrar_calculo(
            especie, indice, temperatura.entradas, valor, status
        )
        entradas_historico = self._entradas_para_historico(indice, temperatura.entradas, entradas)
        historico_grafico = self._registrar_historico_grafico(
            especie, indice, valor, status, entradas_historico, logger
        )
        leitura_gravada, aviso = self._salvar_historico(
            especie, indice, valor, status, entradas_historico, config, logger
        )
        resultado = {
            "indice": indice,
            "valor": valor,
            "status": status,
            "cor": ti.cor_do_status(status),
            "mensagem": ti.mensagem_do_status(status),
            "leitura_gravada": leitura_gravada,
            "entradas": entradas_historico,
            "historico": self._buscar_historico(especie, indice, logger),
            "historico_grafico": historico_grafico,
        }
        if aviso:
            resultado["aviso"] = aviso
        return resultado

    @staticmethod
    def _entradas_para_historico(indice: str, entradas_validas: dict, entradas_preparadas: dict) -> dict:
        entradas_historico = dict(entradas_validas)
        extras = ("tbs", "tbu", "ur") if indice == "IGNU" else ("ur",)
        for campo in extras:
            if campo in entradas_preparadas and campo not in entradas_historico:
                entradas_historico[campo] = entradas_preparadas[campo]
        return entradas_historico

    def _registrar_historico_grafico(
        self,
        especie: str,
        indice: str,
        valor: float,
        status: str,
        entradas: dict,
        logger,
    ) -> list[dict]:
        try:
            return self._historico_grafico.registrar(especie, indice, valor, status, entradas)
        except Exception:
            if logger:
                logger.exception("Falha ao atualizar historico visual dos graficos")
            return []

    def _salvar_historico(
        self,
        especie: str,
        indice: str,
        valor: float,
        status: str,
        entradas: dict,
        config: dict,
        logger,
    ) -> tuple[bool, str | None]:
        try:
            return (
                self._salvar_leitura(
                    especie,
                    indice,
                    valor,
                    status,
                    entradas,
                    config.get("intervaloGravacaoMinutos"),
                ),
                None,
            )
        except Exception:
            if logger:
                logger.exception("Falha ao gravar leitura no banco de dados")
            return (
                False,
                "O valor foi calculado, mas não foi possível salvar no histórico (veja o log do Flask).",
            )

    def _atualizar_equipamentos(self, status: str, entradas: dict, config: dict, logger) -> dict:
        equipamento_info = self._resfriador.estado()
        if not config.get("habilitarEquipamentos"):
            return equipamento_info

        try:
            self._resfriador.registrar_leitura(status)
            limite_umidade = max(
                0.0,
                min(100.0, self._numero_config(config, "limiteUmidadeNebulizador", 70.0)),
            )
            umidade_relativa = None
            if self._campo_preenchido(entradas, "ur"):
                umidade_relativa = float(str(entradas["ur"]).replace(",", "."))
            self._resfriador.aplicar_limite_umidade_nebulizador(
                umidade_relativa,
                limite_umidade,
            )
            return self._resfriador.estado()
        except Exception:
            if logger:
                logger.exception("Falha ao atualizar equipamentos remotos")
            return equipamento_info

    def _smtp_config_atual(self) -> dict:
        """Busca host/porta/usuario/senha SMTP direto da configuracao
        persistida no servidor -- nunca do `config` recebido no corpo do
        request de /api/calcular. O campo de senha e somente-escrita (o
        navegador nunca recebe a senha real de volta, ver
        web._configuracoes_publicas); usar o `config` do request para a
        senha sempre resultaria numa string vazia, mesmo com uma senha
        valida ja salva no banco."""
        if not self._obter_configuracoes:
            return {}
        try:
            persistida = self._obter_configuracoes()
        except Exception:
            return {}
        return {
            "host": persistida.get("smtpHost") or None,
            "porta": persistida.get("smtpPorta") or None,
            "usuario": persistida.get("smtpUsuario") or None,
            "senha": persistida.get("smtpSenha") or None,
        }

    def _montar_email(
        self,
        indice: str,
        valor: float,
        status: str,
        entradas: dict,
        config: dict,
        logger,
    ) -> dict | None:
        if not config.get("enviarEmails"):
            return None
        if not ti.status_atinge_minimo(status, config.get("statusMinimoEmail", "conforto")):
            return None

        try:
            conteudo = self._email_cls.montar_conteudo(indice, valor, status, entradas)
            destino = (config.get("emailDestino") or "produtor@fazenda.com.br").strip()
            email = self._email_cls(destino, conteudo)
            enviado_de_verdade = email.enviar(self._smtp_config_atual())
            return {
                "destino": destino,
                "conteudo": conteudo,
                "enviado_de_verdade": enviado_de_verdade,
            }
        except Exception:
            if logger:
                logger.exception("Falha ao montar/enviar e-mail")
            return None

    def _buscar_historico(self, especie: str, indice: str, logger) -> list[dict]:
        try:
            return self._obter_historico(especie, indice, limite=20)
        except Exception:
            if logger:
                logger.exception("Falha ao consultar historico")
            return []
