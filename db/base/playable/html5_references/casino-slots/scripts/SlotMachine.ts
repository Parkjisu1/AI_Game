import { Easing } from "@tweenjs/tween.js";
import { Container } from "./Core/RenderElements/Container";
import { App } from "..";
import { Slot } from "./Slot";
import { SlotFactory } from "./SlotFactory";
import { SlotConfig } from "./Const"
import { Point, filters } from "pixi.js";
import { AnimatedSprite } from "./Core/RenderElements/AnimatedSprite";

const elementConfig = {
    children: {
        slotsHolder: { class: Container, id: 'slotsHolder' },
    }
}

export class SlotMachine extends Container {

    private _slots: Slot[];
    protected slotsHolder: Container;

    get slots() { return this._slots };

    constructor(config) {
        super({ ...elementConfig, ...config });
        this.slotsHolder = this.child('slotsHolder');
        this.init();
    }

    protected onResize(): void {
        let scale = this.getScale();
        let y = this.getY();

        this.node.scale.set(scale);
        this.node.y = y;
    }

    protected getY(): number {
        let y = 0;
        if (App.isPortrait()) {
            if (App.screenType === 'S') {
                y = -100;
            } else if (App.screenType === 'M') {
                y = -120;
            } else if (App.screenType === 'L') {
                y = -140;
            }
        } else {
            if (App.screenType === 'S') {
                y = -100;
            } else if (App.screenType === 'M') {
                y = -130;
            } else if (App.screenType === 'L') {
                y = -150;
            }
        }

        return y;
    }

    getScale(): number {
        let scale = 1;

        if (App.isPortrait()) {
            if (App.screenType === 'S') {
                scale = 0.85;
            } else if (App.screenType === 'M') {
                scale = 0.95;
            } else if (App.screenType === 'L') {
                scale = 1.05;
            }
        } else {
            if (App.screenType === 'S') {
                scale = 1;
            } else if (App.screenType === 'M') {
                scale = 1.1;
            } else if (App.screenType === 'L') {
                scale = 1.2;
            }
        }

        return scale;
    }

    public init() {
        this.createSlots();
        this.showFirst();
        this.slotsHolder.node.x = -295;
    }

    async showSlotMachine() { 
        this.show(); 
        this.node.alpha = 0;
        this.tweens.to(this.node, { alpha: 1 }, 120);
    }

    showFirst() {

        let iterCount: number = 0;
        this.slots.forEach(slot => {
            if (iterCount === 0){
                slot.showItem('cherry');
            }
            if (iterCount === 1){
                slot.showItem('coin');
            }
            if (iterCount === 2){
                slot.showItem('figure');
            }
            iterCount++;
        });
    }

    animateFireRay(){
        this.fxFireRayAnimation(this.node.position);
    }

    protected async fxFireRayAnimation(position: Point) {
        const fx = new AnimatedSprite({ count: 21, textureName: 'fxFireRay', speed: 0.3, scale: { x: 7, y: 7 } });
        const colorFilter = new filters.ColorMatrixFilter();
        colorFilter.tint(0xccfffc);
        colorFilter.brightness(2.5, true);
        fx.node.filters = [colorFilter];
        fx.node.position = position;
        this.addChild(fx);

        await fx.play();
        fx.hide();
    }

    async hideFirst(slotsNum: number, slotConfig: string[][]) {

        for (let i = 0; i < slotsNum; i++){
            for (let j = 0; j < slotConfig[i].length; j++) {
                if (this.slots[i].items[j].type == 'cherry' && i == 0){
                    await this.slots[i].items[j].moveItem(0, 400, this.slots[i].items[j].type, 190);
                }
                if (this.slots[i].items[j].type == 'coin' && i == 1){
                    await this.slots[i].items[j].moveItem(0, 400, this.slots[i].items[j].type, 190);
                }
                if (this.slots[i].items[j].type == 'figure' && i == 2){
                    await this.slots[i].items[j].moveItem(0, 400, this.slots[i].items[j].type, 190);
                }
            }
            
        }
    }

    darkSlotMachine(): void {
        this._slots.forEach(slot => {
            if (slot.node) {
                this.tweens.to(slot.node, { alpha: 0.3 }, 2000, { easing: Easing.Quadratic.InOut });
            }
        });
    }

    hideSlotMachine(): void {
        this._slots.forEach(slot => {
            if (slot.node) {
                this.tweens.to(slot.node, { alpha: 0 }, 750, { easing: Easing.Quadratic.InOut });
            }
        });
    }

    async spinSlots(slotsNum: number, slotConfig: string[][], numOfSpins: number[]) {
            for (let i = 0; i < slotsNum; i++){
                this.slots[i].spinSlot(i, slotsNum, slotConfig, numOfSpins[i]);
            }
    }

    async moveSlotsDown() {
        await this.tweens.to(this.node, { y: this.node.y + 80 }, 700, { easing: Easing.Bounce.Out, delay: 300 });
        await this.tweens.to(this.node.scale, { x: this.getScale() + 0.1, y: this.getScale() + 0.1 }, 500);
    }

    createSlots() {
        this._slots = null;
        this._slots = SlotFactory.createSlot(3, SlotConfig);
        this._slots.forEach(slot => this.slotsHolder.addChild(slot));
    }

}