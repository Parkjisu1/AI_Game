import { Loader as PIXILoader } from 'pixi.js';

export class Loader {

    private _loader: PIXILoader;

    get loader() { return this._loader };

    constructor(pixiLoader: PIXILoader) {
        this._loader = pixiLoader;
    }

    load(): Promise<void> {
        const config = window['Assets'];
        const keys = Object.keys(config);

        for (let name of keys) {
            const base64 = config[name];
            this.loader.add(name, base64);
        }

        return new Promise(resolve => {
            this.loader.load(() => resolve());
        })
    }
}