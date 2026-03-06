import { _decorator, Component, director, Node, input, Input, EventKeyboard, KeyCode } from 'cc';
const { ccclass, property } = _decorator;

@ccclass('GameManager')
export class GameManager extends Component {
    @property({ type: Node }) startMenu: Node | null = null;   // Initial PLAY screen
    @property({ type: Node }) inGameUI: Node | null = null;   // Pause button (upper right)
    @property({ type: Node }) pauseMenu: Node | null = null;  // Pause overlay with RESUME

    /** Initialize game state: show start menu, hide others, pause game */
    start() {
        if (this.startMenu) this.startMenu.active = true;
        if (this.inGameUI) this.inGameUI.active = false;
        if (this.pauseMenu) this.pauseMenu.active = false;
        
        director.pause(); // Freeze game until PLAY pressed
        input.on(Input.EventType.KEY_DOWN, this._onKeyDown, this);
    }

    /** Cleanup input listeners */
    onDestroy() {
        input.off(Input.EventType.KEY_DOWN, this._onKeyDown, this);
    }

    /** Start gameplay: hide start menu, show in-game UI, unpause */
    startGame() {
        if (!this.startMenu || !this.inGameUI) return;
        
        this.startMenu.active = false;
        this.inGameUI.active = true;
        this.pauseMenu.active = false;
        director.resume();
    }

    /** Pause gameplay: hide in-game UI, show pause menu, freeze game */
    pauseGame() {
        if (!director.isPaused || !this.inGameUI || !this.pauseMenu) return;
        
        this.inGameUI.active = false;
        this.pauseMenu.active = true;
        director.pause();
    }

    /** Resume gameplay: hide pause menu, show in-game UI, unpause */
    resumeGame() {
        if (!director.isPaused || !this.inGameUI || !this.pauseMenu) return;
        
        this.pauseMenu.active = false;
        this.inGameUI.active = true;
        director.resume();
    }

    /** Handle ESC key: toggle pause during gameplay */
    private _onKeyDown(event: EventKeyboard) {
        if (event.keyCode === KeyCode.ESCAPE && this.inGameUI?.active && !director.isPaused) {
            this.pauseGame();
        }
    }
}