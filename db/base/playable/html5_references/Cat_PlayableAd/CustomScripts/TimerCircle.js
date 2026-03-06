class TimerCircle extends Phaser.GameObjects.Container {
    constructor(scene, x, y, duration, spriteKey, onCompleteSpriteKey, onCompleteSpriteScale = 1, onCompleteGlowKey, mode = 1, building) {
        super(scene, x, y);

        this.scene = scene;
        this.duration = duration;
        this.elapsed = 0;
        this.spriteKey = spriteKey;
        this.onCompleteSpriteKey = onCompleteSpriteKey;
        this.onCompleteSpriteScale = onCompleteSpriteScale;
        this.onCompleteGlowKey = onCompleteGlowKey;
        this.mode = mode;
        this.building = building;

        // audio
        this.autoCollectSound = this.scene.sound.add("audio_autoCollectMoney", {
            loop: false,
            volume: 0.5 // Adjust volume as needed
        });

        // Create the sprite
        this.sprite = scene.add.sprite(0, 0, spriteKey);
        this.add(this.sprite);

        this.setScale(0.1);

        this.scene.tweens.add({
            targets: this,
            scale: 0.5,
            duration: 300,
            ease: "Back.easeOut",
        });

        // Create the graphics object for the timer circle
        this.timerGraphics = scene.add.graphics();
        this.add(this.timerGraphics);

        // Start the timer
        this.timerEvent = scene.time.addEvent({
            delay: 1000 / 60, // 60 times per second
            callback: this.updateTimer,
            callbackScope: this,
            loop: true
        });

        // Add this container to the scene
        scene.add.existing(this);
    }

    updateTimer() {
        // Increment the elapsed time
        this.elapsed += 1 / 60;

        // Clear the graphics
        this.timerGraphics.clear();

        // Calculate the angle of the arc
        let angle = Phaser.Math.DegToRad((this.elapsed / this.duration) * 360);

        // Draw the timer arc
        this.timerGraphics.lineStyle(16, 0xfcd703); // Line thickness and color
        this.timerGraphics.beginPath();
        this.timerGraphics.arc(0, -15, 110, -Phaser.Math.PI2 / 4, angle - Phaser.Math.PI2 / 4, false);
        this.timerGraphics.strokePath();

        // Check if the timer has completed
        if (this.elapsed >= this.duration && this.scene != undefined) {
            switch(this.mode) {
                case 1:
                    // Add the onComplete sprite
                    let money = new Money(this.scene, this.x, this.y, 
                                            this.onCompleteSpriteKey, this.onCompleteGlowKey, 
                                            0.1, this.onCompleteSpriteScale,
                                            0.1, 0.5,
                                            1,
                                            this.building
                                        );
                    break;

                case 2:
                    let money2 = new Money(this.scene, this.x, this.y, 
                                            this.onCompleteSpriteKey, this.onCompleteGlowKey, 
                                            0.1, this.onCompleteSpriteScale,
                                            0.1, 0.5,
                                            2,
                                            this.building
                                        );
                    break;

                case 3:
                    this.building.bounceBuilding();
                        this.autoCollectSound.play();

                        // Math.floor(Math.random() * 4) + 4 generates a random number between 4 and 7
                        // Math.random returns [0, 1), * 4 we get [0, 4), floor it we get from 0 to 3, + 4 we get [4, 8) or 4 to 7 
                        // Get the above and multiple by 50, we can cenerate a random amount between 200 and 350, divisible by 50
                        if (this.scene.moneyTotal < 9999)      // we also need to set a threshold
                        {
                            let randomAmount = (Math.floor(Math.random() * 4) + 4) * 50
                            this.scene.moneyTotal += randomAmount;
                            this.scene.moneyLabel.text = this.scene.moneyTotal;
                        }

                        // create TimerCircle mode 3 will create itself
                        let timerCircle3 = new TimerCircle(this.scene, this.x, this.y, 1, "speechBubbleMoney", "moneySingle", this.scene.moneyScale, "glow", 3, this.building);
                        this.scene.timerCircleGroup.add(timerCircle3);

                    break;

                // this is for building 3
                case 4:
                    let money3 = new Money(this.scene, this.x, this.y, 
                                            this.onCompleteSpriteKey, this.onCompleteGlowKey, 
                                            0.1, this.onCompleteSpriteScale, 
                                            0.1, 0.5,
                                            4,
                                            this.building
                                        );
                    break;
            }

            // Destroy the timer circle and its sprite
            this.timerEvent.remove(false);
            this.destroy();
        }
    }
}
