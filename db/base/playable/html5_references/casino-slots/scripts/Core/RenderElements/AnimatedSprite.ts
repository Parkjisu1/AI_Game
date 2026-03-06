import { Texture, AnimatedSprite as PIXIAnimatedSprite } from "pixi.js";
import { RenderElement } from "./RenderElement";

export class AnimatedSprite extends RenderElement {

    protected textureName: string;

    protected _node: PIXIAnimatedSprite;

    constructor(config: any) {
        super(config);
        this.textureName = this.config.textureName;
    }

    protected createNode(): PIXIAnimatedSprite {
        const textures: Texture[] = [];
        for (let i = 0; i <= this.config.count; i++) {
            const texture = Texture.from(`${this.config.textureName}/${i}`);
            textures.push(texture);
        }
        const animation = new PIXIAnimatedSprite(textures);

        animation.anchor.set(.5);
        animation.animationSpeed = this.config.speed || 0.5;
        animation.loop = false;

        return animation;
    }

    play(): Promise<void> {
        return new Promise(resolve => {
            this.node.onComplete = () => resolve();
            this.node.play();
        });
    }
}