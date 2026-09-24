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
import re
import smtplib
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sharedauth.secrets import DIRETORIO_SECRETS_COMPOSE, resolver_segredo

from app.termico import thermal_indices as ti

# Mesma checagem pragmatica usada em database.py: garante formato minimo de
# e-mail e, principalmente, ausencia de espacos/quebras de linha que
# permitiriam injetar cabecalhos SMTP adicionais no envio abaixo.
_EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def agora_utc() -> datetime.datetime:
    """Instante UTC consciente de fuso, sem microssegundos.

    O banco ainda guarda timestamps como texto por compatibilidade. Novas
    escritas usam sempre o offset explícito; ``parsear_timestamp`` abaixo
    permite ler as linhas antigas, que eram ``datetime`` ingênuos.
    """
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0)


def timestamp_utc() -> str:
    return agora_utc().isoformat(timespec="seconds")


def parsear_timestamp(valor: object) -> datetime.datetime:
    """Lê ISO-8601 novo e legado, normalizando o resultado para UTC."""
    if not isinstance(valor, str):
        raise ValueError("timestamp precisa ser texto ISO-8601")
    momento = datetime.datetime.fromisoformat(valor)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=datetime.UTC)
    return momento.astimezone(datetime.UTC)


def como_utc_iso(valor: object) -> object:
    """O instante com o offset explícito (`+00:00`), para o navegador ler certo.

    Janelas e horas agregadas são gravadas em UTC SEM offset, e `new Date()` no
    navegador lê texto sem offset como hora LOCAL: os gráficos mostravam cada
    janela 3 h fora do lugar. Valor que não é texto ISO passa como está.
    """
    if not isinstance(valor, str) or not valor:
        return valor
    try:
        return parsear_timestamp(valor).isoformat(timespec="seconds")
    except ValueError:
        return valor


def fuso_local() -> ZoneInfo:
    """O fuso em que o usuário lê as datas: o `TZ` do contêiner."""
    try:
        return ZoneInfo(os.environ.get("TZ") or "America/Sao_Paulo")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("America/Sao_Paulo")


def limites_utc_do_periodo(
    data_inicio: str | None, data_fim: str | None
) -> tuple[str | None, str | None]:
    """Dias LOCAIS de/até viram o intervalo UTC semiaberto [início, fim).

    Os filtros da tela mandam datas do calendário do usuário; o banco guarda
    instantes UTC em texto ISO. Comparar `2026-09-24 00:00:00` direto com esse
    texto recortava o dia em UTC -- das 21h do dia anterior às 21h do dia, no
    horário de Brasília. Os limites saem sem offset, no mesmo formato
    `AAAA-MM-DDTHH:MM:SS` do texto gravado, para a comparação de texto (e os
    índices sobre ela) continuar valendo tanto para linhas com `+00:00` quanto
    para janelas gravadas sem offset.
    """
    fuso = fuso_local()

    def _utc(dia: datetime.date) -> str:
        meia_noite = datetime.datetime.combine(dia, datetime.time(0), tzinfo=fuso)
        return meia_noite.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S")

    inicio = _utc(datetime.date.fromisoformat(data_inicio)) if data_inicio else None
    fim = (
        _utc(datetime.date.fromisoformat(data_fim) + datetime.timedelta(days=1))
        if data_fim
        else None
    )
    return inicio, fim


def _email_valido(endereco: object) -> bool:
    return isinstance(endereco, str) and bool(_EMAIL_REGEX.fullmatch(endereco.strip()))


def _resolver_senha_smtp() -> str | None:
    """Senha do servidor SMTP, nunca guardada no banco (CT-03).

    Host/porta/usuário continuam editáveis pela tela e persistidos em
    `configuracoes` -- não são segredo. A senha é o único campo que saía de lá
    em texto claro, replicado todo dia pelo dump que o BackupRestore gera e
    cataloga. `resolver_segredo` aceita tanto `SMTP_PASS_FILE` (segredo do
    Compose, ausente por padrão -- SMTP é recurso opcional, nenhuma
    instalação é obrigada a provisionar este arquivo) quanto a variável direta
    `SMTP_PASS`, já documentada em `.env.example` como o fallback deste app
    quando o campo correspondente está vazio.
    """
    return resolver_segredo("SMTP_PASS", caminho_esperado=DIRETORIO_SECRETS_COMPOSE / "smtp_password")


def senha_smtp_configurada() -> bool:
    """Só para a tela saber se há senha configurada -- nunca expõe o valor."""
    return bool(_resolver_senha_smtp())


