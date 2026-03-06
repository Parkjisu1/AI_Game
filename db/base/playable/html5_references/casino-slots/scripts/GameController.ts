import { App } from "..";
import { GameEvents } from "./GameEvents";
import { StartTutorial } from "./StartTutorial";
import { SlotMachine } from "./SlotMachine";
import { Background } from "./Background";
import { SlotConfig } from "./Const";
import { NumOfSpins } from "./Const";
import { MaskHolder } from "./MaskHolder";
import { WinPopup } from "./WinPopup";

export class GameController {

    private bg: Background;
    private startTutorial: StartTutorial;
    private slotMachine: SlotMachine;
    private maskHolder: MaskHolder;
    private winPopup: WinPopup;

    constructor() {

        this.slotMachine = App.getElementByID('slotMachine');
        this.startTutorial = App.getElementByID('startTutorial');
        this.bg = App.getElementByID('bg');
        this.winPopup = App.getElementByID('winPopup');
        const color: number = 0x000000;
        const x: number = 0;
        const y: number = 0;
        const width: number = this.slotMachine.node.width / this.slotMachine.node.scale.x;
        const height: number = this.slotMachine.node.height / this.slotMachine.node.scale.y;

        this.maskHolder = new MaskHolder({color: color, x: x, y: y, width: width, height: height });
        this.setMask();
        this.setEvents(); 
        this.start();  
    }

    protected setEvents() {
        App.once(GameEvents.START_GAME.toString(), this.startGameplay, this);
        App.on(GameEvents.END_GAME.toString(), this.endGame, this);
    }

    protected setMask() {
        this.slotMachine.node.addChild(this.maskHolder.mask);
        this.slotMachine.node.mask = this.maskHolder.mask;
        this.slotMachine.node.mask.x = (-this.slotMachine.node.width / 2) / this.slotMachine.node.scale.x;
        this.slotMachine.node.mask.y = (-this.slotMachine.node.height / 2) / this.slotMachine.node.scale.y;
        
    }

    private async start() {
        this.slotMachine.slots.forEach(slot => slot.node.scale.set(0));
        await this.slotMachine.tweens.wait(250);
        this.slotMachine.slots.forEach(slot => slot.animateSlot());
        this.startTutorial.animate();
        this.slotMachine.showSlotMachine();
    }

    private darkScene(){
        this.bg.darkBg();
        this.slotMachine.hideSlotMachine();
    }

    private async startGameplay() {
        await this.startTutorial.hideAnimation();
        await this.slotMachine.moveSlotsDown();
        await this.bg.lightBg();
        await this.slotMachine.hideFirst(3, SlotConfig);
        await this.slotMachine.spinSlots(3, SlotConfig, NumOfSpins);
        
    }

    private async endGame() {

        await this.slotMachine.animateFireRay();
        await this.winPopup.tweens.wait(800);
        this.darkScene();
        await this.winPopup.show();
        await this.winPopup.showJackpot();
        await this.winPopup.showNumber();
        this.winPopup.animateNumber(1000000);

    }
}