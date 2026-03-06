import { RenderElement } from "./RenderElements/RenderElement";
import * as TWEEN from '@tweenjs/tween.js';

export class Tweens {

    protected element: RenderElement;

    constructor(element: RenderElement) {
        this.element = element;
    }

    create(object: any, to: any, time: number, options?: any) {
        const tween = new TWEEN.Tween(object);
        tween.to(to, time);

        if (!options) return tween;

        if (options.repeat !== undefined) {
            tween.repeat(options.repeat);
        }

        if (options.easing !== undefined) {
            tween.easing(options.easing);
        }

        if (options.yoyo !== undefined) {
            tween.yoyo(options.yoyo);
        }

        if (options.delay !== undefined) {
            tween.delay(options.delay);
        }

        if (options.onUpdate !== undefined) {
            tween.onUpdate(options.onUpdate);
        }

        return tween;
    }

    to(object: any, to: any, time: number, options?: any): Promise<void> {
        return new Promise(resolve => {
            const tween = this.create(object, to, time, options);
            tween.onComplete(() => resolve());
            tween.start();
        });
    }

    wait(time): Promise<void> {
        return this.to({}, {}, time);
    }

    start(tween: TWEEN.Tween<RenderElement>): Promise<void> {
        return new Promise(resolve => {
            tween.onComplete(() => resolve());
            tween.start();
        });
    }

    stop(tween: TWEEN.Tween<RenderElement>) {
        tween.stop();
    }

    fadeIn(time: number = 250) {
        this.to(this.element.node, { alpha: 1 }, time);
    }

    fadeOut(time: number = 250) {
        this.to(this.element.node, { alpha: 0 }, time);
    }
}