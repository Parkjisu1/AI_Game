import { _decorator, Component, input, Input, EventMouse, Animation, Vec3, Camera, geometry, director, Node, Label } from 'cc';
const { ccclass, property } = _decorator;
const { Ray } = geometry;

@ccclass('PlayerController')
export class PlayerController extends Component {
    @property moveSpeed = 250;
    @property weaponLevel = 1;
    @property attackSpeed = 1.5;
    @property attackDuration = 0.4;
    @property({ type: Node }) level1Weapon: Node | null = null;
    @property({ type: Node }) level2Weapon: Node | null = null;
    @property({ type: Node }) level3Weapon: Node | null = null;
    @property({ type: Label }) woodLabel: Label | null = null;
    @property({ type: Label }) stoneLabel: Label | null = null;

    private _moving = false;
    private _attacking = false;
    private _mouse2Held = false;
    private _wood = 0;
    private _stone = 0;
    private _animation: Animation | null = null;
    private _idle = '';
    private _run = '';
    private _attack = '';
    private _current = '';
    private _camera: Camera | null = null;
    private _hitBox: Node | null = null;
    private _safePos: Vec3 | null = null;

    /** Initialize animations, camera reference, and input listeners */
    start() {
        this._animation = this.getComponent(Animation);
        if (this._animation?.clips?.length >= 3) {
            this._idle = this._animation.clips[0].name;
            this._run = this._animation.clips[1].name;
            this._attack = this._animation.clips[2].name;
            this._animation.play(this._idle);
            this._current = this._idle;
        }

        this._camera = this._findCamera(director.getScene());
        this._hitBox = this.node.getChildByName('AttackHitBox');
        input.on(Input.EventType.MOUSE_DOWN, this._onMouseDown, this);
        input.on(Input.EventType.MOUSE_UP, this._onMouseUp, this);
        input.on(Input.EventType.MOUSE_MOVE, this._onMouseMove, this);
    }

    /** Cleanup input listeners */
    onDestroy() {
        input.off(Input.EventType.MOUSE_DOWN, this._onMouseDown, this);
        input.off(Input.EventType.MOUSE_UP, this._onMouseUp, this);
        input.off(Input.EventType.MOUSE_MOVE, this._onMouseMove, this);
    }

    /** Recursively find main camera in scene hierarchy */
    private _findCamera(node: any): Camera | null {
        const cam = node.getComponent(Camera);
        if (cam) return cam;
        for (const child of node.children || []) {
            const result = this._findCamera(child);
            if (result) return result;
        }
        return null;
    }

    /** Handle mouse down: start movement (LMB) or attack (RMB) */
    private _onMouseDown(e: EventMouse) {
        if (e.getButton() === 0) {
            this._rotateToMouse(e);
            this._moving = true;
            this._safePos = null;
        } else if (e.getButton() === 2) {
            this._mouse2Held = true;
            this._startAttack();
        }
    }

    /** Handle mouse up: stop movement (LMB) or release attack (RMB) */
    private _onMouseUp(e: EventMouse) {
        if (e.getButton() === 0 && this._moving) {
            this._safePos = new Vec3().set(this.node.getWorldPosition());
            this._moving = false;
        } else if (e.getButton() === 2) {
            this._mouse2Held = false;
        }
    }

    /** Handle mouse move: rotate player toward cursor */
    private _onMouseMove(e: EventMouse) {
        this._rotateToMouse(e);
    }

    /** Rotate player to face mouse position using raycast */
    private _rotateToMouse(e: EventMouse) {
        if (!this._camera || this._attacking) return;
        
        const ray = new Ray();
        this._camera.screenPointToRay(e.getLocationX(), e.getLocationY(), ray);
        
        const denom = Vec3.dot(ray.d, Vec3.UNIT_Y);
        if (Math.abs(denom) < 0.0001) return;
        
        const t = -Vec3.dot(ray.o, Vec3.UNIT_Y) / denom;
        if (t < 0) return;
        
        const hit = new Vec3();
        Vec3.scaleAndAdd(hit, ray.o, ray.d, t);
        
        const dir = new Vec3(hit.x - this.node.position.x, 0, hit.z - this.node.position.z);
        if (dir.length() <= 0.1) return;
        
        const angle = Math.atan2(dir.x, dir.z) * 180 / Math.PI;
        this.node.setRotationFromEuler(0, angle, 0);
    }

    /** Start attack animation and schedule harvest at peak */
    private _startAttack() {
        if (this._attacking || !this._animation || !this._attack) return;
        
        this._attacking = true;
        const state = this._animation.getState(this._attack);
        if (state) {
            state.speed = this.attackSpeed;
            state.wrapMode = 1;
        }
        this._animation.play(this._attack);
        this._current = this._attack;
        
        const dur = this.attackDuration / this.attackSpeed;
        this.scheduleOnce(() => { if (this._attacking) this._performHarvest(); }, dur * 0.85);
        this.scheduleOnce(() => {
            this._attacking = false;
            this._updateAnim();
            if (this._mouse2Held) this._startAttack();
        }, dur);
    }

