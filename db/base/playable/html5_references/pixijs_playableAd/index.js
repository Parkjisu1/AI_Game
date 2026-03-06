window.onload = function() {
  let appHolder, menu, menu2, menu3, menuHover, menu2Hover, menu3Hover,
      btn, austin, oldStair, hammer, btnOk, finalImgSize, id,
      menuH, menuW, book, chair, decor, globe, logo, table, plant1, plant2,
      stairIcon1, stairIcon2, stairIcon3, stairIconSize, bg, newStair1, newStair2, newStair3, finalImg, overlay,
      isMenuClicked = {
        menu1: false,
        menu2: false,
        menu3: false
      };

  const ease = new Ease.Ease(),
        size = [1390, 640],
        ratio = size[0] / size[1],
        graphics = new PIXI.Graphics(),
        sprite = PIXI.Sprite,
        app = new PIXI.Application({
              width: size[0],         // default: 800
              height: size[1],        // default: 600
              antialias: true,        // default: false
              transparent: false,     // default: false
              resolution: 1           // default: 1
            }
        );

  app.renderer.view.style.position = "absolute";
  app.renderer.view.style.display = "block";
  appHolder = document.getElementById("playable");
  appHolder.appendChild(app.view);

  PIXI.loader
      .add("images/atlas.json")
      .load(setup);

  function setup() {
    id = PIXI.loader.resources["images/atlas.json"].textures;

    initSprites();
    addEvents();
    addImgToStage();
    animateByFrame();
    resize();
  }

  function initSprites() {
    bg = new sprite(id["background.png"]);

    austin = new sprite(id["austin.png"]);
    austin.position.set(735, 265);
    austin.anchor.set(0.5);
    austin.scale.x = 1;

    oldStair = new sprite(id["old-stair.png"]);
    oldStair.position.set(833, 125);

    book = new sprite(id["book.png"]);
    book.position.set(830, -25);

    logo = new sprite(id["logo.png"]);
    logo.position.set(30, 5);

    globe = new sprite(id["globe.png"]);
    globe.position.set(85, 108);

    plant1 = new sprite(id["plant.png"]);
    plant1.position.set(460, -40);

    plant2 = new sprite(id["plant.png"]);
    plant2.position.set(1130, 170);

    chair = new sprite(id["chair.png"]);
    chair.position.set(125, 325);

    decor = new sprite(id["decor.png"]);
    decor.position.set(1120, 435);

    table = new sprite(id["table.png"]);
    table.position.set(200, 190);

    hammer = new sprite(id["hammer.png"]);
    hammer.position.set(1140, 325);
    hammer.alpha = 0;
    hammer.buttonMode = true;
    hammer.anchor.set(0.5);
    hammer.interactive = true;
    hammer.hitArea = new PIXI.Circle(0, 0, hammer.width / 2);
    ease.add(hammer, { y: hammer.y + 10 }, { repeat: true, reverse: true, ease: 'easeOutQuad' });
    ease.add(hammer, { alpha: 1 }, { repeat: false, wait: 2000, duration: 500, ease: 'linear' });

    btnOk = new sprite(id["btn-ok.png"]);
    btnOk.buttonMode = true;
    btnOk.interactive = true;
    btnOk.alpha = 0;
    btnOk.anchor.set(0.5);

    btn = new sprite(id["btn.png"]);
    btn.position.set(690, 560);
    btn.anchor.set(0.5);
    btn.interactive = true;
    btn.buttonMode = true;
    ease.add(btn, { width: btn.width * 1.05, height: btn.height * 1.05 }, { repeat: true, reverse: true, ease: 'easeOutQuad' });

    menu = new sprite(id["menu.png"]);
    menuH = menu.height;
    menuW = menu.width;
    menu.position.set(910, 75);
    menu.buttonMode = true;
    menu.interactive = true;
    menu.hitArea = new PIXI.Circle(0, 0, menu.width / 2);
    menu.width = 0;
    menu.height = 0;
    menu.anchor.set(0.5);

    newStair1 = new sprite(id["new-stair-1.png"]);
    newStair1.position.set(1150, 228);
    newStair1.anchor.set(0.5);
    newStair1.alpha = 0;

    newStair2 = new sprite(id["new-stair-2.png"]);
    newStair2.position.set(1150, 228);
    newStair2.anchor.set(0.5);
    newStair2.alpha = 0;

    newStair3 = new sprite(id["new-stair-3.png"]);
    newStair3.position.set(1150, 228);
    newStair3.anchor.set(0.5);
    newStair3.alpha = 0;

    stairIcon1 = new sprite(id["stair-1.png"]);
    stairIconSize = {
      width: stairIcon1.width,
      height: stairIcon1.height
    };
    stairIcon1.position.set(918, 62);
    stairIcon1.width = 0;
    stairIcon1.height = 0;
    stairIcon1.anchor.set(0.5);

    stairIcon2 = new sprite(id["stair-2.png"]);
    stairIcon2.position.set(1050, 62);
    stairIcon2.width = 0;
    stairIcon2.height = 0;
    stairIcon2.anchor.set(0.5);

    stairIcon3 = new sprite(id["stair-3.png"]);
    stairIcon3.position.set(1175, 62);
    stairIcon3.width = 0;
    stairIcon3.height = 0;
    stairIcon3.anchor.set(0.5);

    menu2 = new sprite(id["menu.png"]);
    menu2.position.set(1040, 75);
    menu2.buttonMode = true;
    menu2.interactive = true;
    menu2.hitArea = new PIXI.Circle(0, 0, menu2.width / 2);
    menu2.width = 0;
    menu2.height = 0;
    menu2.anchor.set(0.5);

    menu3 = new sprite(id["menu.png"]);
    menu3.position.set(1170, 75);
    menu3.buttonMode = true;
    menu3.interactive = true;
    menu3.hitArea = new PIXI.Circle(0, 0, menu3.width / 2);
    menu3.width = 0;
    menu3.height = 0;
    menu3.anchor.set(0.5);

    menuHover = new sprite(id["menu-hover.png"]);
    menuHover.position.set(910, 75);
    menuHover.anchor.set(0.5);
    menuHover.alpha = 0;

    menu2Hover = new sprite(id["menu-hover.png"]);
    menu2Hover.position.set(1040, 75);
    menu2Hover.anchor.set(0.5);
    menu2Hover.alpha = 0;

    menu3Hover = new sprite(id["menu-hover.png"]);
    menu3Hover.position.set(1170, 75);
    menu3Hover.anchor.set(0.5);
    menu3Hover.alpha = 0;

    finalImg = new sprite(id["final.png"]);
    finalImg.position.set(700, 250);
    finalImg.anchor.set(0.5);
    finalImgSize = {
      width: finalImg.width,
      height: finalImg.height
    };
    finalImg.width = 0;
    finalImg.height = 0;

    overlay = graphics.beginFill(0x000000);
    graphics.drawRect(0, 0, app.renderer.view.width, app.renderer.view.height);
    graphics.endFill();
    overlay.alpha = 0;
    overlay.interactive = true;
    overlay.visible = false;
  }

  function addEvents() {
    hammer.on('click', function(){
      hammer.interactive = false;
      ease.removeEase(hammer);
      ease.add(hammer, { alpha: 0 }, { repeat: false, duration: 300, ease: 'linear' });
      ease.add(menu, { width: menuW, height: menuH }, { duration: 1000, ease: 'easeOutElastic' });
      ease.add(stairIcon1, { width: stairIconSize.width, height: stairIconSize.height }, { duration: 1000, ease: 'easeOutElastic' });
      ease.add(menu2, { width: menuW, height: menuH }, {wait: 100, duration: 1000, ease: 'easeOutElastic' });
      ease.add(stairIcon2, { width: stairIconSize.width, height: stairIconSize.height }, {wait: 100, duration: 1000, ease: 'easeOutElastic' });
      ease.add(menu3, { width: menuW, height: menuH }, {wait: 200, duration: 1000, ease: 'easeOutElastic' });
      ease.add(stairIcon3, { width: stairIconSize.width, height: stairIconSize.height }, {wait: 200, duration: 1000, ease: 'easeOutElastic' });

    });

    menu.on('click', function(){
      isMenuClicked = {
        menu1: true,
        menu2: false,
        menu3: false
      };
      btnOk.position.set(910, 150);
      newStair1.position.set(1150, 228);
      oldStair.alpha = 0;
      newStair2.alpha = 0;
      newStair3.alpha = 0;
      ease.add(btnOk, { alpha: 1 }, { repeat: false, duration: 300, ease: 'linear' });
      ease.add(btnOk, { y: btnOk.y + 10 }, { repeat: true, reverse: true, duration: 200, ease: 'easeOutQuad' });
      ease.add(newStair1, { alpha: 1, y: 328 }, { repeat: false, duration: 300, ease: 'linear' });
      ease.add(menu2Hover, { alpha: 0 }, { repeat: false, duration: 300, ease: 'linear' });
      ease.add(menu3Hover, { alpha: 0 }, { repeat: false, duration: 300, ease: 'linear' });
    });

    menu.on('mouseover', function(){
      if(!isMenuClicked.menu1){
        ease.add(menuHover, { alpha: 1 }, { repeat: false, duration: 300, ease: 'linear' });
      }
    });

    menu.on('mouseout', function(){
      if(!isMenuClicked.menu1){
        ease.add(menuHover, { alpha: 0 }, { repeat: false, duration: 300, ease: 'linear' });
      }
    });

    menu2.on('click', function(){
      isMenuClicked = {
        menu1: false,
        menu2: true,
        menu3: false
      };
      oldStair.alpha = 0;
      newStair1.alpha = 0;
      newStair3.alpha = 0;
      btnOk.position.set(1040, 150);
      newStair2.position.set(1150, 228);
      ease.add(btnOk, { alpha: 1 }, { repeat: false, duration: 300, ease: 'linear' });
      ease.add(btnOk, { y: btnOk.y + 10 }, { repeat: true, reverse: true, duration: 200, ease: 'easeOutQuad' });
      ease.add(newStair2, { alpha: 1, y: 328 }, { repeat: false, duration: 300, ease: 'linear' });
      ease.add(menuHover, { alpha: 0 }, { repeat: false, duration: 300, ease: 'linear' });
      ease.add(menu3Hover, { alpha: 0 }, { repeat: false, duration: 300, ease: 'linear' });
    });

    menu2.on('mouseover', function(){
      if(!isMenuClicked.menu2){
        ease.add(menu2Hover, { alpha: 1 }, { repeat: false, duration: 300, ease: 'linear' });
      }
    });

    menu2.on('mouseout', function(){
      if(!isMenuClicked.menu2){
        ease.add(menu2Hover, { alpha: 0 }, { repeat: false, duration: 300, ease: 'linear' });
      }
    });

    menu3.on('click', function(){
      isMenuClicked = {
        menu1: false,
        menu2: false,
        menu3: true
      };
      oldStair.alpha = 0;
      newStair1.alpha = 0;
      newStair2.alpha = 0;
      btnOk.position.set(1170, 150);
      newStair3.position.set(1150, 228);
      ease.add(btnOk, { alpha: 1 }, { repeat: false, duration: 300, ease: 'linear' });
      ease.add(btnOk, { y: btnOk.y + 10 }, { repeat: true, reverse: true, duration: 200, ease: 'easeOutQuad' });
      ease.add(newStair3, { alpha: 1, y: 328 }, { repeat: false, duration: 300, ease: 'linear' });
      ease.add(menu2Hover, { alpha: 0 }, { repeat: false, duration: 300, ease: 'linear' });
      ease.add(menuHover, { alpha: 0 }, { repeat: false, duration: 300, ease: 'linear' });
    });

    menu3.on('mouseover', function(){
      if(!isMenuClicked.menu3){
        ease.add(menu3Hover, { alpha: 1 }, { repeat: false, duration: 300, ease: 'linear' });
      }
    });

    menu3.on('mouseout', function(){
      if(!isMenuClicked.menu3){
        ease.add(menu3Hover, { alpha: 0 }, { repeat: false, duration: 300, ease: 'linear' });
      }
    });

    btn.on('click', function(){
      window.open('https://playrix.ru/mobile-games/index.html');
    });

    btnOk.on('click', function(){
      overlay.visible = true;
      ease.add(finalImg, { width: finalImgSize.width, height: finalImgSize.height }, { duration: 800, ease: 'easeOutElastic' });
      ease.add(overlay, { alpha: 0.5 }, { repeat: false, duration: 500, ease: 'linear' });
      ease.removeEase(btnOk);
    });
  }

  function addImgToStage() {
    //Add images to the stage
    app.stage.addChild(bg);
    app.stage.addChild(austin);
    app.stage.addChild(book);
    app.stage.addChild(chair);
    app.stage.addChild(globe);
    app.stage.addChild(plant1);
    app.stage.addChild(plant2);
    app.stage.addChild(table);
    app.stage.addChild(newStair1);
    app.stage.addChild(newStair2);
    app.stage.addChild(newStair3);
    app.stage.addChild(menu);
    app.stage.addChild(menu2);
    app.stage.addChild(menu3);
    app.stage.addChild(menuHover);
    app.stage.addChild(menu2Hover);
    app.stage.addChild(menu3Hover);
    app.stage.addChild(btnOk);
    app.stage.addChild(stairIcon1);
    app.stage.addChild(stairIcon2);
    app.stage.addChild(stairIcon3);
    app.stage.addChild(oldStair);
    app.stage.addChild(decor);
    app.stage.addChild(hammer);
    app.stage.addChild(overlay);
    app.stage.addChild(logo);
    app.stage.addChild(btn);
    app.stage.addChild(finalImg);
  }

  function animateByFrame() {
    // Rotate Austin
    if(app.renderer.plugins.interaction.mouse.global.x < austin.x){
      austin.scale.x = -1;
    } else {
      austin.scale.x = 1;
    }
    app.renderer.render(app.stage);
    requestAnimationFrame(animateByFrame);
  }

  function resize() {
    let w, h;
    if (window.innerWidth / window.innerHeight >= ratio) {
       w = window.innerHeight * ratio;
       h = window.innerHeight;
    } else {
       w = window.innerWidth;
       h = window.innerWidth / ratio;
    }
    app.renderer.view.style.width = w + 'px';
    app.renderer.view.style.height = h + 'px';
    app.renderer.view.style.top = (window.innerHeight / 2 - h / 2) + 'px';

  }

  window.onresize = resize;
};




