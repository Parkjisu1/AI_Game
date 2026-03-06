import { Easing } from "@tweenjs/tween.js";
import { Sprite } from "./Core/RenderElements/Sprite";
import { Item } from "./Grid/Item";

const elementConfig = {
    texture: "cell"
}

export class Cell extends Sprite {

    protected _item: Item = null;
    
    get item() { return this._item };

    constructor(config) {
        super({ ...elementConfig, ...config });
    }

    addItem(item: Item) {
        this.addChild(item);
        this._item = item;
        item.cell = this;
    }

    removeItem() {
        if (!this.item) return;

        this.removeChild(this.item);
        this.item.cell = null;
        this._item = null;
    }

    animateCell() {
        this.node.scale.set(0, 0)
        this.tweens.to(this.node.scale, { x: 1, y: 1 }, 400, { easing: Easing.Back.Out });
    }
}