    /** Update animation state based on movement/attack */
    private _updateAnim() {
        if (this._attacking || !this._animation) return;
        const target = this._moving ? this._run : this._idle;
        if (target && this._current !== target) {
            this._animation.play(target);
            this._current = target;
        }
    }

    /** Perform harvest: check gate → resource → bench in priority order */
    private _performHarvest() {
        if (!this._hitBox) return;
        
        const hitPos = this._hitBox.getWorldPosition();
        const scale = this._hitBox.getScale();
        const radius = Math.max(scale.x, scale.y, scale.z) * 0.7;
        const scene = director.getScene();
        
        // Gate check (highest priority)
        const gates = scene.getComponentsInChildren('Gate') as any[];
        for (const gate of gates) {
            if (gate.isBroken) continue;
            const gatePos = gate.node.getWorldPosition();
            const dist = Vec3.distance(hitPos, gatePos);
            if (dist < radius * 1.2) {
                if (gate.playTremble) gate.playTremble();
                if (this.weaponLevel >= 3) gate.breakGate();
                return;
            }
        }
        
        // Resource check
        const resources = scene.getComponentsInChildren('Resource') as any[];
        for (const res of resources) {
            if (res.isHarvested) continue;
            const resPos = res.node.getWorldPosition();
            if (Vec3.distance(hitPos, resPos) < radius) {
                if (res.playTremble) res.playTremble();
                if (this.weaponLevel < res.requiredLevel) return;
                this.harvestResource(res);
                return;
            }
        }
        
        // Bench check
        const benches = scene.getComponentsInChildren('CraftingBench') as any[];
        for (const bench of benches) {
            if (bench.isUpgraded) continue;
            const benchPos = bench.node.getWorldPosition();
            if (Vec3.distance(hitPos, benchPos) < radius * 1.5) {
                bench.tryUpgrade(this);
                return;
            }
        }
    }

    /** Harvest resource: increment count and update UI */
    harvestResource(res: any) {
        if (res.isHarvested || this.weaponLevel < res.requiredLevel) return;
        res.harvest();
        if (res.type === 'wood') this._wood++;
        else if (res.type === 'stone') this._stone++;
        this._updateUI();
    }

    /** Update resource counter UI labels */
    private _updateUI() {
        if (this.woodLabel) this.woodLabel.string = this._wood.toString();
        if (this.stoneLabel) this.stoneLabel.string = this._stone.toString();
    }

    /** Equip weapon of specified level */
    setWeaponLevel(level: number) {
        [this.level1Weapon, this.level2Weapon, this.level3Weapon].forEach(w => { if (w) w.active = false; });
        const weapon = level === 1 ? this.level1Weapon : level === 2 ? this.level2Weapon : this.level3Weapon;
        if (weapon) weapon.active = true;
        this.weaponLevel = level;
    }

    /** Upgrade weapon if sufficient resources available */
    upgradeWeapon(level: number, wood: number, stone: number): boolean {
        if (this.weaponLevel >= level || this._wood < wood || this._stone < stone) return false;
        this._wood -= wood;
        this._stone -= stone;
        this.setWeaponLevel(level);
        this._updateUI();
        return true;
    }

    /** Handle player movement with collision avoidance */
    update(dt: number) {
        if (this._moving && !this._attacking) {
            const fwd = this.node.forward;
            const target = new Vec3(this.node.position.x - fwd.x * 0.1, this.node.position.y, this.node.position.z - fwd.z * 0.1);
            if (!this._collides(target)) this.node.setPosition(target);
        }
        
        // Animation state update
        if (!this._attacking && this._animation) {
            const target = this._moving ? this._run : this._idle;
            if (target && this._current !== target) {
                this._animation.play(target);
                this._current = target;
                if (!this._moving && this._collides(this.node.position)) {
                    this.node.setPosition(this._safePos || this.node.position);
                }
            }
        }
        
        // Post-stop collision correction
        if (this._safePos && !this._moving && !this._attacking) {
            if (this._collides(this.node.position)) this.node.setPosition(this._safePos);
            this._safePos = null;
        }
    }

    /** Check if position collides with environmental obstacles */
    private _collides(pos: Vec3): boolean {
        const colliders = director.getScene().getComponentsInChildren('cc.BoxCollider') as any[];
        for (const col of colliders) {
            if (!col?.node?.active || col.isTrigger || col.node.name === 'AttackHitBox' || 
                col.node === this.node || col.node.parent === this.node) continue;
            
            const obsPos = col.node.getWorldPosition();
            const size = col.size || { x: 1, y: 1, z: 1 };
            const obsRadius = Math.max(size.x, size.z) * 0.65;
            const dx = pos.x - obsPos.x;
            const dz = pos.z - obsPos.z;
            if (dx * dx + dz * dz < (0.32 + obsRadius) ** 2) return true;
        }
        return false;
    }
}