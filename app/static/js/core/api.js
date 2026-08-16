const TOKEN_CSRF = document.querySelector('meta[name="csrf-token"]')?.content || "";
const FETCH_NATIVO = window.fetch.bind(window);
const METODOS_HTTP_SEGUROS = new Set(["GET", "HEAD", "OPTIONS"]);

// Todas as mutações da interface usam fetch relativo ao mesmo host. Centralizar
// o cabeçalho aqui evita depender de cada tela lembrar da proteção CSRF.
export function configurarFetchComCsrf() {
  window.fetch = function fetchComCsrf(entrada, opcoes = {}) {
    const metodo = String(
      opcoes.method || (entrada instanceof Request ? entrada.method : "GET")
    ).toUpperCase();
    if (TOKEN_CSRF && !METODOS_HTTP_SEGUROS.has(metodo)) {
      const headers = new Headers(
        entrada instanceof Request ? entrada.headers : undefined
      );
      new Headers(opcoes.headers || {}).forEach((valor, chave) => {
        headers.set(chave, valor);
      });
      headers.set("X-CSRF-Token", TOKEN_CSRF);
      opcoes = { ...opcoes, headers };
    }
    return FETCH_NATIVO(entrada, opcoes);
  };
}
