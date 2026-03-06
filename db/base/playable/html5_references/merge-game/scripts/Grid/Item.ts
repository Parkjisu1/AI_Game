import { App } from "../..";
import { Easing, Tween } from "@tweenjs/tween.js";
import { Sprite } from "../Core/RenderElements/Sprite";
import { GridEvents } from "./GridEvents";
import { Cell } from "../Cell";
import { Point } from "pixi.js";

export class Item extends Sprite {

    private isDragging: Boolean = false;
    private eventData: any;
    private startPosition: { x: number, y: number };
    protected _type: string;
    protected _cell: Cell;

    get type() { return this._type };
    get cell() { return this._cell };
    set cell(value: Cell) { this._cell = value };

    constructor(config) {
        super(config);
        this._type = config.type;
        this.unlock();

        this.init();
    }

    async returnToStartPosition(position: Point): Promise<any> {
        this.lock();
        await this.tweens.to(this.node.position, position, 300, { easing: Easing.Quadratic.Out });
        this.unlock();
        return Promise.resolve();
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
        this.startPosition = { x: this.node.x, y: this.node.y };
        this.setEvents();
    }

    private setEvents(): void {
        this.node.interactive = true;
        this.node
            .on('pointerdown', event => this.onDragStart(event))
            .on('pointermove', () => this.onDragMove())
            .on('pointerup', () => this.onDragEnd())
            .on('pointerupoutside', () => this.onDragEnd())
    }

    private onDragStart(event): void {
        if (this.isDragging) return;
        this.isDragging = true;
        this.eventData = event.data;
        App.emit(GridEvents.ITEM_POINTER_DOWN.toString(), this);
    }

    private onDragMove(): void {
        if (!this.isDragging) return;

        const position = this.eventData.getLocalPosition(this.node.parent);
        this.node.position.set(position.x, position.y);
    }

    private onDragEnd(): void {
        if (!this.isDragging) return;
        this.isDragging = false;

        App.emit(GridEvents.ITEM_POINTER_UP.toString(), this);
    }

    disappear(): Promise<void> {
        return this.tweens.to(this.node.scale, { x: 0, y: 0 }, 250, { easing: Easing.Back.In });
    }
}