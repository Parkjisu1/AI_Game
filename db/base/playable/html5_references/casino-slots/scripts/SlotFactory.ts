import { Slot } from "./Slot";
import { Item } from "./Item";

export class SlotFactory {

    static createSlot(slotsNum: number, slotConfig: string[][]): Slot[] {
        const slots: Slot[] = [];
        let x = 0;
        let y = 0;
        const offset = 0;

        for (let i = 0; i < slotsNum; i++) {
            const slot = new Slot({ texture: 'slot' });

            x = slot.node.width * i + offset * i;
            slot.node.x = x;
            slot.id = i;
            for (let j = 0; j < slotConfig[i].length; j++){


                const type = slotConfig[i][j];
                const item = this.createItem(type);
                slot.addItem(item);
                slot.hideItem(type);


                
            }

            slots.push(slot);

        }

        return slots;
    }

    static createItem(type: string) {
        const texture = `${type}`;
        const item = new Item({ type, texture });
        return item;
    }
}