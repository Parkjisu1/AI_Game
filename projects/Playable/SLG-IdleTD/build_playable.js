const fs = require('fs');
const path = require('path');

const assetsDir   = 'E:\\AI\\projects\\SLG-IdleTD\\assets';
const templatePath = 'E:\\AI\\projects\\SLG-IdleTD\\playable_template.html';
const outputPath  = 'E:\\AI\\projects\\SLG-IdleTD\\output\\playable.html';

function b64(filename) {
  const buf = fs.readFileSync(path.join(assetsDir, filename));
  return buf.toString('base64');
}

console.log('Loading assets...');
const b64_bg     = b64('Map_2048.png');
const b64_tower  = b64('TowerA.png');
const b64_wall   = b64('WallA.png');
const b64_normal = b64('MOB_Cactus01_red_D.png');
const b64_boss   = b64('MOB_Boss_Cactus_Crown_D.png');
const b64_arrow  = b64('Arrow.png');
const b64_coin   = b64('Coin.png');
const b64_button = b64('Button.png');
const b64_hit    = b64('Effect_Star_1.png');
const b64_hp     = b64('HPSlider.png');
const b64_shadow = b64('Shadow.png');
const b64_turret = b64('TurretIcon.png');
console.log('Assets loaded.');

let html = fs.readFileSync(templatePath, 'utf-8');
html = html.replace(/__B64_BG__/g,     b64_bg);
html = html.replace(/__B64_TOWER__/g,  b64_tower);
html = html.replace(/__B64_WALL__/g,   b64_wall);
html = html.replace(/__B64_NORMAL__/g, b64_normal);
html = html.replace(/__B64_BOSS__/g,   b64_boss);
html = html.replace(/__B64_ARROW__/g,  b64_arrow);
html = html.replace(/__B64_COIN__/g,   b64_coin);
html = html.replace(/__B64_BUTTON__/g, b64_button);
html = html.replace(/__B64_HIT__/g,    b64_hit);
html = html.replace(/__B64_HP__/g,     b64_hp);
html = html.replace(/__B64_SHADOW__/g, b64_shadow);
html = html.replace(/__B64_TURRET__/g, b64_turret);

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, html, 'utf-8');

const size = fs.statSync(outputPath).size;
console.log('Output:', outputPath);
console.log('Size:', size, 'bytes |', (size/1024).toFixed(1), 'KB |', (size/1024/1024).toFixed(2), 'MB');
console.log('Under 2MB:', size < 2*1024*1024 ? 'YES' : 'NO');
