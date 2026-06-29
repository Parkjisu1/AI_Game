// Quick unit test for the BalloonFlow export adapter logic.
// Run: node __test_balloonflow_export.mjs

// ── 알고리즘 함수만 inline 복사 (라우트의 동작 검증용) ──
const PRIMARY_TABLE = {
  easy:      [10, 20],
  normal:    [20, 30],
  hard:      [20, 30, 40],
  superHard: [20, 30, 40, 50],
};
const SECONDARY_TABLE = {
  easy:      [30, 40, 50],
  normal:    [10, 40, 50],
  hard:      [10, 50],
  superHard: [10],
};

function dartCapacityMax(railCap) {
  if (railCap <= 40) return 30;
  if (railCap <= 80) return 40;
  return 50;
}

function mulberry32(seed) {
  let t = seed >>> 0;
  return () => {
    t = (t + 0x6D2B79F5) >>> 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r = (r + Math.imul(r ^ (r >>> 7), 61 | r)) ^ r;
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function decomposeMagazines(colorDarts, difficulty, dartMax, rng) {
  const primary   = PRIMARY_TABLE[difficulty].filter(m => m <= dartMax);
  const secondary = SECONDARY_TABLE[difficulty].filter(m => m <= dartMax);
  const primEff = primary.length   ? primary   : secondary;
  const secEff  = secondary.length ? secondary : primary;
  if (!primEff.length) return [];
  const out = [];
  let remaining = colorDarts;
  let safety = 0;
  while (remaining >= 10 && safety < 5000) {
    safety++;
    const pool = rng() < 0.7 ? primEff : secEff;
    let candidates = pool.filter(m => m <= remaining);
    if (!candidates.length) {
      candidates = [...primary, ...secondary].filter(m => m <= remaining);
    }
    if (!candidates.length) break;
    const mag = candidates[Math.floor(rng() * candidates.length)];
    const next = remaining - mag;
    if (next < 0 || next % 10 !== 0) continue;
    out.push(mag);
    remaining = next;
  }
  return out;
}

const round1 = n => Math.round(n * 10) / 10;

let pass = 0, fail = 0;
function check(name, cond, detail = "") {
  if (cond) { console.log(`✓ ${name}`); pass++; }
  else      { console.log(`✗ ${name} ${detail}`); fail++; }
}

// ── Test 1: decomposeMagazines 합계 = colorDarts ──
const rng1 = mulberry32(42);
for (const diff of ["easy", "normal", "hard", "superHard"]) {
  for (const cd of [10, 30, 80, 120, 200, 240, 600]) {
    for (const railCap of [40, 80, 120, 160]) {
      const dmax = dartCapacityMax(railCap);
      const mags = decomposeMagazines(cd, diff, dmax, rng1);
      const sum = mags.reduce((s, m) => s + m, 0);
      const allInSet = mags.every(m => [10, 20, 30, 40, 50].includes(m));
      const allUnderMax = mags.every(m => m <= dmax);
      check(
        `decompose(${cd},${diff},rail${railCap},max${dmax}) sum=${sum} mags=[${mags.join(",")}]`,
        sum === cd && allInSet && allUnderMax,
        `expected sum=${cd}, got ${sum}, allInSet=${allInSet}, allUnderMax=${allUnderMax}`,
      );
    }
  }
}

// ── Test 2: 좌표 변환 (Level_0010과 동일한 식) ──
const balloonScale = 0.2;
const gridCols = 20, gridRows = 20;
// col=0, row=0 (top-left, flipY=false)
const x0 = round1((0 - (gridCols - 1) / 2) * balloonScale);
const y0 = round1(((gridRows - 1) / 2 - 0) * balloonScale);
check("coord (col=0,row=0,top) → x=-1.9", x0 === -1.9, `got ${x0}`);
check("coord (col=0,row=0,top) → y=+1.9", y0 === 1.9, `got ${y0}`);

const x19 = round1((19 - 9.5) * balloonScale);
const y19 = round1(((gridRows - 1) / 2 - 19) * balloonScale);
check("coord (col=19,row=19,bot) → x=+1.9", x19 === 1.9, `got ${x19}`);
check("coord (col=19,row=19,bot) → y=-1.9", y19 === -1.9, `got ${y19}`);

// flipY=true
const yFlip0 = round1((0 - (gridRows - 1) / 2) * balloonScale);
check("coord flipY=true (row=0) → y=-1.9", yFlip0 === -1.9, `got ${yFlip0}`);

// ── Test 3: 좌표 0.2 간격 ──
const yA = round1(((gridRows - 1) / 2 - 0) * balloonScale);
const yB = round1(((gridRows - 1) / 2 - 1) * balloonScale);
check("coord row 0→1 step = -0.2", round1(yA - yB) === 0.2, `delta=${yA-yB}`);

// ── Test 4: dartCapacityMax 매핑 ──
check("dartMax(40) === 30", dartCapacityMax(40) === 30);
check("dartMax(80) === 40", dartCapacityMax(80) === 40);
check("dartMax(120) === 50", dartCapacityMax(120) === 50);
check("dartMax(160) === 50", dartCapacityMax(160) === 50);

// ── Test 5: 동일 seed → 동일 결과 (재현성) ──
const a = decomposeMagazines(200, "normal", 50, mulberry32(7));
const b = decomposeMagazines(200, "normal", 50, mulberry32(7));
check("same seed → same decomp", JSON.stringify(a) === JSON.stringify(b),
  `a=${JSON.stringify(a)} b=${JSON.stringify(b)}`);

// ── Test 6: 미니 cells → balloons 변환 시뮬레이션 ──
const cells = [
  [-1,  0,  0, -1],
  [ 0,  0,  1,  1],
  [-1,  1, -1, -1],
];
const rows = cells.length, cols = cells[0].length;
const balloons = [];
const colorCounts = {};
for (let r = 0; r < rows; r++) {
  for (let c = 0; c < cols; c++) {
    const v = cells[r][c];
    if (v < 0) continue;
    balloons.push({
      balloonId: balloons.length, color: v,
      gridPosition: {
        x: round1((c - (cols - 1) / 2) * balloonScale),
        y: round1(((rows - 1) / 2 - r) * balloonScale),
      },
    });
    colorCounts[v] = (colorCounts[v] || 0) + 1;
  }
}
check("mini cells balloon count = 7", balloons.length === 7,
  `got ${balloons.length}: ${JSON.stringify(balloons.map(b => b.color))}`);
check("color counts: c0=4, c1=3", colorCounts[0] === 4 && colorCounts[1] === 3,
  `got ${JSON.stringify(colorCounts)}`);
check("first balloon (col=1,row=0) at (x=-0.1,y=0.2)",
  balloons[0].gridPosition.x === -0.1 && balloons[0].gridPosition.y === 0.2,
  `got ${JSON.stringify(balloons[0].gridPosition)}`);

console.log(`\n=== ${pass} passed, ${fail} failed ===`);
process.exit(fail > 0 ? 1 : 0);
