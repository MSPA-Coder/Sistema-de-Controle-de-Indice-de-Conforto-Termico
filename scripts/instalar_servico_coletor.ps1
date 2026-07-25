<#
instalar_servico_coletor.ps1
==============================
Instala/atualiza o processo COLETOR (run_coletor.py) como serviço do
Windows usando NSSM (https://nssm.cc/), sem precisar mudar nenhum
código -- só embrulha o mesmo `python.exe run_coletor.py` de sempre num
serviço supervisionado pelo Service Control Manager (inicia no boot,
reinicia sozinho se cair, redireciona stdout/stderr para arquivo).

Não instala nem baixa o NSSM sozinho -- de propósito. Baixar e rodar um
executável de terceiros sem o operador confirmar cada passo não é algo
que este script deveria fazer silenciosamente. Baixe o NSSM manualmente
em https://nssm.cc/download, extraia `nssm.exe` (usar a versão win64) e
informe o caminho abaixo, ou coloque `nssm.exe` no PATH.

USO (PowerShell como Administrador):
    .\instalar_servico_coletor.ps1
    .\instalar_servico_coletor.ps1 -NssmPath "C:\ferramentas\nssm.exe" -Porta 5000

Para desinstalar:
    .\instalar_servico_coletor.ps1 -Desinstalar
#>

param(
    [string]$NomeServico = "ConfortoTermicoColetor",
    [string]$NssmPath = "nssm.exe",
    [string]$PythonPath = "",
    [string]$ProjetoPath = (Split-Path -Parent $PSScriptRoot),
    [string]$Porta = "",
    [switch]$Desinstalar
)

$ErrorActionPreference = "Stop"

function Resolver-Comando($nome) {
    $cmd = Get-Command $nome -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$nssm = Resolver-Comando $NssmPath
if (-not $nssm -and (Test-Path $NssmPath)) { $nssm = (Resolve-Path $NssmPath).Path }
if (-not $nssm) {
    Write-Error "NSSM nao encontrado ('$NssmPath'). Baixe em https://nssm.cc/download, extraia nssm.exe e rode de novo passando -NssmPath 'C:\caminho\nssm.exe' (ou deixe no PATH)."
    exit 1
}

if ($Desinstalar) {
    Write-Host "Parando e removendo o servico '$NomeServico'..."
    & $nssm stop $NomeServico 2>$null
    & $nssm remove $NomeServico confirm
    Write-Host "Servico removido. run_coletor.py e instance/historico.db NAO foram apagados."
    exit 0
}

if (-not $PythonPath) {
    $python = Resolver-Comando "python.exe"
    if (-not $python) {
        Write-Error "python.exe nao encontrado no PATH. Informe -PythonPath 'C:\caminho\python.exe' (o do ambiente virtual do projeto, se houver um)."
        exit 1
    }
    $PythonPath = $python
}

$runColetor = Join-Path $ProjetoPath "run_coletor.py"
if (-not (Test-Path $runColetor)) {
    Write-Error "run_coletor.py nao encontrado em '$ProjetoPath'. Rode este script de dentro de scripts\, ou informe -ProjetoPath."
    exit 1
}

Write-Host "Instalando servico '$NomeServico'"
Write-Host "  Python:  $PythonPath"
Write-Host "  Script:  $runColetor"
Write-Host "  Projeto: $ProjetoPath"

& $nssm install $NomeServico $PythonPath $runColetor
& $nssm set $NomeServico AppDirectory $ProjetoPath
& $nssm set $NomeServico DisplayName "ConfortoTermico - Coletor"
& $nssm set $NomeServico Description "Le sensores, calcula o indice de conforto e aciona equipamentos (ConfortoTermico). Reinicia sozinho se cair."
& $nssm set $NomeServico Start SERVICE_AUTO_START
& $nssm set $NomeServico AppExit Default Restart
& $nssm set $NomeServico AppStdout (Join-Path $ProjetoPath "instance\coletor_servico.log")
& $nssm set $NomeServico AppStderr (Join-Path $ProjetoPath "instance\coletor_servico.log")
& $nssm set $NomeServico AppRotateFiles 1
& $nssm set $NomeServico AppRotateBytes 10485760

if ($Porta) {
    & $nssm set $NomeServico AppEnvironmentExtra "CONFORTO_PORT=$Porta"
}

Write-Host ""
Write-Host "Servico instalado. Para iniciar agora:"
Write-Host "  nssm start $NomeServico"
Write-Host "Para conferir status:"
Write-Host "  nssm status $NomeServico"
Write-Host "Log em: $ProjetoPath\instance\coletor_servico.log"
Write-Host ""
Write-Host "Lembrete: a conta que roda o servico (por padrao, Sistema Local) precisa"
Write-Host "de permissao de leitura/escrita em '$ProjetoPath\instance' e, se o coletor"
Write-Host "usar Modbus RTU, de acesso a porta COM correspondente. Se algo falhar so"
Write-Host "quando rodando como servico (mas funcionar rodando manualmente no terminal),"
Write-Host "comece verificando essas duas permissoes."
