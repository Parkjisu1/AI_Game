const c=[];
process.stdin.on('data',d=>c.push(d));
process.stdin.on('end',()=>{
  const r = JSON.parse(c.join(''));
  console.log('='.repeat(70));
  console.log('  IdleMoney Design DB 전체 검색 결과');
  console.log('  총 ' + r.count + '건');
  console.log('='.repeat(70));

  const byDomain = {};
  for (const e of r.results) {
    const d = e.domain || 'Unknown';
    if (!(d in byDomain)) byDomain[d] = [];
    byDomain[d].push(e);
  }

  const order = ['InGame','OutGame','Balance','Content','BM','LiveOps','UX','Meta','Generic'];
  for (const dom of order) {
    const items = byDomain[dom];
    if (!items) continue;
    console.log('');
    console.log('\u2500'.repeat(70));
    console.log('  [' + dom + '] ' + items.length + '\uAC74');
    console.log('\u2500'.repeat(70));

    // Separate tables vs flow/spec
    const tables = items.filter(e => e.data_type === 'table' || e.data_type === 'config' || e.data_type === 'content_data');
    const flows = items.filter(e => e.data_type !== 'table' && e.data_type !== 'config' && e.data_type !== 'content_data');

    if (tables.length > 0) {
      console.log('  -- Data Tables --');
      for (const e of tables) {
        const type = (e.data_type || '').padEnd(13);
        const sys = (e.system || '').substring(0, 26).padEnd(26);
        const area = (e.balance_area || '-').padEnd(14);
        const summ = (e.summary || '').substring(0, 30);
        console.log('    ' + type + sys + area + summ);
      }
    }
    if (flows.length > 0) {
      console.log('  -- Flow / Spec / Formula --');
      for (const e of flows) {
        const type = (e.data_type || '').padEnd(13);
        const sys = (e.system || '').substring(0, 26).padEnd(26);
        const area = (e.balance_area || '-').padEnd(14);
        const tags = (e.tags || []).slice(0, 5).join(', ');
        console.log('    ' + type + sys + area + '[' + tags + ']');
      }
    }
  }

  console.log('');
  console.log('='.repeat(70));
  console.log('  Summary');
  console.log('='.repeat(70));
  const types = {};
  for (const e of r.results) types[e.data_type] = (types[e.data_type]||0)+1;
  console.log('  Data types: ' + Object.entries(types).map(([k,v])=>k+'('+v+')').join(', '));
  const domains = {};
  for (const e of r.results) domains[e.domain] = (domains[e.domain]||0)+1;
  console.log('  Domains:    ' + Object.entries(domains).map(([k,v])=>k+'('+v+')').join(', '));
  const genres = {};
  for (const e of r.results) genres[e.genre] = (genres[e.genre]||0)+1;
  console.log('  Genres:     ' + Object.entries(genres).map(([k,v])=>k+'('+v+')').join(', '));
});
