class LevelSelect extends Phaser.Scene {
    constructor() {
        super("levelSelect");
    }

    create() {
        this.scene.start('levelMaker');
    }
}