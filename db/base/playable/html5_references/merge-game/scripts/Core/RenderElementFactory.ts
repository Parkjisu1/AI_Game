import { Application } from "./Application";
import { Sprite } from "./RenderElements/Sprite";

export class RenderElementFactory {

    private app: Application;

    constructor(app: Application) {
        this.app = app;
    }

    createRenderElement(config) {
        const type = config.class ? config.class : Sprite;
        const renderElement = new type(config);
        const id = config.id ? config.id : null;

        if (id)
            this.app.renderElements[config.id] = renderElement;

        return renderElement;
    }
}