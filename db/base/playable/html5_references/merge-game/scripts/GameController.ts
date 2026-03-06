import { App } from "..";
import { Blackout } from "./Blackout";
import { Counter } from "./Counter";
import { FailPopup } from "./FailPopup";
import { GameEvents } from "./GameEvents";
import { DragHolder } from "./Grid/DragHolder";
import { Grid } from "./Grid/Grid";
import { GridEvents } from "./Grid/GridEvents";
import { ProgressBar } from "./ProgressBar";
import { StartPopup } from "./StartPopup";
import { WinPopup } from "./WinPopup";

export class GameController {

    private blackout: Blackout;
    private startPopup: StartPopup;
    private grid: Grid;
    private progressBar: ProgressBar;
    private failPopup: FailPopup;
    private winPopup: WinPopup;
    private counter: Counter;
    private dragHolder: DragHolder;

    constructor() {
        this.blackout = App.getElementByID('blackout');
        this.startPopup = App.getElementByID('startPopup');
        this.grid = App.getElementByID('grid');
        this.progressBar = App.getElementByID('progressBar');
        this.failPopup = App.getElementByID('failPopup');
        this.winPopup = App.getElementByID('winPopup');
        this.counter = App.getElementByID('counter');
        this.dragHolder = App.getElementByID('dragHolder');

        this.setEvents(); 
        this.start();  
    }

    protected setEvents() {
        App.once(GameEvents.START_GAME.toString(), this.startGameplay, this);
        App.on(GameEvents.START_NEW_GAME.toString(), this.startNewGame, this);
        App.on(GameEvents.FAILED_GAME.toString(), this.showFailedPackshot, this);
        App.on(GameEvents.END_GAME.toString(), this.endGame, this);
        App.on(GridEvents.MERGE, this.onMerge, this);
    }

    protected onMerge() {
        this.counter.addValue();
    }

    private async start() {
        this.progressBar.node.alpha = 0;
        this.counter.node.alpha = 0;
        this.grid.lock();
        this.grid.cells.forEach(cell => cell.node.scale.set(0));
        await this.grid.tweens.wait(250);
        this.grid.cells.forEach(cell => cell.animateCell());
        await this.grid.tweens.wait(450);
        this.blackout.showAnimation();
        this.startPopup.show();
        this.startPopup.animate();
    }

    private async startGameplay() {
        this.blackout.hideAnimation();
        this.startPopup.hideAnimation();
        this.failPopup.hideAnimation();
        this.grid.unlock();  
        this.counter.tweens.fadeIn(200);
        this.progressBar.tweens.fadeIn(200);  
        await this.grid.tweens.wait(500);    
        this.progressBar.start();
    }

    private showFailedPackshot() {
        this.blackout.showAnimation();
        this.failPopup.show();
        this.failPopup.showAnimatiom();
        this.grid.lock();
        this.dragHolder.removeChildren();
    }

    private startNewGame() {
        this.grid.createGrid();
        this.progressBar.reset();
        this.startGameplay();
        this.counter.value = 0;
    }

    private endGame() {
        this.progressBar.stop();
        this.blackout.showAnimation();
        this.winPopup.show();
        this.winPopup.showAnimatiom();

        this.grid.lock();
    }
}