import assert from 'node:assert/strict';
import {test} from 'node:test';
import {chromium} from 'playwright';

const base = process.env.BASE_URL;

test('login acompanha o idioma do navegador inclusive na mensagem de erro', async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({locale: 'en-US'});
  page.setDefaultTimeout(12000);
  try {
    await page.goto(base + '/login');
    assert.equal(await page.locator('html').getAttribute('lang'), 'en');
    await page.getByRole('heading', {name: 'Thermal Comfort'}).waitFor();
    await page.getByLabel('User', {exact: true}).fill('usuario-inexistente');
    await page.getByLabel('Password', {exact: true}).fill('senha-sintetica');
    await page.getByRole('button', {name: 'Sign in', exact: true}).click();
    await page.getByRole('alert').getByText('Invalid username or password.', {exact: true}).waitFor();
  } catch (error) {
    await page.screenshot({path: '/results/conforto-idioma-login.png', fullPage: true});
    throw error;
  } finally { await browser.close(); }
});

test('conta em inglês mostra preferências e validação de senha traduzidas', async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({locale: 'pt-BR'});
  page.setDefaultTimeout(12000);
  try {
    await page.goto(base + '/login');
    await page.getByLabel('Usuário', {exact: true}).fill('browser-en');
    await page.getByLabel('Senha', {exact: true}).fill('Synthetic-browser-only-2026!');
    await Promise.all([page.waitForURL(base + '/'), page.getByRole('button', {name: 'Entrar', exact: true}).click()]);
    await page.getByRole('tab', {name: 'Analysis', exact: true}).waitFor();
    assert.equal(await page.evaluate(() => window.t('Preferências')), 'Preferences');
    const recommendation = 'As condições de temperatura exigem atenção imediata. Caso seja possível, ligue ventiladores ou nebulizadores. O índice já vem caindo nos últimos 15 minutos. 2 sensores sem leitura recente -- confira a conexão Modbus antes de confiar no índice mostrado.';
    assert.equal(await page.evaluate(text => window.traduzirRecomendacao(text), recommendation), 'Temperature conditions require immediate attention. If possible, turn on fans or misters. The index has been falling over the last 15 minutes. 2 sensors have no recent readings -- check the Modbus connection before relying on the displayed index.');
    assert.equal(await page.evaluate(text => window.traduzirRecomendacao(text), recommendation + ' Texto desconhecido.'), recommendation + ' Texto desconhecido.');
    assert.equal(await page.evaluate(text => window.traduzirErro(text), "Selecione uma das cidades de referência da zona 'A <B> O'Connor'."), "Select one of the reference cities for zone 'A <B> O'Connor'.");
    assert.equal(await page.evaluate(text => window.traduzirErro(text), 'latitude deve estar entre -90 e 90.'), 'latitude must be between -90 and 90.');
    assert.equal(await page.evaluate(text => window.traduzirErro(text), 'Erro desconhecido.'), 'Erro desconhecido.');
    await page.getByText('STALE DATA', {exact: true}).first().waitFor();
    assert.match(await page.locator('[data-role="icones-ventilador"]').first().getAttribute('aria-label'), /^Fan off/);
    await page.getByRole('tab', {name: 'Analysis', exact: true}).click();
    await page.getByText('Comfort in the last 24h', {exact: true}).first().waitFor();
    await page.getByRole('tab', {name: 'History', exact: true}).click();
    await page.locator('#filtro-historico-resolucao').waitFor();
    assert.match(await page.locator('#filtro-historico-resolucao').innerText(), /15-minute aggregate/i);
    await page.getByRole('tab', {name: 'Input data', exact: true}).click();
    await page.locator('#dados-zona-1-densidade_categoria').waitFor();
    assert.match(await page.locator('#dados-zona-1-densidade_categoria').innerText(), /Above average/);
    assert.equal(await page.locator('#dados-zona-1-densidade_categoria').inputValue(), 'media');
    await page.getByRole('tab', {name: 'Registration', exact: true}).click();
    await page.locator('#btn-nova-zona').click();
    await page.locator('#dialog-zona').getByRole('heading', {name: 'New zone', exact: true}).waitFor();
    await page.locator('#btn-cancelar-zona').click();
    await page.getByRole('tab', {name: 'Operation', exact: true}).click();
    await page.locator('#zona-principal').selectOption('1');
    await page.waitForFunction(() => document.querySelector('#operacao-estado-atuadores')?.textContent.includes('Desired — fan:'));
    assert.match(await page.locator('#campo-wrap-tbs label').innerText(), /Dry-bulb \/ ambient temperature/i);
    await page.locator('#campo-tbs-regional').fill('26,5');
    await page.locator('#campo-tbu-regional').fill('22,5');
    await page.locator('#campo-tbu-regional').blur();
    await page.locator('#btn-calcular').click();
    const calculation = page.getByRole('dialog');
    await calculation.getByText('Save the current settings and calculate this zone?', {exact: true}).waitFor();
    await calculation.getByRole('button', {name: 'Cancel', exact: true}).click();
    await api(page, '/api/__browser__/collector-fault', 'POST', {enabled: true});
    try {
      await page.locator('#btn-calcular').click();
      await calculation.getByRole('button', {name: 'Confirm', exact: true}).click();
      await page.waitForFunction(() => document.querySelector('#mensagem-erro')?.textContent.includes('The collector service is temporarily unavailable. Try again shortly.'));
      assert.equal(await page.locator('#mensagem-erro').isVisible(), true);
    } finally {
      await api(page, '/api/__browser__/collector-fault', 'POST', {enabled: false});
    }
    await page.goto(base + '/preferencias');
    assert.equal(await page.locator('html').getAttribute('lang'), 'en');
    await page.getByRole('heading', {name: 'Preferences', exact: true}).waitFor();
    await page.locator('label').filter({hasText: 'Date 31/12/2026 · Value 1.234,56'}).waitFor();
    await page.goto(base + '/minha-senha');
    await page.getByLabel('Current password', {exact: true}).fill('invalid-password');
    await page.getByLabel('New password', {exact: true}).fill('New-synthetic-password!');
    await page.getByLabel('Confirm new password', {exact: true}).fill('New-synthetic-password!');
    await page.getByRole('button', {name: 'Change password', exact: true}).click();
    await page.getByRole('alert').getByText('Invalid current password.', {exact: true}).waitFor();
    await page.goto(base + '/usuarios/');
    await page.getByRole('heading', {name: 'Users', exact: true}).waitFor();
    const row = page.getByRole('row').filter({hasText: 'browser-denied'});
    assert.match(await row.innerText(), /Browser <denied> "O'Connor"/);
    await row.getByRole('button', {name: 'Delete', exact: true}).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByText('Delete user Browser <denied> "O\'Connor"? This action cannot be undone.', {exact: true}).waitFor();
    await dialog.getByRole('button', {name: 'Cancel', exact: true}).click();
    await row.getByRole('link', {name: 'Zones', exact: true}).click();
    await page.getByRole('heading', {name: 'Zones for Browser <denied> "O\'Connor"', exact: true}).waitFor();
    await page.getByRole('button', {name: 'Save zones', exact: true}).waitFor();
    await page.goto(base + '/usuarios/novo');
    await page.getByRole('heading', {name: 'New user', exact: true}).waitFor();
    await page.getByLabel('Role', {exact: true}).locator('option').filter({hasText: 'Operator'}).waitFor({state: 'attached'});
  } catch (error) {
    await page.screenshot({path: '/results/conforto-idioma-conta.png', fullPage: true});
    throw error;
  } finally { await browser.close(); }
});

