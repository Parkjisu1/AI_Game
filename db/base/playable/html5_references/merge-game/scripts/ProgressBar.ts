import { App } from "..";
import { Container } from "./Core/RenderElements/Container";
import { RenderElement } from "./Core/RenderElements/RenderElement";
import { Sprite } from "./Core/RenderElements/Sprite";
import { Utils } from "./Core/Utils";
import { GameEvents } from "./GameEvents";
import * as TWEEN from '@tweenjs/tween.js';

const elementConfig = {
    children: {
        bg: { texture: 'progressBar' },
        main: {
            texture: 'progressBar',
            children: {
                mask: { texture: 'progressBar' }
            }
        },
    }
}

export class ProgressBar extends Container {

    protected main: Sprite;
    protected mask: Sprite;
    protected bg: Sprite;
    protected progressTween: TWEEN.Tween<RenderElement>;

    constructor(config) {
        super({ ...config, ...elementConfig });
        this.main = this.child('main');
        this.mask = this.main.child('mask');
        this.bg = this.child('bg');

        this.main.node.tint = 0x80be1f;
        this.main.node.mask = this.mask.node;
    }

    async start() {
        this.progressTween = this.mask.tweens.create(this.mask.node, { x: -this.mask.node.width }, 15000, {
            onUpdate: (sprite, k) => {
                if (k > 0.4) {
                    const color = Utils.lerpColor(0x80be1f, 0xbe1f1f, (k - 0.4) * 3);
                    this.main.node.tint = color;
                }
            }
        });

        await this.tweens.start(this.progressTween);
        App.emit(GameEvents.FAILED_GAME.toString());
    }

    reset() {
        this.mask.node.x = 0;
        this.main.node.tint = 0x80be1f;
    }

    stop() {
        this.tweens.stop(this.progressTween);
    }

    protected onResize(): void {
        let scale = 1;
        let x = 0;
        let y = 0;
        let angle = 0;
        if (App.isPortrait()) {
            if (App.screenType === 'S') {
                scale = 0.84;
                y = 450;
            } else if (App.screenType === 'M') {
                scale = 0.98;
                y = 525;
            } else if (App.screenType === 'L') {
                scale = 1.14
                y = 600;
            }
            angle = 0;
        } else {
            if (App.screenType === 'S') {
                x = 460;
                y = 5;
                scale = 0.78;
            } else if (App.screenType === 'M') {
                x = 500;
                y = 5;
                scale = 0.88;
            } else if (App.screenType === 'L') {
                x = 650;
                y = 5;
                scale = 1.12;
            }
            angle = -90;
        }

        this.node.scale.set(scale);
        this.node.angle = angle;
        this.node.x = x;
        this.node.y = y;
    }
}