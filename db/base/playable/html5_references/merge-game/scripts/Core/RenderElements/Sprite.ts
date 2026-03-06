import { RenderElement } from "./RenderElement";
import { Sprite as PIXISprite } from "pixi.js";

export class Sprite extends RenderElement {

    protected _node: PIXISprite;

    constructor(config) {
        super(config);
    }

    protected createNode(): PIXISprite {
        return PIXISprite.from(this.config.texture)
    }
}