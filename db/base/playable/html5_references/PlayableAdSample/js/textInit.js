var menuTextStyle = new PIXI.TextStyle({
    fontFamily: 'Montserrat',
    fontSize: 24,
    fill: 0xFFFFFF,
    stroke: 0x000000,
    strokeThickness: 3,
    align: 'center'
});

class UIButton
{
    constructor(buttonText, x,y, width, height, fillColor, strokeColor, callbackFunc)
    {
        this.buttonGraphic = new PIXI.Graphics();
        this.buttonGraphic.beginFill(fillColor)
        .lineStyle(3, strokeColor)
        .drawRect(x - width/2, y - width/2, width, height)
        .endFill();

        this.buttonGraphic.interactive = true;
        this.buttonGraphic.cursor = 'pointer';
        this.buttonGraphic.addListener('pointerdown', callbackFunc);

        this.buttonText = new PIXI.Text(buttonText, menuTextStyle);
        this.buttonText.anchor.set(0.5, 0.5);
        this.buttonText.x = x;
        this.buttonText.y = y - this.buttonText.height * 0.8;
        this.buttonGraphic.addChild(this.buttonText);
    }


}