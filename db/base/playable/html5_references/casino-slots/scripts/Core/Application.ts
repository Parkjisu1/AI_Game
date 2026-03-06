import { Application as PIXIApplication, utils } from 'pixi.js';
import { TScreenType, TSize } from './types';
import { Loader } from './Loader';
import { RenderElementFactory } from './RenderElementFactory';
import { RenderElement } from './RenderElements/RenderElement';
import { defaultConfig } from '../DefaultConfig';
import * as TWEEN from '@tweenjs/tween.js';
import { APP_EVENTS } from './APP_EVENTS';
import { GameController } from '../GameController';

export class Application extends utils.EventEmitter {

    private app: PIXIApplication;
    private loader: Loader;
    private _size: TSize;
    private _renderElementFactory: RenderElementFactory;
    private _renderElements: Map<string, RenderElement>;
    private _screenType: TScreenType;
    private gameController: GameController;

    get renderElements() { return this._renderElements };
    get renderElementsFactrory() { return this._renderElementFactory };
    get size() { return this._size };
    get screenType() { return this._screenType };

    set screenType(value: TScreenType) { this._screenType = value };

    constructor() {
        super();
        this._size = this.calculateSizes();
        this.app = this.createApp();
        this.loader = new Loader(this.app.loader);
        this._renderElements = new Map();
        this._renderElementFactory = new RenderElementFactory(this);

        window.addEventListener('resize', this.resize.bind(this), false);
        this.init();
    }

    private async init() {
        await this.loader.load();
        this.readConfig();
        this.emit(APP_EVENTS.ON_LOAD.toString());
        this.resize();
        this.app.ticker.add(this.update, this);
        this.gameController = new GameController();
    }

    private createApp(): PIXIApplication {
        return new PIXIApplication({
            view: <HTMLCanvasElement>document.getElementById('playable-canvas'),
            antialias: true,
            width: this.size.width, 
            height: this.size.height
        });
    }

    private calculateSizes() {
        let width = this.isPortrait() ? 1080 : 1920;
        let height = this.isPortrait() ? 1920 : 1080;

        this.isPortrait() ?
            width = Math.round(innerWidth * height / innerHeight) :
            height = Math.round(width * innerHeight / innerWidth);

        return { width, height };
    }

    private resize() {
        this._size = this.calculateSizes();
        const canvas = <HTMLCanvasElement> document.getElementById("playable-canvas");
        canvas.style.width = window.innerWidth + 'px';
        canvas.style.height = window.innerHeight + 'px';
        canvas.width = this.size.width;
        canvas.height = this.size.height;
        this.app.renderer.resize(this.size.width, this.size.height);
        this.calculateScreenType();
        this.emit(APP_EVENTS.RESIZE.toString());
    }

    private calculateScreenType() {
        const ratio = this.isPortrait() ? this.size.width / this.size.height : this.size.height / this.size.width;
        
        if (ratio < 0.5) {
            this.screenType = 'S';
        } else if (ratio > 0.5 && ratio < 0.6) {
            this.screenType = 'M';
        } else if (ratio > 0.6) {
            this.screenType = 'L';
        }
    }

    public isPortrait() {
        return innerWidth < innerHeight;
    }

    public readConfig() {
        const keys = Object.keys(defaultConfig);

        keys.forEach(key => {
            const config = defaultConfig[key];
            config.key = key;
            const renderElement = this.renderElementsFactrory.createRenderElement(config);
            this.app.stage.addChild(renderElement.node);
        })
    }

    getElementByID(id: string) {
        return this.renderElements[id] || null;
    }

    update() {
        TWEEN.update();
    }
}