async function logged(region, action) {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.setDefaultTimeout(12000);
  try {
    await page.goto(base + '/login');
    await page.locator('[name=login]').fill('browser-' + region);
    await page.locator('[name=senha]').fill('Synthetic-browser-only-2026!');
    await Promise.all([page.waitForURL(base + '/'), page.getByRole('button', {name: 'Entrar', exact: true}).click()]);
    await page.locator('#zona-principal option').first().waitFor({state: 'attached'});
    await action(page);
  } catch (error) {
    await page.screenshot({path: '/results/conforto-' + region + '-failure.png', fullPage: true});
    throw error;
  } finally { await browser.close(); }
}
async function api(page, path, method = 'GET', data) {
  return page.evaluate(async ({path, method, data}) => {
    const response = await fetch(path, {method, headers: {'Content-Type': 'application/json'},
      body: data === undefined ? undefined : JSON.stringify(data)});
    const text = await response.text();
    return {status: response.status, body: response.headers.get('Content-Type')?.includes('json') ? JSON.parse(text) : text};
  }, {path, method, data});
}
async function confirm(page) {
  await page.getByRole('dialog').getByRole('button', {name: 'Confirmar', exact: true}).click();
}
test('dado antigo não é classificação atual; decimal BR/EUA chega ao coletor e persiste', async () => {
  for (const region of ['br', 'us']) await logged(region, async page => {
    await page.getByText('DADO DESATUALIZADO', {exact: true}).first().waitFor();
    await page.getByRole('tab', {name: 'Operação', exact: true}).click();
    await page.locator('#zona-principal').selectOption('1');
    await page.locator('#campo-tbs-regional').fill(region === 'br' ? '26,5' : '26.5');
    await page.locator('#campo-tbu-regional').fill(region === 'br' ? '22,5' : '22.5');
    await page.locator('#campo-tbu-regional').blur();
    const response = page.waitForResponse(r => r.url().endsWith('/api/zonas/1/calcular'));
    await page.locator('#btn-calcular').click();
    await confirm(page);
    const result = await response;
    assert.equal(result.status(), 200);
    const body = await result.json();
    assert.equal(body.entradas.tbs, 26.5);
    assert.equal(body.entradas.tbu, 22.5);
    const history = await api(page, '/api/zonas/1/historico');
    assert.equal(history.status, 200);
    assert.match(JSON.stringify(history.body), /26.5/);
    assert.equal(await page.locator('#mensagem-erro').isVisible(), false);
  });
});
test('4xx preservado, 502 visível e zona sem ACL recusada pelo servidor', async () => {
  await logged('br', async page => {
    const bad = await api(page, '/api/zonas/1/calcular', 'POST', {entradas: {tbs: 18, tbu: 30}});
    assert.equal(bad.status, 400);
    assert.match(bad.body.erro, /dados informados/);
    await api(page, '/api/__browser__/collector-fault', 'POST', {enabled: true});
    try {
      await page.getByRole('tab', {name: 'Operação', exact: true}).click();
      await page.locator('#campo-tbs-regional').fill('26,5');
      await page.locator('#campo-tbu-regional').fill('22,5');
      await page.locator('#campo-tbu-regional').blur();
      const response = page.waitForResponse(r => r.url().endsWith('/api/zonas/1/calcular'));
      await page.locator('#btn-calcular').click();
      await confirm(page);
      assert.equal((await response).status(), 502);
      await page.waitForFunction(() => document.querySelector('#mensagem-erro').textContent.includes('indisponível'));
    } finally { await api(page, '/api/__browser__/collector-fault', 'POST', {enabled: false}); }
  });
  await logged('denied', async page => {
    const response = await api(page, '/api/zonas/1/calcular', 'POST', {entradas: {tbs: 26.5, tbu: 22.5}});
    assert.equal(response.status, 403);
    assert.ok(response.body.erro);
  });
});
test('filtros inválidos preservam a última consulta e resposta antiga não sobrescreve a nova', async () => {
  await logged('br', async page => {
    await page.getByRole('tab', {name: 'Histórico', exact: true}).click();
    const historicoUrl = response => {
      if (!response.url().includes('/api/historico-leituras?')) return null;
      return new URL(response.url()).searchParams;
    };
    const zone = page.locator('#filtro-historico-zona');
    const zoneResponse = page.waitForResponse(response => {
      const params = historicoUrl(response);
      return params?.get('zona_id') === '2' && !params.has('data_inicio') && !params.has('data_fim');
    });
    await zone.selectOption({label: 'Zona sintética 2'});
    assert.equal((await zoneResponse).status(), 200);

    const inicio = page.locator('#filtro-historico-de-regional');
    const fim = page.locator('#filtro-historico-ate-regional');
    await inicio.waitFor({state: 'visible'});
    await fim.waitFor({state: 'visible'});
    const linhas = page.locator('#tabela-historico tbody tr');
    const fimValido = page.waitForResponse(response => {
      const params = historicoUrl(response);
      return params?.get('zona_id') === '2' && params?.get('data_fim') === '2025-01-01' && !params.has('data_inicio');
    });
    await fim.fill('01/01/2025');
    assert.equal(await fim.inputValue(), '01/01/2025');
    assert.equal(await page.locator('#filtro-historico-ate').inputValue(), '2025-01-01');
    await fim.blur();
    assert.equal((await fimValido).status(), 200);
    await page.waitForFunction(() => document.querySelectorAll('#tabela-historico tbody tr').length === 1);
    assert.match(await linhas.first().innerText(), /70,00/);

    let historicoRequests = 0;
    page.on('request', request => {
      if (request.url().includes('/api/historico-leituras?')) historicoRequests += 1;
    });
    const antesInvalido = historicoRequests;
    await inicio.fill('02/01/2025');
    assert.equal(await inicio.inputValue(), '02/01/2025');
    assert.equal(await page.locator('#filtro-historico-de').inputValue(), '2025-01-02');
    await inicio.blur();
    const aviso = page.locator('#historico-filtro-periodo-status');
    await aviso.getByText('A data inicial não pode ser posterior à data final. Os filtros atuais não foram aplicados; os resultados exibidos são da última consulta válida.', {exact: true}).waitFor();
    assert.equal(historicoRequests, antesInvalido);
    assert.equal(await linhas.count(), 1);
    assert.match(await linhas.first().innerText(), /70,00/);

    const consultaVazia = page.waitForResponse(response => {
      const params = historicoUrl(response);
      return params?.get('zona_id') === '2' && params?.get('data_inicio') === '2025-01-02' && !params.has('data_fim');
    });
    await fim.fill('');
    assert.equal(await page.locator('#filtro-historico-ate').inputValue(), '');
    await fim.blur();
    const respostaVazia = await consultaVazia;
    assert.equal(respostaVazia.status(), 200);
    assert.equal((await respostaVazia.json()).total, 0);
    await page.waitForFunction(() => document.querySelectorAll('#tabela-historico tbody tr').length === 0);

    let liberarAntiga;
    let iniciouAntiga;
    const antigaIniciou = new Promise(resolve => { iniciouAntiga = resolve; });
    const aguardarLiberacao = new Promise(resolve => { liberarAntiga = resolve; });
    const padraoHistorico = '**/api/historico-leituras?*';
    await page.route(padraoHistorico, async route => {
      const params = new URL(route.request().url()).searchParams;
      if (params.get('data_inicio') === '2025-01-02' && params.get('data_fim') === '2025-01-03') {
        iniciouAntiga();
        await aguardarLiberacao;
      }
      await route.continue();
    });
    const respostaAntiga = page.waitForResponse(response => {
      const params = historicoUrl(response);
      return params?.get('data_inicio') === '2025-01-02' && params?.get('data_fim') === '2025-01-03';
    });
    try {
      await fim.fill('03/01/2025');
      assert.equal(await page.locator('#filtro-historico-ate').inputValue(), '2025-01-03');
      await fim.blur();
      await antigaIniciou;

      const respostaNova = page.waitForResponse(response => {
        const params = historicoUrl(response);
        return params?.get('data_fim') === '2025-01-03' && !params.has('data_inicio');
      });
      await inicio.fill('');
      assert.equal(await page.locator('#filtro-historico-de').inputValue(), '');
      await inicio.blur();
      const respostaNovaRecebida = await respostaNova;
      assert.equal(respostaNovaRecebida.status(), 200);
      assert.equal((await respostaNovaRecebida.json()).total, 1);
      await page.waitForFunction(() => document.querySelectorAll('#tabela-historico tbody tr').length === 1);
      assert.match(await linhas.first().innerText(), /70,00/);

      liberarAntiga();
      const respostaAntigaRecebida = await respostaAntiga;
      assert.equal(respostaAntigaRecebida.status(), 200);
      assert.equal((await respostaAntigaRecebida.json()).total, 0);
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert.equal(await linhas.count(), 1);
      assert.match(await linhas.first().innerText(), /70,00/);
    } finally {
      liberarAntiga();
      await page.unroute(padraoHistorico);
    }
  });
});
test('série pequena publica só ao concluir; staging não exporta nem copia', {timeout: 60000}, async () => {
  await logged('br', async page => {
    await page.getByRole('tab', {name: 'Dados de entrada', exact: true}).click();
    await page.locator('#dados-entrada-dias').fill('1');
    await page.locator('#dados-entrada-intervalo').fill('60');
    await page.locator('#dados-entrada-data-final-regional').fill('01/10/2026');
    await page.locator('#dados-entrada-data-final-regional').blur();
    const generated = page.waitForResponse(r => r.url().endsWith('/api/dados-entrada/gerar'));
    await page.locator('#btn-gerar-dados-entrada').click();
    await confirm(page);
    try {
      await page.waitForFunction(async () => {
        const state = await (await fetch('/api/__browser__/state')).json();
        return state.weather_requests === 2 && state.staging === 24;
      });
      const running = (await api(page, '/api/__browser__/state')).body.execucoes[0];
      assert.equal(running.status, 'processando');
      const exported = await api(page, '/api/dados-entrada/exportar.csv?execucao_id=' + running.id);
      assert.equal(exported.status, 200);
      assert.equal(exported.body.trim().split(/\r?\n/).length, 1);
      const copy = await api(page, '/api/dados-entrada/copiar-para-historico', 'POST', {execucao_id: running.id});
      assert.equal(copy.status, 400);
      assert.equal(await page.getByRole('link', {name: 'CSV', exact: true}).count(), 0);
      assert.equal(await page.getByRole('button', {name: 'Copiar para histórico', exact: true}).count(), 0);
      await api(page, '/api/__browser__/weather-release', 'POST', {});
      const done = await generated;
      assert.equal(done.status(), 201);
      assert.equal((await done.json()).total_medicoes, 48);
      await page.getByRole('link', {name: 'CSV', exact: true}).waitFor();
      const csv = await api(page, '/api/dados-entrada/exportar.csv?execucao_id=' + running.id);
      assert.equal(csv.body.trim().split(/\r?\n/).length, 49);
      const first = await api(page, '/api/dados-entrada/copiar-para-historico', 'POST', {execucao_id: running.id});
      const replay = await api(page, '/api/dados-entrada/copiar-para-historico', 'POST', {execucao_id: running.id});
      assert.equal(first.status, 200);
      assert.equal(first.body.novas_copiadas, 48);
      assert.equal(replay.body.novas_copiadas, 0);
    } finally { await api(page, '/api/__browser__/weather-release', 'POST', {}); }
  });
});
