import { Graphics } from "pixi.js";
import { Container } from "./Core/RenderElements/Container";

export class Blackout extends Container {
    constructor(config) {
        super(config);
        this.drawRect();
        this.node.alpha = 0;
    }

    protected drawRect() {
        const rect = new Graphics();
        rect.beginFill(0x000000, 0.75);
        rect.drawRect(0, 0, 1920, 1920);
        rect.endFill();
        rect.pivot = { x: 1920 / 2, y: 1920 / 2 };
        this.node.addChild(rect);
    }

    showAnimation() {
        this.tweens.to(this.node, { alpha: 1 }, 200);
    }

    hideAnimation() {
        this.tweens.to(this.node, { alpha: 0 }, 200);
    }
}