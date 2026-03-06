class Load extends Phaser.Scene
{
    constructor()
    {
        super("bootGame");
    }

    preload()
    {
        // dir prefixes
        this.audioDirPrefix = "assets/Audio/";
        this.uiDirPrefix = "assets/UI/";
        this.configDirPrefix = "LevelConfig/";

        // UI
        this.load.image("button", this.uiDirPrefix + "button.png");
        this.load.image("buttonPressed", this.uiDirPrefix + "button pressed.png");
        this.load.image("gameLogo", this.uiDirPrefix + "gameLogo.png");
        this.load.image("cat", "assets/Characters/cat.png");
        this.load.image("pointer", this.uiDirPrefix + "pointer.png");

        // background
        this.load.image("background", "assets/background/BG.png");

        // bubble speech
        this.load.image("speechBubble", this.uiDirPrefix + "speechBubble.png");
        this.load.image("speechBubbleMoney", this.uiDirPrefix + "bubbleMoney.png");

        // money
        this.load.image("moneySingle", this.uiDirPrefix + "moneySingle.png");
        this.load.image("moneyPlural", this.uiDirPrefix + "moneyPlural.png");
        this.load.image("glow", this.uiDirPrefix + "glow.png");
        this.load.image("moneyPanel", this.uiDirPrefix + "moneyPanel.png");

        // level up
        this.load.image("levelUpArrow", this.uiDirPrefix + "levelUpArrow.png");
        this.load.image("hammer", this.uiDirPrefix + "hammer.png");

        // particle
        this.load.image("star", this.uiDirPrefix + "star.png");
        this.load.image("dust", this.uiDirPrefix + "dust.png");
        this.load.image("party1", this.uiDirPrefix + "party1.png");
        this.load.image("party2", this.uiDirPrefix + "party2.png");
        this.load.image("lightColumn", this.uiDirPrefix + "lightColumn.png");
        this.load.image("singleDollar", this.uiDirPrefix + "singleDollar.png");

        // sound
        this.load.audio("audio_bgTheme", this.audioDirPrefix + "BGTheme.mp3");
        this.load.audio("audio_autoCollectMoney", this.audioDirPrefix + "autoCollectMoney.mp3");
        this.load.audio("audio_building", this.audioDirPrefix + "building.mp3");
        this.load.audio("audio_moneyCollect", this.audioDirPrefix + "moneyCollect.mp3");
        this.load.audio("audio_upgrade", this.audioDirPrefix + "upgrade.mp3");
        this.load.audio("audio_winning", this.audioDirPrefix + "winning.mp3");
        this.load.audio("audio_pop", this.audioDirPrefix + "pop.mp3");

        // json
        this.load.json("levelMakerConfig", this.configDirPrefix + "LevelMakerConfig.json");
        this.load.json("moneyConfig", this.configDirPrefix + "MoneyConfig.json");

        // atlas
        this.load.atlas("dryer1", "assets/Pack_v2/Dryer_upgrades/Dryer_upgrades1.png", "assets/Pack_v2/Dryer_upgrades/Dryer_upgrades1.json");
        this.load.atlas("dryer2", "assets/Pack_v2/Dryer_upgrades/Dryer_upgrades2.png", "assets/Pack_v2/Dryer_upgrades/Dryer_upgrades2.json");

        this.load.multiatlas('restingArea1', 'assets/Pack_v2/RestingArea_upgrades/RestingArea_upgrades1.json', 'assets/Pack_v2/RestingArea_upgrades');
        this.load.multiatlas('restingArea2', 'assets/Pack_v2/RestingArea_upgrades/RestingArea_upgrades2.json', 'assets/Pack_v2/RestingArea_upgrades');

        this.load.atlas("shredder1", "assets/Pack_v2/Shredder_upgrades/Shredder_upgrades1.png", "assets/Pack_v2/Shredder_upgrades/Shredder_upgrades1.json");
        this.load.atlas("shredder2", "assets/Pack_v2/Shredder_upgrades/Shredder_upgrades2-0.png", "assets/Pack_v2/Shredder_upgrades/Shredder_upgrades2.json");

        // anchor
        this.load.plugin('rexanchorplugin', 'https://raw.githubusercontent.com/rexrainbow/phaser3-rex-notes/master/dist/rexanchorplugin.min.js', true);
    }

    create()
    {
        this.add.text(20, 20, "Loading...");
        this.scene.start("levelSelect");
    }
}