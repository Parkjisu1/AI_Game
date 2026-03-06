import { Easing } from "@tweenjs/tween.js";
import { Container } from "./Core/RenderElements/Container";
import { App } from "..";
import { GameEvents } from "./GameEvents";

const elementConfig = {
    children: {
        finger: { texture: 'finger' },
    }
}

export class Finger extends Container {

    constructor(config) {
        super({ ...elementConfig, ...config });
    }

    async showFinger() {

        this.node.x = 250;
        this.node.y = 50;
        this.node.scale.set(1);
        this.showFingerAnimation();
    }

    protected async showFingerAnimation() {
        await this.tweens.to(this.node, { x: 120, y: this.node.y }, 500, { easing: Easing.Quadratic.InOut });
        await this.tweens.to(this.node.scale, { x: 0.6, y: 0.6 }, 300, { easing: Easing.Quadratic.InOut });
        await this.tweens.to(this.node.scale, { x: 1, y: 1 }, 300, { easing: Easing.Quadratic.InOut });
        await this.tweens.wait(500);
        await this.tweens.to(this.node, { x: 250, y: this.node.y }, 500, { easing: Easing.Quadratic.InOut });
        this.showFingerAnimation();
    }

    protected delay(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    protected setEvents() {
        App.on(GameEvents.START_GAME.toString(), this.hide, this);
    }

}