// // Phaser configuration
// var config = {
//     type: Phaser.AUTO,
//     backgroundColor: 0xb3c3d3,
//     scene: [Load, LevelSelect, LevelMaker],
//     scale: {
//         mode: Phaser.Scale.NONE, // Disable Phaser's built-in scaling
//         autoCenter: Phaser.Scale.CENTER_VERTICALLY,
//         width: 1440 * 1.6,
//         height: 3200
//     }
// };
//
// // Initialize Phaser game
// var game = new Phaser.Game(config);
//
// // Resize game function
// game.resizeGame = function resizeGame() {
//     const canvas = game.canvas;
//     if (canvas) {
//         const windowHeight = window.innerHeight;
//         const gameHeight = game.config.height;
//         const gameWidth = game.config.width;
//         const scaleRatio = windowHeight / gameHeight;
//
//         // Calculate new width for canvas
//         const scaledWidth = gameWidth * scaleRatio;
//
//         // Update canvas dimensions
//         canvas.style.height = `${windowHeight}px`;
//         canvas.style.width = `${scaledWidth}px`;
//         //console.log(canvas.style.width)
//         //canvas.style.marginLeft = `${(window.innerWidth - scaledWidth) / 2}px`;
//
//         // canvas.style.marginTop = '0px';
//
//         // Calculate the horizontal offset to center the canvas
//         const horizontalOffset = (window.innerWidth - scaledWidth) / 2;
//         if (horizontalOffset > 0) {
//             canvas.style.transform = `translateX(${horizontalOffset}px)`;
//         } else {
//             canvas.style.transform = `translateX(${horizontalOffset}px)`;
//         }
//
//         canvas.style.marginTop = '0px';
//     }
// }
//
// // Call resizeGame on game boot and window resize
// game.events.once('boot', game.resizeGame);
// window.addEventListener('resize', game.resizeGame);

var config = {
    type: Phaser.AUTO,
    backgroundColor: 0xb3c3d3,
    scene: [Load, LevelSelect, LevelMaker],
    scale: {
        mode: Phaser.Scale.NONE, // Disable Phaser's built-in scaling
        autoCenter: Phaser.Scale.CENTER_VERTICALLY,
        width: 1152,
        height: 1600
    }
};

// Initialize Phaser game
var game = new Phaser.Game(config);

// Resize game function
game.resizeGame = function resizeGame() {
    const canvas = game.canvas;
    if (canvas) {
        const windowHeight = window.innerHeight;
        const windowWidth = window.innerWidth;
        const gameHeight = game.config.height;
        const gameWidth = game.config.width;
        const scaleRatio = windowHeight / gameHeight;

        // Calculate new width for canvas
        const scaledWidth = gameWidth * scaleRatio;

        // Update canvas dimensions
        canvas.style.height = `${windowHeight}px`;
        canvas.style.width = `${scaledWidth}px`;

        // Calculate the horizontal offset to center the canvas
        const horizontalOffset = (windowWidth - scaledWidth) / 2;

        if (horizontalOffset <= 0) {
            // height always fits, width can be shown or hidden
            game.verticalOffset = 0;
            //canvas.style.transform = `translateX(${horizontalOffset}px)`;

            // on some ios device using canvas.style.marginTop won't make the hitbox of the sprite change with it
            // and if we don't change marginTop, there will be a blank space under the canvas, so we need to use translate on canvas
            // this line is to get the pixel we need to move the canvas down to fill the blank space
            var blankPixels = parseInt(canvas.style.marginTop, 10) || 0;

            // move the canvas down
            canvas.style.transform = `translateX(${horizontalOffset}px) translateY(${-blankPixels}px)`;

        } else {
            // width always fits, height can be shown or hidden
            // Switch to centering both horizontally and vertically
            const scaleRatioWidth = windowWidth / gameWidth;
            game.scaleRatio = scaleRatioWidth;

            // Apply the new scaling based on width
            canvas.style.width = `${windowWidth}px`;
            canvas.style.height = `${gameHeight * scaleRatioWidth}px`;

            // Recalculate the vertical offset to center the canvas
            const verticalOffset = (windowHeight - gameHeight * scaleRatioWidth) / 2;
            game.verticalOffset = verticalOffset;

            var blankPixels = parseInt(canvas.style.marginTop, 10) || 0;

            // Center the canvas both horizontally and vertically
            canvas.style.transform = `translateX(0px) translateY(${verticalOffset - blankPixels}px)`;
        }
    }
}

// Call resizeGame on game boot and window resize
game.events.once('boot', game.resizeGame);
window.addEventListener('resize', game.resizeGame);
