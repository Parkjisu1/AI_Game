import { RenderElement } from "./RenderElement";
import { Text as PIXIText } from 'pixi.js';

export class Text extends RenderElement {

    protected _node: PIXIText;

    constructor(config){
        super(config);
    }

    protected createNode(): PIXIText {
        return new PIXIText(this.config.value, this.config.style);
    }
}