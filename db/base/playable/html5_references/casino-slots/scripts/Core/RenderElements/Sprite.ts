import { RenderElement } from "./RenderElement";
import { Sprite as PIXISprite, Texture } from "pixi.js";

export class Sprite extends RenderElement {

    protected _node: PIXISprite;

    constructor(config) {
        super(config);
        // Проверяем, что текстура инициализирована
        if (!config.texture) {
            throw new Error("Texture is required to create a Sprite.");
        }
    }

    protected createNode(): PIXISprite {
        // Убедимся, что текстура корректная
        const texture = Texture.from(this.config.texture);
        return new PIXISprite(texture);
    }

    get node(): PIXISprite {
        if (!this._node) {
            this._node = this.createNode();
        }
        return this._node;
    }
}
