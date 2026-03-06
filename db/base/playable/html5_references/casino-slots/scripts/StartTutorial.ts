import { Container } from "./Core/RenderElements/Container";
import { Easing } from "@tweenjs/tween.js";
import { SpinButton } from "./SpinButton";
import { Finger } from "./Finger";
import { App } from "..";

const elementConfig = {
    children: {
        itemsHolder: { class: Container, id: 'itemsHolder', alpha: 0 },
        finger: { class: Finger, id: 'finger', alpha: 0 },
        spinButton: { class: SpinButton, id: 'spinButton', alpha: 0 },
    }
}

export class StartTutorial extends Container {

    protected itemsHolder: Container;
    protected spinButton: SpinButton;
    protected finger: Finger;


    constructor(config) {
        super({ ...elementConfig, ...config });
        this.itemsHolder = this.child('itemsHolder');
        this.spinButton = this.child('spinButton');
        this.finger = this.child('finger');
        this.onResize();
    }

    async animate() {

        this.itemsHolder.addChild(this.spinButton);
        this.itemsHolder.addChild(this.finger);
        this.show();
        this.node.alpha = 1;
        this.itemsHolder.node.alpha = 1;
        this.tweens.to(this.spinButton.node, { alpha: 1 }, 500);
        this.tweens.to(this.finger.node, { alpha: 1 }, 500);
        this.finger.showFinger();
        this.spinButton.pulse();

    }

    async showAnimation() {
        
    }

    async hideAnimation() {
        this.tweens.to(this.node, { alpha: 0 }, 350);
        await this.tweens.to(this.node.scale, { x: 0, y: 0 }, 400, { easing: Easing.Quadratic.InOut });
        this.hide();
    }

    protected onResize(): void {
        let scale = this.getScale();
        let y = this.getY();
        this.node.scale.set(scale);
        this.node.y = y;
    }

    protected getY(): number {
        let y = 0;
        if (App.isPortrait()) {
            if (App.screenType === 'S') {
                y = 450;
            } else if (App.screenType === 'M') {
                y = 500;
            } else if (App.screenType === 'L') {
                y = 550;
            }
        } else {
            if (App.screenType === 'S') {
                y = 250;
            } else if (App.screenType === 'M') {
                y = 270;
            } else if (App.screenType === 'L') {
                y = 290;
            }
        }

        return y;
    }

    getScale(): number {
        let scale = 1;

        if (App.isPortrait()) {
            if (App.screenType === 'S') {
                scale = 1.4;
            } else if (App.screenType === 'M') {
                scale = 1.5;
            } else if (App.screenType === 'L') {
                scale = 1.6;
            }
        } else {
            if (App.screenType === 'S') {
                scale = 1.1;
            } else if (App.screenType === 'M') {
                scale = 1.2;
            } else if (App.screenType === 'L') {
                scale = 1.3;
            }
        }

        return scale;
    }
}