def formatar_linhas_entradas(entradas: dict | None) -> list[str]:
    """Monta, uma por linha, a descricao "- Rótulo (campo): valor unidade"
    de cada entrada usada num calculo (ex.: temperatura, umidade). Ponto
    unico dessa formatacao, reutilizado pelos e-mails de alerta e pelos
    resumos consolidados de zonas."""
    if not entradas:
        return []

    linhas = ["Dados usados no cálculo:"]
    for campo, valor in entradas.items():
        metadados = ti.CAMPO_METADADOS.get(campo, {})
        label = metadados.get("label", campo)
        unidade = metadados.get("unidade", "")
        sufixo = f" {unidade}" if unidade else ""
        linhas.append(f"- {label} ({campo}): {valor}{sufixo}")
    return linhas


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
        # A função de conveniência é a fonte única da sequência
        # validar -> calcular -> arredondar -> classificar. Isso evita que o
        # fluxo manual e o coletor discordem na fronteira de uma faixa.
        entradas_validas = self.verificar_temperatura(entradas)
        valor, status = ti.calcular_e_classificar(self.especie, self.indice, entradas_validas)
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
        self.nebulizador_ativo: bool = False
        self.intensidade: str | None = None
        self.intensidade_reducao_pendente: str | None = None
        self.leituras_reducao_consecutivas: int = 0

    def _aplicar_intensidade(self, intensidade: str | None) -> None:
        if intensidade is None:
            self.desativar()
            return

        self.ativo = True
        self.intensidade = intensidade
        self.tipo_de_resfriador = 3  # a dissertacao liga ventilador + nebulizador juntos
        self.nebulizador_ativo = True
        self.intensidade_reducao_pendente = None
        self.leituras_reducao_consecutivas = 0

    def desativar(self) -> None:
        self.ativo = False
        self.intensidade = None
        self.tipo_de_resfriador = 0
        self.nebulizador_ativo = False
        self.intensidade_reducao_pendente = None
        self.leituras_reducao_consecutivas = 0

    def aplicar_limite_umidade_nebulizador(
        self,
        umidade_relativa: float | None,
        limite_umidade: float,
    ) -> None:
        if not self.ativo:
            self.nebulizador_ativo = False
            self.tipo_de_resfriador = 0
            return

        self.nebulizador_ativo = umidade_relativa is not None and umidade_relativa <= limite_umidade
        self.tipo_de_resfriador = 3 if self.nebulizador_ativo else 1

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
            "nebulizador": self.nebulizador_ativo,
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

    def enviar(self, smtp_config: dict | None = None) -> bool:
        """Envia o e-mail via SMTP.

        `smtp_config` (opcional) traz host/porta/usuario vindos da
        configuracao persistida no banco -- nunca a senha (CT-03: ela nao
        fica no banco, para nao ir parar em texto claro num dump). Quando um
        campo especifico vem vazio, a respectiva variavel de ambiente
        (`SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`) e usada como fallback; a senha
        vem sempre de `_resolver_senha_smtp` (segredo do Compose ou
        `SMTP_PASS`)."""
        import logging

        logger = logging.getLogger(__name__)

        smtp_config = smtp_config or {}
        host = smtp_config.get("host") or os.environ.get("SMTP_HOST")
        if not host:
            self._enviado = False
            return False
        if not _email_valido(self.destino):
            # Defesa em profundidade: o caminho normal ja valida o
            # destinatario em database.salvar_configuracoes, mas esta classe
            # nunca deve montar uma mensagem SMTP com um valor fora do
            # formato esperado, mesmo que chegue aqui por outro caminho no
            # futuro. Isso evita injecao de cabecalhos adicionais (ex.:
            # "Bcc:") via quebras de linha ou caracteres de controle.
            self._enviado = False
            return False
        host = str(host)
        porta = smtp_config.get("porta") or int(os.environ.get("SMTP_PORT", "587"))
        usuario = str(smtp_config.get("usuario") or os.environ.get("SMTP_USER") or "")
        senha = str(smtp_config.get("senha") or _resolver_senha_smtp() or "")
        try:
            msg = MIMEText(self.conteudo, _charset="utf-8")
            msg["Subject"] = "Alerta - Sistema de Controle dos Índices de Conforto Térmico"
            msg["From"] = usuario
            msg["To"] = self.destino
            with smtplib.SMTP(host, int(porta), timeout=10) as servidor:
                servidor.starttls()
                # Credenciais sao usadas apenas internamente - nunca logadas
                servidor.login(usuario, senha)
                servidor.sendmail(usuario, [self.destino], msg.as_string())
            self._enviado = True
        except smtplib.SMTPAuthenticationError:
            logger.error("Falha de autenticação SMTP para %s", host)
            self._enviado = False
        except smtplib.SMTPConnectError:
            logger.error("Não foi possível conectar ao SMTP %s:%s", host, porta)
            self._enviado = False
        except Exception as erro:
            # Sanitizar log para evitar expor credenciais
            logger.error("Erro ao enviar e-mail: %s", str(erro))
            self._enviado = False
        return self._enviado

    @staticmethod
    def _formatar_entradas(entradas: dict | None) -> str:
        linhas = formatar_linhas_entradas(entradas)
        return ("\n".join(linhas) + "\n") if linhas else ""

    @staticmethod
    def _formatar_zona(zona: dict | None) -> str:
        if not zona:
            return ""

        nome = zona.get("nome") or zona.get("zona_nome")
        zona_id = zona.get("id") or zona.get("zona_id")
        if nome and zona_id:
            return f"Zona: {nome} (ID {zona_id})\n"
        if nome:
            return f"Zona: {nome}\n"
        if zona_id:
            return f"Zona: ID {zona_id}\n"
        return ""

    @staticmethod
    def montar_conteudo(
        indice: str,
        valor: float,
        status: str,
        entradas: dict | None = None,
        zona: dict | None = None,
    ) -> str:
        """Monta o texto do e-mail no mesmo layout das Figuras 20/22/25/28."""
        agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        return (
            f"Status: {ti.rotulo_do_status(status)}\n"
            f"Data: {agora}\n"
            f"{Email._formatar_zona(zona)}"
            f"Valor do {indice}: {valor}\n"
            f"{Email._formatar_entradas(entradas)}"
            f"Mensagem: {ti.mensagem_do_status(status)}\n" + "*" * 75 + "\n"
            "Você está recebendo esse e-mail por estar cadastrado na lista de "
            "usuários do Sistema de Controle dos Índices de Conforto Térmico. "
            "Em caso de dúvida contate o administrador do sistema.\nObrigado."
        )
