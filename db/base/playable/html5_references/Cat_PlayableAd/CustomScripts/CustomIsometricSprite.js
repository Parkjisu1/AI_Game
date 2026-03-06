class CustomIsometricSprite extends Phaser.GameObjects.Container {
    constructor(scene, ground, building, buildingOffsetX, buildingOffsetY, buildingScale, scale = 1) {
        super(scene);
        this.scene = scene;
        
        this.ground = scene.add.image(0, 0, ground);
        this.building = scene.add.image(buildingOffsetX, buildingOffsetY, building)
        this.building.setScale(buildingScale); 
        this.add(this.ground);
        this.add(this.building);
        
        this.setScale(scale);
        
        scene.add.existing(this);
    }
}