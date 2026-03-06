var GameContainer = new PIXI.Container();
app.stage.addChild(GameContainer);

var gameBG;

var titleText;

var playButton;

function loadMenu()
{
    gameBG = PIXI.Sprite.from(PIXI.Assets.get('GameBG'));
    gameBG.width = winSize.width;
    gameBG.height = winSize.height;
    GameContainer.addChild(gameBG);

    titleText = new PIXI.Text('Produce Shinobi', menuTextStyle);
    titleText.anchor.set(0.5, 0.5);
    titleText.x = winSize.width/2;
    titleText.y = winSize.height/2;
    GameContainer.addChild(titleText);

    playButton = new UIButton("PLAY", winSize.width/2, winSize.height/2 + 100, 100, 50, 0x33FF33, 0x000000, onPlayClick);
    GameContainer.addChild(playButton.buttonGraphic);
}

function hideMenu()
{
    titleText.visible = false;
    playButton.buttonGraphic.visible = false;
    playButton.buttonText.visible = false;
}

var gameScene;

function onPlayClick()
{
    hideMenu();

    gameScene = new GameScene();
}


