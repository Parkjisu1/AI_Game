
class GameScene
{
    constructor()
    {
        this.gameStage = new PIXI.Container();
        this.gameStage.interactive = true;
        this.gameStage.width = winSize.width;
        this.gameStage.height = winSize.height;
        this.gameStage.hitArea = app.screen;
        GameContainer.addChild(this.gameStage);

        this.minSpawnInterval = 2;
        this.maxSpawnInterval = 2.5;
        this.spawnInterval = this.minSpawnInterval;
        this.gameTimer = 59;
        this.spawnSeconds = 0;

        this.touchStart = {x: 0, y:0};
        this.touchEnd = {x:0, y:0};

        this.isGameOver = false;

        this.scoreText = new PIXI.Text('0', menuTextStyle);
        this.scoreText.position.set(10, 10);
        this.scoreText.scale.set(2, 2);
        this.score = 0;
        this.gameStage.addChild(this.scoreText);

        this.timerText = new PIXI.Text('0:' + this.gameTimer, menuTextStyle);
        this.timerText.scale.set(2, 2);
        this.timerText.position.set(winSize.width - this.timerText.width - 10, 10);
        this.gameStage.addChild(this.timerText);

        
        app.ticker.add((delta) => { this.Update(delta); });
    }

    spawnFruit()
    {
        this.spawnSeconds = 0;
        if(this.gameTimer < 15)
        {
            this.minSpawnInterval = 0.5;
            this.maxSpawnInterval = 0.75;
        }
        else if(this.gameTimer < 30)
        {
            this.minSpawnInterval = 0.75;
            this.maxSpawnInterval = 1.15;
        }

        this.spawnInterval = (Math.random() * (this.maxSpawnInterval - this.minSpawnInterval) + this.minSpawnInterval).toFixed(2);
        var fruitSpawned = new Fruit(this.gameStage);
    }

    addScore(scoreVal)
    {
        this.score += scoreVal;
        this.scoreText.text = this.score;
    }

    updateTimerText()
    {
        var secondsLeft = Math.floor(this.gameTimer);
        var secondsString = secondsLeft.toString();
        var leadingString = secondsString.length < 2 ? '0:0' : '0:';
        this.timerText.text = leadingString + Math.floor(this.gameTimer);
    }

    showGameOver()
    {
        console.log("Game Over");
        this.isGameOver = true;

        var gameOverPanel = PIXI.Sprite.from(PIXI.Assets.get('BoardTexture'));
        gameOverPanel.anchor.set(0.5, 0.5);
        gameOverPanel.width = winSize.width * 0.75;
        gameOverPanel.height = winSize.height * 0.5;
        gameOverPanel.position.set(winSize.width/2, winSize.height/2);
        this.gameStage.addChild(gameOverPanel);

        var finalScoreText = new PIXI.Text('Game Over!\nYour final score:\n' + this.score, menuTextStyle);
        finalScoreText.anchor.set(0.5, 0.5);
        finalScoreText.position.set(gameOverPanel.x, gameOverPanel.y);
        this.gameStage.addChild(finalScoreText);
    }

    Update(delta)
    {
        for(var i = 0; i < this.gameStage.children.length; i++)
        {
            var bounds = this.gameStage.children[i].getBounds();
            this.gameStage.children[i].renderable = bounds.x >= -200 && bounds.y >= -200 &&
            bounds.x + bounds.width * 0.5 <= winSize.width && bounds.y+bounds.height * 0.5 <= winSize.height;
        }

        if(this.isGameOver)
        {
            return;
        }

        this.spawnSeconds += 1/app.ticker.FPS * delta;
        this.gameTimer -= 1/app.ticker.FPS * delta;

        if(this.gameTimer < 0)
        {
            this.gameTimer = 0;
            this.showGameOver();
        }

        this.updateTimerText();

        if(this.spawnSeconds >= this.spawnInterval && this.gameTimer > 0)
        {
            this.spawnFruit();
        }
    }
}