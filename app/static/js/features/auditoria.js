export function criarAuditoria({ documento = document, requisitar = (...args) => fetch(...args) }) {
  const document = documento;
  const fetch = requisitar;

  function texto(valor) { return valor == null || valor === "" ? "—" : String(valor); }
  function contexto(evento) {
    const dados = evento.contexto || {};
    return [dados.method, dados.path, dados.ip].filter(Boolean).join(" · ") || "—";
  }
  async function carregar() {
    const corpo = document.querySelector("#tabela-auditoria tbody");
    const vazio = document.getElementById("auditoria-vazia");
    if (!corpo || !vazio) return;
    try {
      const resposta = await fetch("/api/auditoria?limite=100");
      if (!resposta.ok) throw new Error("Resposta de auditoria inválida");
      const dados = await resposta.json();
      const eventos = Array.isArray(dados.eventos) ? dados.eventos : [];
      corpo.textContent = "";
      vazio.classList.toggle("oculto", eventos.length > 0);
      eventos.forEach((evento) => {
        const linha = document.createElement("tr");
        [texto(evento.criado_em).replace("T", " ").replace("+00:00", " UTC"), `${texto(evento.ator_login)} (${texto(evento.ator_perfil)})`, texto(evento.acao), contexto(evento)].forEach((valor) => {
          const celula = document.createElement("td"); celula.textContent = valor; linha.appendChild(celula);
        });
        corpo.appendChild(linha);
      });
    } catch (erro) {
      console.error("Não foi possível carregar a auditoria:", erro);
      corpo.textContent = ""; vazio.textContent = "Não foi possível carregar a trilha de auditoria."; vazio.classList.remove("oculto");
    }
  }
  function inicializar() { document.getElementById("btn-atualizar-auditoria")?.addEventListener("click", carregar); }
  return { carregar, inicializar };
}
