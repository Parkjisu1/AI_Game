import { Graphics } from "pixi.js";
import { Container } from "./Core/RenderElements/Container";
import { Sprite } from "./Core/RenderElements/Sprite";
import { Easing } from "@tweenjs/tween.js";
import { StartPopupButton } from "./StartPopupButton";
import { App } from "..";

const elementConfig = {
    children: {
        popupBg: { texture: 'startPopup/popupBg' },
        text: {
            texture: 'startPopup/text',
            y: -20,
            children: {
                maskHolder: { class: Container }
            }
        },
        button: { class: StartPopupButton, y: 140, alpha: 0 }
    }
}

export class StartPopup extends Container {

    protected text: Sprite;
    protected maskHolder: Container;
    protected rectTop: Graphics;
    protected rectBottom: Graphics;
    protected button: StartPopupButton;

    constructor(config) {
        super({ ...elementConfig, ...config });
        this.text = this.child('text');
        this.maskHolder = this.text.child('maskHolder');
        this.button = this.child('button');
        this.createMaskRects();
        this.onResize();
    }

    protected createMaskRects() {
        this.rectTop = this.createRect(-1460, -60, 1000, 60);
        this.rectBottom = this.createRect(-1200, 0, 800, 60);

        this.rectTop.position.set()
        this.maskHolder.node.addChild(this.rectTop);
        this.maskHolder.node.addChild(this.rectBottom);
        this.text.node.mask = this.maskHolder.node;
    }

    protected createRect(x: number, y: number, width: number, height: number): Graphics {
        const rect = new Graphics();
        rect.beginFill(0xff0000);
        rect.drawRect(x, y, width, height);
        rect.endFill();
        return rect;
    }

    async animate() {
        const scaleTo = this.getScale();
        this.node.scale.set(1.5);
        this.node.alpha = 0;
        this.tweens.to(this.node, { alpha: 1 }, 250, { easing: Easing.Quartic.Out });
        await this.tweens.to(this.node.scale, { x: scaleTo, y: scaleTo }, 400, { easing: Easing.Back.Out });
        await this.tweens.to(this.rectTop, { x: 1000 }, 750);
        await this.tweens.to(this.rectBottom, { x: 800 }, 750);
        await this.tweens.wait(400);
        await this.button.showButton();
        await this.tweens.wait(500);
        this.button.pulse();
        await this.tweens.wait(500);
    }

    async hideAnimation() {
        this.tweens.to(this.node, { alpha: 0 }, 350);
        await this.tweens.to(this.node.scale, { x: 0, y: 0 }, 400, { easing: Easing.Back.In });
        this.hide();
    }

    protected onResize(): void {
        let scale = this.getScale();

        this.node.scale.set(scale);
    }

    getScale(): number {
        let scale = 1;

        if (App.isPortrait()) {
            if (App.screenType === 'S') {
                scale = 0.8;
            } else if (App.screenType === 'M') {
                scale = 1;
            } else if (App.screenType === 'L') {
                scale = 1.2;
            }
        } else {
            if (App.screenType === 'S') {
                scale = 1.1;
            } else if (App.screenType === 'M') {
                scale = 1.1;
            } else if (App.screenType === 'L') {
                scale = 1.2;
            }
        }

        return scale;
    }
}