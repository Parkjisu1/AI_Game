class Money extends Phaser.GameObjects.Container {
    constructor(scene, x, y, spriteKey, glowKey, scale = 1, scaleTo = 1, glowScale = 1, glowScaleTo = 1, mode = 1, building) {
        if (!scene) {
            console.error("Scene is not defined.");
            return;
        }

        super(scene, x, y);

        this.scene = scene;
        this.mode = mode;
        this.sendMoneyToX = this.scene.moneyIcon.x;
        this.sendMoneyToY = this.scene.moneyIcon.y;
        this.scaleValue = scaleTo;
        this.building = building;

        // config paramater
        // json reader
        this.moneyData = this.scene.cache.json.get('moneyConfig');

        this.spawnMoneySpriteRate = this.moneyData.spawnRate;
        this.moneySpriteTweenDuration = this.moneyData.tweenDuration;
        this.levelUpArrowScaleFrom = 0.1;
        this.levelUpArrowScaleTo = this.moneyData.scaleTo;

        // audio
        this.popSound = this.scene.sound.add("audio_pop", {
            loop: false,
            volume: 1 // Adjust volume as needed
        });

        if (mode != 3 && mode != 5)
            this.popSound.play();

        this.collectSound = this.scene.sound.add("audio_moneyCollect", {
            loop: false,
            volume: 0.1 // Adjust volume as needed
        });

        // Create the glow sprite and set it to spin
        this.glow = scene.add.sprite(0, 0, glowKey);
        this.glow.setScale(glowScale);
        this.scene.tweens.add({
            targets: this.glow,
            angle: 360,
            duration: 2000,
            ease: 'Linear',
            repeat: -1
        });

        // Create the money sprite
        this.money = scene.add.sprite(0, 0, spriteKey);
        this.money.setScale(scale);

        // Add sprites to the container
        this.add(this.glow);
        this.add(this.money);

        this.scene.tweens.add({
            targets: this.money,
            scale: scaleTo,
            duration: 300,
            ease: "Back.easeOut",
        });

        this.scene.tweens.add({
            targets: this.glow,
            scale: glowScaleTo,
            duration: 300,
            ease: "Back.easeOut",
        });

        // Make the money sprite interactive
        this.money.setInteractive();
        // Add this container to the scene
        scene.add.existing(this);

        // Ensure `sendMoney` is properly bound
        this.money.on('pointerdown', () => {
            switch (this.mode) {
                case 1:
                    this.collectSound.play();

                    // spawn 5 money sprite
                    for (let i = 0; i < 5; i++) {
                        this.scene.time.delayedCall(i * this.spawnMoneySpriteRate, () => {
                            this.sendMoney(scene);
                        });
                    }

                    // update money text
                    this.scene.moneyTotal = this.scene.moneyTotal + 100;
                    this.scene.moneyLabel.text = this.scene.moneyTotal;

                    // create time circle with mode = 2
                    // TimerCircle(scene, x, y, duration, spriteKey, onCompleteSpriteKey, onCompleteSpriteScale = 1, onCompleteGlowKey, mode = 1, building)
                    let timerCircle = new TimerCircle(scene, x, y, 2, "speechBubbleMoney", "moneySingle", this.scene.moneyScale, "glow", 2, this.building);
                    this.destroy();
                    break;

                case 2:
                    this.collectSound.play();

                    // spawn 5 money sprite
                    for (let i = 0; i < 5; i++) {
                        this.scene.time.delayedCall(i * this.spawnMoneySpriteRate, () => {
                            this.sendMoney(scene);
                        });
                    }

                    // update money text
                    this.scene.moneyTotal = this.scene.moneyTotal + 100;
                    this.scene.moneyLabel.text = this.scene.moneyTotal;

                    // add the level up sprite
                    // Money(scene, x, y, spriteKey, glowKey, scale = 1, scaleTo = 1, glowScale = 1, glowScaleTo = 1, mode)
                    let levelUpArrow = new Money(this.scene, this.x, this.y, "levelUpArrow", 
                                                glowKey, this.levelUpArrowScaleFrom, this.levelUpArrowScaleTo, 
                                                glowScale, glowScaleTo, 
                                                3,
                                                this.building
                                            );

                    this.destroy();
                    break;

                case 3:
                    this.scene.pointer.setVisible(false);
                    this.building.levelUp();

                    // create TimerCircle mode 3
                    let timerCircle3 = new TimerCircle(this.scene, x, y, 1, "speechBubbleMoney", "moneySingle", this.scene.moneyScale, "glow", 3, this.building);

                    // pointer
                    //this.scene.pointer.setVisible(false);

                    this.destroy();
                    break;

                // case 4 and 5 are for the 3rd building
                case 4:
                    this.collectSound.play();

                    // spawn 5 money sprite
                    for (let i = 0; i < 5; i++) {
                        this.scene.time.delayedCall(i * this.spawnMoneySpriteRate, () => {
                            this.sendMoney(scene);
                        });
                    }

                    // update money text
                    this.scene.moneyTotal = this.scene.moneyTotal + 100;
                    this.scene.moneyLabel.text = this.scene.moneyTotal;

                    // add the level up sprite
                    // Money(scene, x, y, spriteKey, glowKey, scale = 1, scaleTo = 1, glowScale = 1, glowScaleTo = 1, mode)
                    let levelUpArrow2 = new Money(this.scene, this.x, this.y, "levelUpArrow", 
                                                glowKey, this.levelUpArrowScaleFrom, this.levelUpArrowScaleTo, 
                                                glowScale, glowScaleTo, 
                                                5,
                                                this.building
                                            );

                    this.destroy();
                    break;
                
                case 5:
                    this.building.levelUp();

                    // pointer
                    this.scene.pointer.setVisible(false);

                    // turn off all the timer circle
                    this.scene.turnOffAllTimerCircle();
                    
                    this.destroy();
                    break;
            }
        });
    }

    sendMoney = (scene) => {
        if (scene) {
            let moneyToSend = scene.add.image(this.x, this.y, "moneySingle").setScale(this.scaleValue);

            // if (game.verticalOffset >= 0)
            // {
            //     this.sendMoneyToX = scene.moneyIcon.x;
            //     this.sendMoneyToY = scene.moneyIcon.y;
            // }
            // else
            // {
            //     this.sendMoneyToX = 1700;
            //     this.sendMoneyToY = scene.downloadBtnY - game.verticalOffset - 170;
            // }

            scene.tweens.add({
                targets: moneyToSend,
                x: this.sendMoneyToX,
                y: this.sendMoneyToY,
                duration: this.moneySpriteTweenDuration,
                ease: "Linear",
                onComplete: () => {
                    moneyToSend.destroy();
                }
            });
        } else {
            console.error("Scene is not defined.");
        }
    }
}
