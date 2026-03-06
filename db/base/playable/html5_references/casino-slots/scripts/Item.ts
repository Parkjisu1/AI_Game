import { Easing, Tween } from "@tweenjs/tween.js";
import { Sprite } from "./Core/RenderElements/Sprite";
import { Slot } from "./Slot";

export class Item extends Sprite {

    private isDragging: Boolean = false;
    private eventData: any;
    private startPosition: { x: number, y: number };
    protected _type: string;
    protected _slot: Slot;

    get type() { return this._type };
    get slot() { return this._slot };
    set slot(value: Slot) { this._slot = value };

    constructor(config) {
        super(config);
        this._type = config.type;
        this.unlock();

        this.init();
    }

    async moveItem(x: number, y: number, type: string, time: number) {
        this.node.visible = true;
        await this.tweens.to(this.node, { x, y }, time);
    }

    complete(): void {
        this.hide();
    }

    lock() {
        this.node.interactive = false;
    }

    unlock() {
        this.node.interactive = true;
    }

    private init(): void {
        this.node.scale.set(1.5);
        this.startPosition = { x: this.node.x, y: this.node.y };

    }

    disappear(): Promise<void> {
        return this.tweens.to(this.node.scale, { x: 0, y: 0 }, 250, { easing: Easing.Quadratic.InOut });
    }

}