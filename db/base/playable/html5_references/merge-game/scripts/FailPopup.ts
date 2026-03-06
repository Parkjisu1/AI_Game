import { Easing } from "@tweenjs/tween.js";
import { App } from "..";
import { Container } from "./Core/RenderElements/Container";
import { TryAgainButton } from "./TryAgainButton";
import { Graphics } from "pixi.js";
import { Sprite } from "./Core/RenderElements/Sprite";

const elementConfig = {
    children: {
        bgPopup: { texture: 'failPopup/popupBg' },
        text: { texture: 'failPopup/text'},
        tryAgainButton: { class: TryAgainButton, id: 'tryAgainButton', visible: false }
    }
}

export class FailPopup extends Container {

    private button: TryAgainButton;
    protected text: Sprite;
    private mask: Graphics;

    constructor(config) {
        super({...elementConfig, ...config});
        this.text = this.child('text');
        this.button = this.child('tryAgainButton');
        this.mask = this.createMask();
        this.setMask();
    }

    protected onResize(): void {
        const resizeValues = this.getResizeValues();
        const scale = resizeValues.scale;
        const y = resizeValues.y;

        this.node.scale.set(scale);
        this.node.y = y;
    }

    async hideAnimation() {
        this.tweens.to(this.node, { alpha: 0 }, 350);
        await this.tweens.to(this.node.scale, { x: 0, y: 0 }, 400, { easing: Easing.Back.In });
        this.hide();
        this.button.hide();
        this.mask.angle = 0;
    }

    protected createMask(): Graphics {
        const mask = new Graphics();
        mask.beginFill(0xff0000);
        mask.drawCircle(0, 0, 600);
        mask.endFill();
        mask.pivot = { x: mask.width / 2, y: -mask.height / 2 };

        return mask;
    }

    protected setMask() {
        this.mask.x = 250;
        this.mask.y = 500;
        this.text.node.addChild(this.mask);
        this.text.node.mask = this.mask;
    }

    async showAnimatiom() {
        this.tweens.to(this.mask, { angle: 120 }, 700, { easing: Easing.Quadratic.Out });
        const scaleTo = this.getResizeValues().scale;
        this.node.scale.set(0.5);
        this.node.alpha = 0;
        this.tweens.to(this.node, { alpha: 1 }, 350, { easing: Easing.Quartic.Out });
        await this.tweens.to(this.node.scale, { x: scaleTo, y: scaleTo }, 250, { easing: Easing.Back.Out });
        await this.tweens.wait(250);
        this.button.node.alpha = 0;
        this.button.show();
        this.button.tweens.fadeIn();
        this.button.pulse();
    }

    protected getResizeValues() {
        let scale = 1;
        let y = 0;

        if (App.isPortrait()) {
            if (App.screenType === 'S') {
                scale = 0.77;
            } else if (App.screenType === 'M') {
                scale = 0.95;
            } else if (App.screenType === 'L') {
                scale = 1.1
            }
        } else {
            if (App.screenType === 'S') {
                y = -70;
                scale = 0.6;
            } else if (App.screenType === 'M') {
                y = -115;
                scale = 0.8;
            } else if (App.screenType === 'L') {
                y = -130;
                scale = 1;
            }
        }

        return { scale, y };
    }
}