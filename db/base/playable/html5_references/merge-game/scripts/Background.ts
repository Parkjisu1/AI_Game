import { App } from "..";
import { Sprite } from "./Core/RenderElements/Sprite";

export class Background extends Sprite {

    constructor(config) {
        super(config);
    }

    protected onResize() {
        const x = App.size.width / 2;
        const y = App.size.height / 2;
        this.node.position.set(x, y);
    }
}