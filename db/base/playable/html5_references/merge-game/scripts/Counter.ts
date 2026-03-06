import { Easing } from "@tweenjs/tween.js";
import { App } from "..";
import { Container } from "./Core/RenderElements/Container";
import { Text } from "./Core/RenderElements/Text";

const elementConfig = {
    children: {
        main: { texture: 'counter' },
        numberHolder: {
            class: Container,
            children: {
                text: {
                    class: Text,
                    value: 0,
                    x: 165,
                    y: -1,
                    style: {
                        fontFamily: 'Counter',
                        fill: 0x1ea7e1,
                        fontSize: 40
                    }
                }
            }
        }
    }
}

export class Counter extends Container {

    protected _value: number = 0;
    protected numberHolder: Container;
    protected text: Text;

    set value(v: number) { 
        this._value = v;
        this.text.node.text = this._value;
     } 

    constructor(config) {
        super({ ...config, ...elementConfig })
        this.numberHolder = this.child('numberHolder');
        this.text = this.numberHolder.child('text');
    }

    protected onResize(): void {
        let scale = 1;
        let x = 0;
        let y = 0;
        let startX = -App.size.width / 2;
        let startY = -App.size.height / 2;
        if (App.isPortrait()) {
            if (App.screenType === 'S') {
                scale = 1.05;
                x = -160;
                y = -455;
            } else if (App.screenType === 'M') {
                scale = 1.1;
                x = -210;
                y = -525;
            } else if (App.screenType === 'L') {
                scale = 1.4;
                x = -220;
                y = -610;
            }
        } else {
            if (App.screenType === 'S') {
                scale = 1.1;
                x = startX + 250;
                y = startY + 100;
            } else if (App.screenType === 'M') {
                scale = 1.1;
                x = startX + 250;
                y = startY + 100;
            } else if (App.screenType === 'L') {
                scale = 1.1;
                x = startX + 250;
                y = startY + 100;
            }
        }

        this.node.scale.set(scale);
        this.node.x = x;
        this.node.y = y;
    }

    addValue() {
        this.value = this._value + 1;
        this.textBounce();
    }

    textBounce() {
        this.text.tweens.to(this.text.node.scale, { x: 1.3, y: 1.3 }, 300, { yoyo: true, repeat: 1, easing: Easing.Quadratic.Out });
    }
}