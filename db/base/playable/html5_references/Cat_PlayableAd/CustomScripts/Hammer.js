class Hammer extends Phaser.GameObjects.Sprite {
    constructor(scene, x, y, scale, texture, tweenHitAngle, tweenHitDuration, tweenEase, vanishDuration) {
        super(scene, x, y, texture);

        this.scene = scene;
        this.setScale(scale).setOrigin(0, 1); // Set the origin to (0, 1)

        // config parameter:
        this.tweenHitAngle = tweenHitAngle;
        this.tweenHitDuration = tweenHitDuration;
        this.tweenEase = tweenEase;
        this.vanishDuration = vanishDuration;

        // audio
        this.buildingSound = this.scene.sound.add("audio_building", {
            loop: false,
            volume: 1 // Adjust volume as needed
        });

        // dust particle
        this.dustEmitter = this.scene.add.particles(x + 200, y + 50, "dust", {
            lifespan: 800,
            speed: { min: 250, max: 650 },
            scale: { min: 0.25, max: 0.5 },
            alpha: { start: 0.7, end: 0.2 },
            blendMode: Phaser.BlendModes.NORMAL,
            emitting: false
        });
        this.dustEmitter.setDepth(1);

        // Add this sprite to the scene
        scene.add.existing(this);
    }

    hit() {
        // audio
        this.buildingSound.play();

        // Tween to rotate 45 degrees clockwise in 0.2 seconds
        this.scene.tweens.add({
            targets: this,
            angle: this.tweenHitAngle,
            duration: this.tweenHitDuration,
            ease: this.tweenEase,
            onComplete: () => {
                // dust fx
                this.dustEmitter.explode(20);

                // Tween to rotate back to 0 degrees in 0.2 seconds
                this.scene.tweens.add({
                    targets: this,
                    angle: 0,
                    duration: this.tweenHitDuration,
                    ease: this.tweenEase,
                    onComplete: () => {
                        // Tween to fade out the sprite in 0.1 seconds
                        this.scene.tweens.add({
                            targets: this,
                            alpha: 0,
                            duration: this.vanishDuration,
                            ease: this.tweenEase,
                        });
                    }
                });
            }
        });
    }
}