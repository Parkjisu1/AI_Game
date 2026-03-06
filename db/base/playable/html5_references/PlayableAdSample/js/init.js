var app;
var renderer;
var loader;

var winSize = {width:360, height:740};
var winRatio = winSize.width/winSize.height;

app = new PIXI.Application(
    {
        width:winSize.width,
        height:winSize.height,
        backgroundColor: 0xAAAAAA,
        autoResize:true
    }
)
app.resizeTo = window;
renderer = PIXI.autoDetectRenderer(winSize[0], winSize[1]);

createjs.Ticker.setFPS(app.ticker.FPS);

PIXI.Assets.add('FruitsTexture', 'assets/GameFruits.png');
PIXI.Assets.add('FruitsData', 'assets/GameFruits.json');
PIXI.Assets.add('BoardTexture', 'assets/board.png');
PIXI.Assets.add('GameBG', 'assets/game_bg.jpg');

const assetLoadPromise = PIXI.Assets.load(['FruitsTexture', 'FruitsData', 'BoardTexture', 'GameBG']);

assetLoadPromise.then(()=> {
    loadMenu();
});

document.body.appendChild(app.view);

