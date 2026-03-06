import { Container } from "./Core/RenderElements/Container";
import { StartTutorial } from "./StartTutorial";
import { SlotMachine } from "./SlotMachine";
import { WinPopup } from "./WinPopup";

const elementConfig = {
    children: {
        startTutorial: { class: StartTutorial, id: 'startTutorial', visible: false },
        slotMachine: { class: SlotMachine, id: 'slotMachine', visible: false },
        winPopup: { class: WinPopup, id: 'winPopup', visible: false },
    } 
}

export class Main extends Container {

    constructor(config) {
        super({ ...elementConfig, ...config });

    }
    
    protected onResize(): void {
        this.toCenter();
    }
}