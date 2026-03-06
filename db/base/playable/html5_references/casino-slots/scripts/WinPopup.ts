import { Container } from "./Core/RenderElements/Container";
import { Easing } from "@tweenjs/tween.js";
import { App } from "..";
import { Text } from "./Core/RenderElements/Text";


const elementConfig = {
    children: {
        jackpotPopup: { texture: 'jackpotPopup', id: 'jackpotPopup', scale: 0, alpha: 1, visible: false },
        numberHolder: {
            class: Container,
            children: {
                text: {
                    class: Text,
                    value: 0,
                    y: 250,
                    style: {
                        fontFamily: 'Counter',
                        fill: 0xffd700,
                        fontSize: 80
                    }
                }
            }
        }
    }
}

export class WinPopup extends Container {

    protected jackpotPopup: Container;
    protected numberHolder: Container;
    protected text: Text;

    constructor(config) {
        super({ ...elementConfig, ...config });
        this.jackpotPopup = this.child('jackpotPopup');
        this.numberHolder = this.child('numberHolder');
        this.text = this.numberHolder.child('text');
    }

    async animateJackpot() {
        await this.jackpotPopup.tweens.to(this.jackpotPopup.node.scale, { x: this.getScale() + 0.05, y: this.getScale() + 0.05 }, 1000, { easing: Easing.Quadratic.InOut });
        await this.jackpotPopup.tweens.to(this.jackpotPopup.node.scale, { x: this.getScale(), y: this.getScale() }, 1000, { easing: Easing.Quadratic.InOut });
        this.animateJackpot();
    }

    showJackpot(){
        this.jackpotPopup.show();
        this.tweens.to(this.jackpotPopup.node.scale, { x: this.getScale(), y: this.getScale() }, 1200, { easing: Easing.Bounce.Out } );
        this.animateJackpot();
    }

    protected onResize(): void {
        let scale = this.getScale();
        let y = this.getY();

        this.node.y = y;
        this.node.scale.set(scale);
    }

    async showNumberAnimation(numScaleX: number, numScaleY: number) {
        await this.text.tweens.to(this.text.node.scale, { x: numScaleX + 0.05, y: numScaleY + 0.05 }, 1000, { easing: Easing.Quadratic.InOut });
        await this.text.tweens.to(this.text.node.scale, { x: numScaleX, y: numScaleY }, 1000, { easing: Easing.Quadratic.InOut });
        this.showNumberAnimation(numScaleX, numScaleY);
    }

    async showNumber() {

        const numScaleX = this.text.node.scale.x;
        const numScaleY = this.text.node.scale.y;
        this.text.tweens.to(this.text.node.scale, { x: 1.2, y: 1.2 }, 1000, { easing: Easing.Quadratic.InOut });
        this.showNumberAnimation(numScaleX, numScaleY);

    }
    
    async animateNumber(targetValue: number) {
        const stepTime = 10; // Время между увеличениями числа
        const step = Math.max(Math.floor(targetValue / 200), 1); // Шаг увеличения
        const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms)); // Функция задержки
    
        // Начальное значение
        let currentValue = parseInt(this.text.node.text.replace(/[^0-9]/g, ''), 10) || 0;
    
        while (currentValue < targetValue) {
            currentValue = Math.min(currentValue + step, targetValue); // Увеличиваем число
            this.text.node.text = `$${currentValue.toLocaleString()}`; // Обновляем текст с форматом и значком доллара
            await delay(stepTime); // Ждем перед следующим шагом
        }

    }

    protected getY(): number {
        let y = 0;
        if (App.isPortrait()) {
            if (App.screenType === 'S') {
                y = -65;
            } else if (App.screenType === 'M') {
                y = -60;
            } else if (App.screenType === 'L') {
                y = -55;
            }
        } else {
            if (App.screenType === 'S') {
                y = -30;
            } else if (App.screenType === 'M') {
                y = -15;
            } else if (App.screenType === 'L') {
                y = -10;
            }
        }

        return y;
    }

    getScale(): number {
        let scale = 1;

        if (App.isPortrait()) {
            if (App.screenType === 'S') {
                scale = 0.75;
            } else if (App.screenType === 'M') {
                scale = 0.8;
            } else if (App.screenType === 'L') {
                scale = 0.9;
            }
        } else {
            if (App.screenType === 'S') {
                scale = 0.9;
            } else if (App.screenType === 'M') {
                scale = 1;
            } else if (App.screenType === 'L') {
                scale = 1.1;
            }
        }

        return scale;
    }
}