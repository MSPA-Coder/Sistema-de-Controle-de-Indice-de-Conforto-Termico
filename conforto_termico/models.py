# -*- coding: utf-8 -*-
"""
models.py
=========
Classes de dominio inspiradas literalmente no Diagrama de Classes da
dissertacao (Figura 14, secao 3.3.3): Temperatura, Resfriamento e Email.

No documento original, o diagrama descreve:
    Temperatura     -Temperatura: double        +VerificarTemperatura(): void
                                                  +CalcularICT(): void
    Resfriamento    -TipoDeResfriador: int       +Ativar(): void
                                                  +Desativar(): void
    Email           -Destino: char               +Enviar(): void
                    -Conteudo: char               +InformarEnvio(): void

As tres classes abaixo implementam esses mesmos metodos, adaptados para
Python/Flask.
"""

from __future__ import annotations

import datetime
import os
import smtplib
from email.mime.text import MIMEText

from . import thermal_indices as ti


class Temperatura:
    """Corresponde a classe 'Temperatura' da Figura 14: recebe leituras
    (manuais ou de sensores simulados) e calcula o Indice de Conforto
    Termico (ICT) apropriado para a especie selecionada."""

    def __init__(self, especie: str, indice: str):
        if especie not in ti.ESPECIES_VALIDAS:
            raise ti.EntradaInvalidaError(f"Espécie inválida: '{especie}'.")
        if not ti.indice_disponivel(especie, indice):
            raise ti.EntradaInvalidaError(
                f"O índice {indice} não está disponível para {ti.NOME_ESPECIE.get(especie, especie)}."
            )
        self.especie = especie
        self.indice = indice
        self.temperatura: float | None = None  # ultimo valor calculado (ICT)
        self.entradas: dict = {}  # ultimas entradas validadas (para persistir o historico)

    def verificar_temperatura(self, entradas: dict) -> dict:
        """Valida os dados recebidos (digitados ou de sensores remotos)."""
        return ti.validar_entradas(self.indice, entradas)

    def calcular_ict(self, entradas: dict) -> tuple[float, str]:
        """Calcula o Indice de Conforto Termico e devolve (valor, status)."""
        entradas_validas = self.verificar_temperatura(entradas)
        valor = round(ti.CALCULADORAS[self.indice](**entradas_validas), 2)
        status = ti.classificar_status(valor, self.especie, self.indice)
        self.temperatura = valor
        self.entradas = entradas_validas
        return valor, status


class Resfriamento:
    """Corresponde a classe 'Resfriamento' da Figura 14: representa o estado
    dos equipamentos remotos (ventiladores e nebulizadores) descritos na
    secao 4.3 da dissertacao."""

    ORDEM_INTENSIDADE = {
        None: 0,
        "baixa": 1,
        "media": 2,
        "maxima": 3,
    }

    INTENSIDADE_POR_ORDEM = {
        0: None,
        1: "baixa",
        2: "media",
        3: "maxima",
    }

    # tipo_de_resfriador: 0=nenhum, 1=ventilador, 2=nebulizador, 3=ambos
    def __init__(self):
        self.tipo_de_resfriador: int = 0
        self.ativo: bool = False
        self.intensidade: str | None = None
        self.intensidade_reducao_pendente: str | None = None
        self.leituras_reducao_consecutivas: int = 0

    def ativar(self, intensidade: str) -> None:
        self._aplicar_intensidade(intensidade)

    def _aplicar_intensidade(self, intensidade: str | None) -> None:
        if intensidade is None:
            self.desativar()
            return

        self.ativo = True
        self.intensidade = intensidade
        self.tipo_de_resfriador = 3  # a dissertacao liga ventilador + nebulizador juntos
        self.intensidade_reducao_pendente = None
        self.leituras_reducao_consecutivas = 0

    def desativar(self) -> None:
        self.ativo = False
        self.intensidade = None
        self.tipo_de_resfriador = 0
        self.intensidade_reducao_pendente = None
        self.leituras_reducao_consecutivas = 0

    def registrar_leitura(self, status: str, leituras_para_reduzir: int = 3) -> None:
        nova_intensidade = ti.intensidade_do_status(status)
        ordem_atual = self.ORDEM_INTENSIDADE[self.intensidade]
        nova_ordem = self.ORDEM_INTENSIDADE[nova_intensidade]

        if nova_ordem > ordem_atual:
            self._aplicar_intensidade(nova_intensidade)
            return

        if nova_ordem == ordem_atual:
            self.intensidade_reducao_pendente = None
            self.leituras_reducao_consecutivas = 0
            return

        intensidade_reduzida = self.INTENSIDADE_POR_ORDEM[ordem_atual - 1]
        if self.intensidade_reducao_pendente != intensidade_reduzida:
            self.intensidade_reducao_pendente = intensidade_reduzida
            self.leituras_reducao_consecutivas = 1
        else:
            self.leituras_reducao_consecutivas += 1

        if self.leituras_reducao_consecutivas >= leituras_para_reduzir:
            self._aplicar_intensidade(intensidade_reduzida)

    def estado(self) -> dict:
        return {
            "ativo": self.ativo,
            "intensidade": self.intensidade,
            "ventilador": self.ativo,
            "nebulizador": self.ativo,
            "intensidade_reducao_pendente": self.intensidade_reducao_pendente,
            "leituras_reducao_consecutivas": self.leituras_reducao_consecutivas,
            "leituras_conforto_consecutivas": (
                self.leituras_reducao_consecutivas
                if self.intensidade_reducao_pendente is None
                else 0
            ),
        }


class Email:
    """Corresponde a classe 'Email' da Figura 14: monta e (opcionalmente)
    envia a notificacao, no mesmo formato mostrado nas Figuras 20/22/25/28
    da dissertacao.

    Sem variaveis de ambiente de SMTP configuradas, opera em modo simulado:
    o conteudo e montado normalmente para exibicao na tela, mas nenhum
    e-mail real e disparado."""

    def __init__(self, destino: str, conteudo: str):
        self.destino = destino
        self.conteudo = conteudo
        self._enviado = False

    def enviar(self) -> bool:
        host = os.environ.get("SMTP_HOST")
        if not host:
            self._enviado = False
            return False
        porta = int(os.environ.get("SMTP_PORT", "587"))
        usuario = os.environ.get("SMTP_USER")
        senha = os.environ.get("SMTP_PASS")
        try:
            msg = MIMEText(self.conteudo, _charset="utf-8")
            msg["Subject"] = "Alerta - Sistema de Controle dos Índices de Conforto Térmico"
            msg["From"] = usuario
            msg["To"] = self.destino
            with smtplib.SMTP(host, porta, timeout=10) as servidor:
                servidor.starttls()
                servidor.login(usuario, senha)
                servidor.sendmail(usuario, [self.destino], msg.as_string())
            self._enviado = True
        except Exception:
            self._enviado = False
        return self._enviado

    def informar_envio(self) -> bool:
        return self._enviado

    @staticmethod
    def montar_conteudo(indice: str, valor: float, status: str) -> str:
        """Monta o texto do e-mail no mesmo layout das Figuras 20/22/25/28."""
        agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        return (
            f"Status: {status}\n"
            f"Data: {agora}\n"
            f"Valor do {indice}: {valor}\n"
            f"Mensagem: {ti.mensagem_do_status(status)}\n"
            + "*" * 75
            + "\n"
            "Você está recebendo esse e-mail por estar cadastrado na lista de "
            "usuários do Sistema de Controle dos Índices de Conforto Térmico. "
            "Em caso de dúvida contate o administrador do sistema.\nObrigado."
        )
