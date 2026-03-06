export class Utils {

    static lerpColor(colorFrom: number, colorTo: number, k: number): number {
        k = Math.max(0, Math.min(1, k));

        const fromR = (colorFrom >> 16) & 0xFF;
        const fromG = (colorFrom >> 8) & 0xFF;
        const fromB = colorFrom & 0xFF;

        const toR = (colorTo >> 16) & 0xFF;
        const toG = (colorTo >> 8) & 0xFF;
        const toB = colorTo & 0xFF;

        const resultR = Math.round(fromR + (toR - fromR) * k);
        const resultG = Math.round(fromG + (toG - fromG) * k);
        const resultB = Math.round(fromB + (toB - fromB) * k);

        const resultColor = (resultR << 16) | (resultG << 8) | resultB;

        return resultColor;
    }

}