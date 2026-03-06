import { Easing } from "@tweenjs/tween.js";
import { Container } from "./Core/RenderElements/Container";
import { App } from "..";
import { GameEvents } from "./GameEvents";
import { Item } from "./Item";
import { Graphics } from "pixi.js";
import { MaskHolder } from "./MaskHolder";

const elementConfig = {
    children: {
        slot: { texture: 'slot', id: 'slot', scale: 2 },
        itemHolder: { class: Container, id: 'itemHolder' }
    }
}

export class Slot extends Container {

    protected _items: Item[] = [];
    protected _id: number = null;
    protected itemHolder: Container;
    private maskHolder: MaskHolder;

    get id() {return this._id};
    set id(id: number) {this._id = id};
    get items() { return this._items };

    constructor(config) {
        super({ ...elementConfig, ...config });
        this.itemHolder = this.child('itemHolder');
        this.createRects();

    }

    async animateRects(rect: Graphics) {

        rect.alpha = 0;
        await this.tweens.to(rect, { alpha: 0 }, 1500, { easing: Easing.Quadratic.InOut });
        this.tweens.to(rect, { alpha: 1 }, 1500, { easing: Easing.Quadratic.InOut});
        this.animateRects(rect);
    }

    createRects() {
        const width = this.node.width;
        const height = this.node.height;
        const rect = this.createRect(-width/2, -height/2, width, height, 0xffd700);
        const rect1 = this.createRect(-width/2, -height/2, width, height, 0x000000);
        this.node.addChild(rect);
        this.node.addChild(rect1);
        this.animateRects(rect1);
    }

    createRect(x: number, y: number, width: number, height: number, color: number): Graphics {
        const rect = new Graphics();
        rect.lineStyle(20, color);
        rect.drawRect(x, y, width, height);
        rect.endFill();
        return rect;
    }

    addItem(item: Item) {
        this.itemHolder.addChild(item);
        this._items.push(item);
        item.slot = this;
    }

    hideItem(type: string){
        this.items.forEach(item => {
            if (item.type == type) {
                item.node.y = -400;
                item.node.visible = false;
            }
        });
    }

    showItem(type: string){
        this.items.forEach(item => {
            if (item.type == type) {
                item.node.y = 0;
                item.node.visible = true;
            }
        });
    }

    async spinSlot(numOfCurrSlot: number, slotsNum: number, slotConfig: string[][], numOfSpins: number) {

        for (let i = 0; i < numOfSpins; i++) {
            for (let j = 0; j < slotConfig[numOfCurrSlot].length; j++) {
                await this.items[j].moveItem(0, 400, this.items[j].type, 190);
                this.items[j].node.y = -400;
            }
        }
    
        if (slotConfig[numOfCurrSlot] && slotConfig[numOfCurrSlot].length > 0) { // Проверка для второго цикла
            for (let i = 0; i < slotConfig[numOfCurrSlot].length; i++) {
                if (this.items[i].type === 'figure') {
                    if (numOfCurrSlot === slotsNum - 1) {
                        await this.items[i].moveItem(0, 0, this.items[i].type, 150);
                        App.emit(GameEvents.END_GAME.toString());
                    }
                    this.items[i].moveItem(0, 0, this.items[i].type, 190);
                }
            }
        }
    }
    

    animateSlot() {
        this.node.scale.set(0, 0)
        this.tweens.to(this.node.scale, { x: 1, y: 1 }, 400, { easing: Easing.Quadratic.InOut });
    }
}