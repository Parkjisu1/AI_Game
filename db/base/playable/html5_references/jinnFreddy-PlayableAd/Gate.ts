import { _decorator, Component, Node, Color, MeshRenderer, Vec3, director } from 'cc';
const { ccclass, property } = _decorator;

const FLASH_DUR = 0.06;
const FLASH_COL = new Color(255, 255, 255, 255);
const NO_EMISS = new Color(0, 0, 0, 255);
const TREMBLE_ANG = 3.0;
const TREMBLE_SPD = 20.0;
const TREMBLE_DUR = 0.22;

@ccclass('Gate')
export class Gate extends Component {
    @property requiredLevel = 3; // Required weapon level to break

    isBroken = false;
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
    }

    /** Process gate break: flash + destruction after 3 hits */
    breakGate() {
        if (this.isBroken) return;
        this._hitCount++;
        this._flash();
        if (this._hitCount >= 3) {
            this.isBroken = true;
            this.scheduleOnce(() => {
                this.node.destroy();
                this._triggerMRAID();
            }, 0.15);
        }
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

    /** Flash gate material white for hit feedback */
    private _flash() {
        const renderer = this.node.getComponent(MeshRenderer);
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

    /** Trigger MRAID win flow on gate destruction */
    private _triggerMRAID() {
        const win = window as any;
        if (win.mraid?.open) {
            win.mraid.open('https://play.google.com/store/apps/details?id=com.idle.breaker.game');
        } else if (win.open) {
            win.open('https://play.google.com/store/apps/details?id=com.idle.breaker.game', '_blank');
        }
        director.pause();
    }
}