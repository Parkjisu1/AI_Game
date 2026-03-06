import { _decorator, Component, Node, director, Label, Color } from 'cc';
const { ccclass, property } = _decorator;

const RADIUS = 2.5;
const WHEEL_BASE = 60;
const WHEEL_BOOST = 720;
const BOOST_FRAMES = 300;

@ccclass('CraftingBench')
export class CraftingBench extends Component {
    @property maxLevel = 3;
    @property costWoodLevel2 = 3;
    @property costIronLevel2 = 0;
    @property costWoodLevel3 = 3;
    @property costIronLevel3 = 2;
    @property({ type: Node }) uiNode: Node | null = null;
    @property({ type: Label }) requirementsLabel: Label | null = null;
    @property({ type: Label }) upgradeBtnLabel: Label | null = null;
    @property({ type: Node }) wheelNode: Node | null = null;

    private _player: any = null;
    private _inRange = false;
    private _wheelAngle = 0;
    private _boostFrames = 0;

    /** Initialize bench; find player and setup UI events */
    start() {
        const players = director.getScene().getComponentsInChildren('PlayerController');
        this._player = players[0] || null;
        
        if (this.wheelNode) this._wheelAngle = this.wheelNode.eulerAngles.z;
        
        if (this.uiNode && this.requirementsLabel && this.upgradeBtnLabel) {
            this.uiNode.active = false;
            this.upgradeBtnLabel.node.on(Node.EventType.MOUSE_DOWN, this._onUpgradeClick, this);
            // Pre-warm UI layout to prevent first-activation jump
            this.uiNode.active = true;
            this.uiNode.active = false;
        }
    }

    /** Cleanup UI event listeners */
    onDestroy() {
        this.upgradeBtnLabel?.node.off(Node.EventType.MOUSE_DOWN, this._onUpgradeClick, this);
    }

    /** Update wheel animation and proximity-based UI visibility */
    update(dt: number) {
        // Wheel rotation (continuous with optional boost)
        if (this.wheelNode) {
            const speed = this._boostFrames > 0 ? WHEEL_BOOST : WHEEL_BASE;
            this._wheelAngle += dt * speed;
            this.wheelNode.setRotationFromEuler(0, 0, this._wheelAngle);
            if (this._boostFrames > 0) this._boostFrames--;
        }
        
        // Hide UI if player has max weapon level
        if (!this._player || !this.uiNode || this._player.weaponLevel >= this.maxLevel) {
            this.uiNode.active = false;
            return;
        }
        
        // Proximity check for UI activation
        const p = this._player.node.getWorldPosition();
        const b = this.node.getWorldPosition();
        const inRange = Math.sqrt((p.x - b.x) ** 2 + (p.z - b.z) ** 2) < RADIUS;
        
        if (inRange !== this._inRange) {
            this._inRange = inRange;
            this.uiNode.active = inRange;
        }
        
        // Update UI content when in range
        if (inRange && this.uiNode.active) this._updateUI();
    }

    /** Update UI with current upgrade requirements and button state */
    private _updateUI() {
        if (!this.requirementsLabel || !this.upgradeBtnLabel || !this._player) return;
        
        const next = this._player.weaponLevel + 1;
        const wood = next === 2 ? this.costWoodLevel2 : this.costWoodLevel3;
        const stone = next === 2 ? this.costIronLevel2 : this.costIronLevel3;
        
        // Build requirements text
        let text = `Upgrade to Level ${next}\n`;
        if (wood > 0) text += `Wood: ${this._player._wood}/${wood}\n`;
        if (stone > 0) text += `Stone: ${this._player._stone}/${stone}`;
        this.requirementsLabel.string = text;
        
        // Update button appearance based on resource availability
        const enough = this._player._wood >= wood && this._player._stone >= stone;
        this.upgradeBtnLabel.string = enough ? "UPGRADE" : "NEED MORE";
        this.upgradeBtnLabel.color = enough ? new Color(100, 255, 100, 255) : new Color(150, 150, 150, 255);
    }

    /** Handle upgrade button click (resource check + weapon upgrade) */
    private _onUpgradeClick() {
        if (!this._player || !this._inRange) return;
        
        const next = this._player.weaponLevel + 1;
        if (next > this.maxLevel) return;
        
        const wood = next === 2 ? this.costWoodLevel2 : this.costWoodLevel3;
        const stone = next === 2 ? this.costIronLevel2 : this.costIronLevel3;
        
        // Shake UI if insufficient resources
        if (this._player._wood < wood || this._player._stone < stone) {
            if (this.uiNode) {
                const pos = this.uiNode.getPosition();
                this.uiNode.setPosition(pos.x + 0.15, pos.y, pos.z);
                this.scheduleOnce(() => this.uiNode?.setPosition(pos), 0.1);
            }
            return;
        }
        
        // Trigger wheel boost and perform upgrade
        this._boostFrames = BOOST_FRAMES;
        this._player.upgradeWeapon(next, wood, stone);
    }

    /** External upgrade trigger (for E-key interaction) */
    tryUpgrade(player: any) {
        if (!this._player) this._player = player;
        this._onUpgradeClick();
    }
}