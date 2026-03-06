import { App } from "../..";
import { Cell } from "../Cell";
import { GridConfig } from "../Const";
import { Container } from "../Core/RenderElements/Container";
import { DragHolder } from "./DragHolder";
import { GridFactory } from "./GridFactory";

const elementConfig = {
    children: {
        cellsHolder: { class: Container },
        dragHolder: { class: DragHolder, id: 'dragHolder' }
    }
}

export class Grid extends Container {

    private _cells: Cell[];
    protected cellsHolder: Container;
    protected dragHolder: DragHolder;

    get cells() { return this._cells };

    constructor(config) {
        super({ ...elementConfig, ...config });
        this.cellsHolder = this.child('cellsHolder');
        this.dragHolder = this.child('dragHolder');
        this.init();
    }

    onResize(): void {
        let scale = 1;
        if (App.isPortrait()) {
            if (App.screenType === 'S') {
                scale = 0.85;
            } else if (App.screenType === 'M') {
                scale = 1
            } else if (App.screenType === 'L') {
                scale = 1.15;
            }
        } else {
            if (App.screenType === 'S') {
                scale = 0.8;
            } else if (App.screenType === 'M') {
                scale = 0.9
            } else if (App.screenType === 'L') {
                scale = 1.15;
            }
        }

        this.node.scale.set(scale);
    }

    public init() {
        this.createGrid();
        this.centrize();
    }

    protected centrize() {
        const pivotX = this.node.width / 2 - 20;
        const pivotY = this.node.height / 2 - 20;

        this.node.pivot = { x: pivotX, y: pivotY };
    }

    createGrid() {
        this._cells = null;
        this.dragHolder.removeChildren();
        this._cells = GridFactory.createGrid(GridConfig);
        this._cells.forEach(cell => this.cellsHolder.addChild(cell));
    }

    lock() {
        this.cells.forEach(cell => {
            if (cell.item) {
                cell.item.node.interactive = false;
            }
        })
    }

    unlock() {
        this.cells.forEach(cell => {
            if (cell.item) {
                cell.item.node.interactive = true;
            }
        })
    }
}