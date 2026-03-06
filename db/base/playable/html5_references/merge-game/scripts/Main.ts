import { Container } from "./Core/RenderElements/Container";
import { Grid } from "./Grid/Grid";
import { GridController } from "./Grid/GridController";
import { StartPopup } from "./StartPopup";
import { Blackout } from "./Blackout";
import { ProgressBar } from "./ProgressBar";
import { Counter } from "./Counter";
import { WinPopup } from "./WinPopup";
import { FailPopup } from "./FailPopup";

const elementConfig = {
    children: {
        progressBar: { class: ProgressBar, id: 'progressBar', y: 450 },
        counter: { class: Counter, id: 'counter' },
        grid: { class: Grid, id: 'grid', scale: { x: 0.8, y: 0.8 } },
        blackout: { class: Blackout, id: 'blackout' },
        startPopup: { class: StartPopup, id: 'startPopup', visible: false },
        winPopup: { class: WinPopup, id: 'winPopup', visible: false },
        failPopup: { class: FailPopup, id: 'failPopup', visible: false }
    }
}

export class Main extends Container {

    protected grid: Grid;
    protected gridController: GridController;

    constructor(config) {
        super({ ...elementConfig, ...config });
        this.grid = this.child('grid');
        this.gridController = new GridController(this.grid);
    }
    
    protected onResize(): void {
        this.toCenter();
    }
}