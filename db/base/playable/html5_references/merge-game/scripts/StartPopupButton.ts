import { Easing } from "@tweenjs/tween.js";
import { Container } from "./Core/RenderElements/Container";
import { App } from "..";
import { GameEvents } from "./GameEvents";

const elementConfig = {
    children: {
        button: { texture: 'startPopup/button' },
        textButton: { texture: 'startPopup/textButton' }
    }
}

export class StartPopupButton extends Container {

    constructor(config) {
        super({ ...elementConfig, ...config });
    }

    async showButton() {  
        this.node.y = 100;
        this.node.alpha = 0;
        this.tweens.to(this.node, { alpha: 1 }, 120);
        this.tweens.to(this.node, { y: 140 }, 200);

        this.setEvents();
    }

    pulse() {
        this.tweens.to(this.node.scale, { x: 1.05, y: 1.05 }, 500, { easing: Easing.Sinusoidal.InOut, yoyo: true, repeat: Infinity })
    }

    protected setEvents() {
        this.node.interactive = true;
        this.node.on('pointerdown', () => App.emit(GameEvents.START_GAME.toString()));
    }
}