import { Container } from "./Core/RenderElements/Container";
import { Graphics } from "pixi.js";

export class MaskHolder extends Container {

    protected _mask: Graphics;
    get mask() { return this._mask };

    constructor(config) {
        super(config);
        this._mask = new Graphics();
        this.createMask(this._mask, config.color, config.x, config.y, config.width, config.height);
    }

    createMask(mask: Graphics, color: number, x: number, y: number, width: number, height: number){
        
        mask.beginFill(color);
        mask.drawRect(x, y, width, height);
        mask.endFill();
        
    }
}