import base64
import os

assets_dir = '/e/AI/projects/SLG-IdleTD/assets'
output_path = '/e/AI/projects/SLG-IdleTD/output/playable.html'

def b64(filename):
    with open(os.path.join(assets_dir, filename), 'rb') as f:
        return base64.b64encode(f.read()).decode('ascii')

print("Loading assets...")
b64_bg = b64('Map_2048.png')
b64_tower = b64('TowerA.png')
b64_wall = b64('WallA.png')
b64_normal = b64('MOB_Cactus01_red_D.png')
b64_boss = b64('MOB_Boss_Cactus_Crown_D.png')
b64_arrow = b64('Arrow.png')
b64_coin = b64('Coin.png')
b64_button = b64('Button.png')
b64_hit = b64('Effect_Star_1.png')
b64_hp = b64('HPSlider.png')
b64_shadow = b64('Shadow.png')
b64_turret = b64('TurretIcon.png')
print("Assets loaded.")

# Build HTML
html = open('/e/AI/projects/SLG-IdleTD/playable_template.html', 'r', encoding='utf-8').read()
html = html.replace('__B64_BG__', b64_bg)
html = html.replace('__B64_TOWER__', b64_tower)
html = html.replace('__B64_WALL__', b64_wall)
html = html.replace('__B64_NORMAL__', b64_normal)
html = html.replace('__B64_BOSS__', b64_boss)
html = html.replace('__B64_ARROW__', b64_arrow)
html = html.replace('__B64_COIN__', b64_coin)
html = html.replace('__B64_BUTTON__', b64_button)
html = html.replace('__B64_HIT__', b64_hit)
html = html.replace('__B64_HP__', b64_hp)
html = html.replace('__B64_SHADOW__', b64_shadow)
html = html.replace('__B64_TURRET__', b64_turret)

os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)

size = os.path.getsize(output_path)
print(f"Output: {output_path}")
print(f"Size: {size} bytes ({size/1024:.1f} KB) ({size/1024/1024:.2f} MB)")
print(f"Under 2MB: {size < 2*1024*1024}")
