import { App } from "../..";
import { Item } from "./Item";
import { DragHolder } from "./DragHolder";
import { Grid } from "./Grid";
import { GridEvents } from "./GridEvents";
import { GameEvents } from "../GameEvents";
import { Cell } from "../Cell";
import { Point, filters } from "pixi.js";
import { AnimatedSprite } from "../Core/RenderElements/AnimatedSprite";

export class GridController {

    protected grid: Grid;
    protected dragHolder: DragHolder;

    constructor(grid: Grid) {
        this.grid = grid;
        this.dragHolder = App.getElementByID('dragHolder');

        this.setEvents();
    }

    protected setEvents() {
        App.on(GridEvents.ITEM_POINTER_DOWN.toString(), item => this.onItemDown(item));
        App.on(GridEvents.ITEM_POINTER_UP.toString(), item => this.onItemUp(item));
    }

    protected onItemDown(item: Item) {
        item.changeParent(this.dragHolder);
    }

    protected onItemUp(dragItem: Item) {
        const cells = this.grid.cells;
        for (let i = 0; i < cells.length; i++) {
            const cell = cells[i];
            const item = cell.item;
            if (!item) continue;

            if (item !== dragItem && item.checkCollision(dragItem) && item.type === dragItem.type ) {
                this.merge(cell, dragItem);
                return;
            }
        }

        this.returnItemToCell(dragItem);
    }

    protected async merge(cell: Cell, dragItem: Item) {
        App.emit(GridEvents.MERGE);

        const fxPosition = cell.node.position;
        dragItem.cell.removeItem();
        this.dragHolder.removeChild(dragItem);
        this.fxAnimation(fxPosition);
        await cell.item.disappear();
        cell.removeItem();

        if (this.isCellsEmpty())
            App.emit(GameEvents.END_GAME.toString());
    }

    protected async fxAnimation(position: Point) {
        const fx = new AnimatedSprite({ count: 14, textureName: 'fx', speed: 0.8, scale: { x: 1.4, y: 1.4 } });
        const colorFilter = new filters.ColorMatrixFilter();
        colorFilter.tint(0xccfffc);
        colorFilter.brightness(2.5, true);
        fx.node.filters = [colorFilter];
        fx.node.position = position;
        this.grid.addChild(fx);

        await fx.play();
        fx.hide();
    }

    protected isCellsEmpty(): Boolean {
        return this.grid.cells.every(cell => cell.item == null);
    }

    protected async returnItemToCell(dragItem: Item) {
        const localPos = this.dragHolder.getLocalPositionFor(dragItem.cell);
        await dragItem.returnToStartPosition(localPos);
        dragItem.changeParent(dragItem.cell);
        dragItem.node.position.set(0, 0);
    }

    
}