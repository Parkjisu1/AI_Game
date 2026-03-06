import { Easing } from "@tweenjs/tween.js";
import { Container } from "./Core/RenderElements/Container";
import { App } from "..";
import { Graphics } from "pixi.js";
import { Sprite } from "./Core/RenderElements/Sprite";


const elementConfig = {
    children: {
        popupBg: { texture: "winPopup/popupBg"},
        text: { texture: "winPopup/text"}
    }
}

export class WinPopup extends Container {

    protected text: Sprite;
    private mask: Graphics;

    constructor(config) {
        super({...elementConfig, ...config});
        this.text = this.child('text');
        this.mask = this.createMask();
        this.setMask();
    }

    async showAnimatiom() {
        this.tweens.to(this.mask, { angle: 120 }, 700, { easing: Easing.Quadratic.Out });
        const scaleTo = this.getScale();
        this.node.scale.set(1.5);
        this.node.alpha = 0;
        this.tweens.to(this.node, { alpha: 1 }, 350, { easing: Easing.Quartic.Out });
        this.tweens.to(this.node.scale, { x: scaleTo, y: scaleTo }, 250, { easing: Easing.Back.Out });
    }

    protected createMask(): Graphics {
        const mask = new Graphics();
        mask.beginFill(0xff0000);
        mask.drawCircle(0, 0, 600);
        mask.endFill();
        mask.pivot = { x: mask.width / 2, y: -mask.height / 2 };

        return mask;
    }

    protected setMask(): void {
        this.mask.x = 250;
        this.mask.y = 500;
        this.text.node.addChild(this.mask);
        this.text.node.mask = this.mask;
    }

    protected onResize(): void {
        const scale = this.getScale();

        this.node.scale.set(scale);
    }

    protected getScale(): number {
        let scale = 1;

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
                scale = 0.6;
            } else if (App.screenType === 'M') {
                scale = 0.8;
            } else if (App.screenType === 'L') {
                scale = 1;
            }
        }

        return scale;
    }
}