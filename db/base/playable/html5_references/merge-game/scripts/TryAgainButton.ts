import { Easing } from "@tweenjs/tween.js";
import { App } from "..";
import { Container } from "./Core/RenderElements/Container";
import { GameEvents } from "./GameEvents";

const elementConfig = {
    children: {
        button: { texture: 'failPopup/button' },
        text: { texture: 'failPopup/textButton'}
    }
}

export class TryAgainButton extends Container {
    constructor(config){
        super({...elementConfig, ...config});
        this.init();
    }

    protected onResize(): void {
        let y = 0;
        if (App.isPortrait()) {
            if (App.screenType === 'S') {
                y = 850;
            } else if (App.screenType === 'M') {
                y = 700;
            } else if (App.screenType === 'L') {
                y = 670;
            }
        } else {
            if (App.screenType === 'S') {
                y = 600;
            } else if (App.screenType === 'M') {
                y = 600;
            } else if (App.screenType === 'L') {
                y = 620;
            }
        }

        this.node.y = y;
    }

    init() {
        this.setEvents();
    }

    pulse() {
        this.tweens.to(this.node.scale, { x: 1.05, y: 1.05 }, 600, { easing: Easing.Sinusoidal.InOut, yoyo: true, repeat: Infinity })
    }

    protected setEvents() {
        this.node.interactive = true;
        this.node.on('pointerdown', () => App.emit(GameEvents.START_NEW_GAME.toString()));
    }
}