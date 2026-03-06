import { RenderElement } from "./RenderElement";
import { Container as PIXIContainer } from "pixi.js";

export class Container extends RenderElement {

    public _node: PIXIContainer;

    constructor(config) {
        super(config);
    }

    protected createNode(): PIXIContainer {
        return new PIXIContainer();
    }
}