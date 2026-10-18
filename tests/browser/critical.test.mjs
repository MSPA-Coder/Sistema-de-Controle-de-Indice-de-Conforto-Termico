import assert from 'node:assert/strict';
import {test} from 'node:test';
import {chromium} from 'playwright';

const base = process.env.BASE_URL;
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
