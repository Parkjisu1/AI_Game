import { Easing } from "@tweenjs/tween.js";
import { Container } from "./Core/RenderElements/Container";
import { App } from "..";
import { GameEvents } from "./GameEvents";

const elementConfig = {
    children: {
        button: { texture: 'spinButton' },
    }
}

export class SpinButton extends Container {

    constructor(config) {
        super({ ...elementConfig, ...config });
    }

    pulse() {
        this.tweens.to(this.node.scale, { x: 1, y: 1 }, 500, { easing: Easing.Quadratic.InOut, yoyo: true, repeat: Infinity});
        this.setEvents();
    }

    pulseStop() {
        this.tweens.to(this.node.scale, { x: 1, y: 1 }, 500);
    }

    protected setEvents() {
        this.node.interactive = true;
        this.node.on('pointerdown', () => {
            App.emit(GameEvents.START_GAME.toString());
            this.node.interactive = false;
        });
    }

}