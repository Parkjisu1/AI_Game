class CustomButton extends Phaser.GameObjects.Container {
    constructor(scene, x, y, upTexture, overTexture, buttonText, textSize, yTextOffset, scale) {
        super(scene, x, y);
        this.scene = scene;

        this.upImage = scene.add.image(0, 0, upTexture);
        this.overImage = scene.add.image(0, 0, overTexture);
        this.buttonText = scene.add.text(0, -yTextOffset, buttonText, {
            fontSize: `${textSize}px`,
            color: '#000000'
        }).setOrigin(0.5, 0.5);

        // scale image (I only use this because I can't find a button sprite that is large enough)
        this.upImage.setScale(scale);
        this.overImage.setScale(scale);

        this.overImage.setVisible(false);

        this.add(this.upImage);
        this.add(this.overImage);
        this.add(this.buttonText);

        this.setSize(this.upImage.width * scale, this.upImage.height * scale);

        this.setInteractive()
            .on(Phaser.Input.Events.GAMEOBJECT_POINTER_OVER, () => {
                this.upImage.setVisible(false);
                this.overImage.setVisible(true);
            })
            .on(Phaser.Input.Events.GAMEOBJECT_POINTER_OUT, () => {
                this.upImage.setVisible(true);
                this.overImage.setVisible(false);
            });

        scene.add.existing(this);
    }
}
