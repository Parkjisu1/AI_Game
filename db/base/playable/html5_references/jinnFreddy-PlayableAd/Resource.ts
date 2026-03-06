import { _decorator, Component, Node, Color, MeshRenderer, Vec3 } from 'cc';
const { ccclass, property } = _decorator;

const FLASH_DUR = 0.06;
const FLASH_COL = new Color(255, 255, 255, 255);
const NO_EMISS = new Color(0, 0, 0, 255);
const TREMBLE_ANG = 2.5;
const TREMBLE_SPD = 20.0;
const TREMBLE_DUR = 0.20;

@ccclass('Resource')
export class Resource extends Component {
    @property type = 'wood';          // Resource type: 'wood' or 'stone'
    @property requiredLevel = 1;      // Required weapon level to harvest
    @property({ type: Node }) state0: Node | null = null; // Intact visual
    @property({ type: Node }) state1: Node | null = null; // Damaged visual
    @property({ type: Node }) state2: Node | null = null; // Broken visual

    isHarvested = false;
    private _hitCount = 0;
    private _initPos = new Vec3();
    private _initX = 0;
    private _initY = 0;
    private _initZ = 0;
    private _trembling = false;
    private _trembleTime = 0;

    /** Cache initial position and rotation for tremble stability */
    start() {
        this.node.getWorldPosition(this._initPos);
        const e = this.node.eulerAngles;
        this._initX = e.x;
        this._initY = e.y;
        this._initZ = e.z;
        this._updateState();
    }

    /** Process harvest: flash + state transition (3 hits to destroy) */
    harvest() {
        if (this.isHarvested) return;
        this._hitCount++;
        this._flash();
        this._updateState();
        this._flash();
        if (this._hitCount >= 3) this.scheduleOnce(() => this.node.active = false, 0.15);
    }

    /** Start tremble animation (called on every hit) */
    playTremble() {
        this._trembling = true;
        this._trembleTime = 0;
    }

    /** Update tremble animation: Y-axis wobble with position locking */
    update(dt: number) {
        if (!this._trembling) return;
        
        this._trembleTime += dt;
        this.node.setWorldPosition(this._initPos);
        
        // Smooth sine-wave oscillation on Y-axis
        const angle = Math.sin(this._trembleTime * Math.PI * 2 * TREMBLE_SPD) * TREMBLE_ANG;
        this.node.setRotationFromEuler(this._initX, this._initY + angle, this._initZ);
        
        // End tremble after duration
        if (this._trembleTime >= TREMBLE_DUR) {
            this._trembling = false;
            this.node.setWorldPosition(this._initPos);
            this.node.setRotationFromEuler(this._initX, this._initY, this._initZ);
        }
    }

    /** Flash current active state material white for hit feedback */
    private _flash() {
        const state = this._getActiveState();
        if (!state) return;
        
        const renderer = state.getComponent(MeshRenderer);
        const mat = renderer?.getMaterialInstance(0);
        if (!mat) return;
        
        // Try emissive first, fallback to mainColor
        try { mat.setProperty('emissive', FLASH_COL); }
        catch { try { mat.setProperty('mainColor', FLASH_COL); } catch {} }
        
        // Revert after flash duration
        this.scheduleOnce(() => {
            if (!renderer?.isValid) return;
            const m = renderer.getMaterialInstance(0);
            if (!m) return;
            try { m.setProperty('emissive', NO_EMISS); }
            catch { try { m.setProperty('mainColor', FLASH_COL); } catch {} }
        }, FLASH_DUR);
    }

    /** Get currently active visual state node */
    private _getActiveState(): Node | null {
        return this.state0?.active ? this.state0 : 
               this.state1?.active ? this.state1 : 
               this.state2?.active ? this.state2 : null;
    }

    /** Update visual state based on hit count */
    private _updateState() {
        if (this.state0) this.state0.active = this._hitCount === 0;
        if (this.state1) this.state1.active = this._hitCount === 1;
        if (this.state2) this.state2.active = this._hitCount >= 2;
    }
}