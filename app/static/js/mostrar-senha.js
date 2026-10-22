// "Mostrar senha" das telas de conta (trocar senha, novo usuário).
// Arquivo próprio porque a CSP é `script-src 'self'`: nada de <script> inline.
for (const caixa of document.querySelectorAll("input[data-mostrar-senha]")) {
  caixa.addEventListener("change", () => {
    const formulario = caixa.closest("form");
    if (!formulario) return;
    // Só os campos que o próprio marcador governa: depois de virar "text" o
    // tipo original se perde, então ele fica registrado no atributo.
    for (const campo of formulario.querySelectorAll("input[data-era-senha], input[type='password']")) {
      campo.dataset.eraSenha = "1";
      campo.type = caixa.checked ? "text" : "password";
    }
  });
}
