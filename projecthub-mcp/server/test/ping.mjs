// e2e smoke: GET /health, POST /ping (Unity bridge), POST /inspect.scene.list
const MCP = process.env.MCP_URL || 'http://localhost:7900';
const TOKEN = process.env.PROJECTHUB_MCP_TOKEN || '';

async function call(path, body = '{}', method = 'POST') {
    const headers = { 'Content-Type': 'application/json' };
    if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
    const res = await fetch(`${MCP}/${path}`, {
        method, headers,
        body: method === 'GET' ? undefined : body,
    });
    return { status: res.status, body: await res.text() };
}

(async () => {
    console.log('1) GET /health');
    console.log('  ', await call('health', null, 'GET'));

    console.log('\n2) POST /ping (→ Unity bridge)');
    console.log('  ', await call('ping'));

    console.log('\n3) POST /inspect.scene.list');
    console.log('  ', await call('inspect.scene.list'));
})();
